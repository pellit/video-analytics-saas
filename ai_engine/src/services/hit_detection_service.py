import cv2
import numpy as np
import os
import urllib.request
import time
import base64
import requests
from typing import Any, Dict, List

# ==========================================
# 0. API WRAPPER
# ==========================================
class ExternalApiWrapper:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url

    def segment_image(self, image_b64):
        url = f"{self.base_url}/segment/image"
        payload = {"image_base64": f"data:image/jpeg;base64,{image_b64}"}
        try:
            resp = requests.post(url, json=payload, timeout=1.0) # Timeout rápido
            if resp.status_code == 200: return resp.json()
        except: pass
        return None

    def compare_faces(self, face_a_b64, face_b_b64):
        url = f"{self.base_url}/face/compare"
        payload = {"image_a_base64": face_a_b64, "image_b_base64": face_b_b64, "score_threshold": 0.6}
        try:
            resp = requests.post(url, json=payload, timeout=2.0)
            if resp.status_code == 200: return resp.json()
        except: pass
        return "Error conexión"

# ==========================================
# 1. CLASES DE IA
# ==========================================
class YoloBaseWrapper:
    def __init__(self, model_path, conf_thres=0.4, iou_thres=0.5):
        self.model_path = model_path
        self.conf_thres = conf_thres
        self.iou_thres = iou_thres
        self.net = None
        self.input_size = (640, 640)

    def load_model(self, name="YOLO"):
        if not os.path.exists(self.model_path) or os.path.getsize(self.model_path) < 1000:
            return False
        try:
            self.net = cv2.dnn.readNet(self.model_path)
            self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
            self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
            self.net.setInput(np.zeros((1, 3, 640, 640), dtype=np.float32))
            self.net.forward()
            print(f"[{name}] ✅ GPU Ready.")
            return True
        except: return False

    def preprocess(self, img):
        return cv2.dnn.blobFromImage(img, 1/255.0, self.input_size, swapRB=True, crop=False)

class YoloDetWrapper(YoloBaseWrapper):
    def detect_ball(self, blob, img_w, img_h):
        if self.net is None: return []
        self.net.setInput(blob)
        outputs = self.net.forward()
        preds = np.squeeze(outputs[0]).T
        if preds.shape[1] > 36:
            scores = preds[:, 32+4] 
            keep = scores > self.conf_thres
            preds = preds[keep]
            scores = scores[keep]
        else: return []
        if len(scores) == 0: return []
        boxes = preds[:, :4]
        boxes[:, 0] -= boxes[:, 2] / 2
        boxes[:, 1] -= boxes[:, 3] / 2
        indices = cv2.dnn.NMSBoxes(boxes.tolist(), scores.tolist(), self.conf_thres, self.iou_thres)
        balls = []
        sx, sy = img_w / self.input_size[0], img_h / self.input_size[1]
        for i in indices.flatten():
            b = boxes[i]
            balls.append([int(b[0]*sx), int(b[1]*sy), int(b[2]*sx), int(b[3]*sy), float(scores[i])])
        return balls

class YoloPoseWrapper(YoloBaseWrapper):
    def detect_pose(self, blob, img_w, img_h):
        if self.net is None: return []
        self.net.setInput(blob)
        outputs = self.net.forward()
        preds = np.squeeze(outputs[0]).T
        scores = preds[:, 4]
        keep = scores > self.conf_thres
        preds = preds[keep]
        scores = scores[keep]
        if len(scores) == 0: return []
        kpts = preds[:, 5:]
        indices = cv2.dnn.NMSBoxes(preds[:, :4].tolist(), scores.tolist(), self.conf_thres, self.iou_thres)
        people = []
        sx, sy = img_w / self.input_size[0], img_h / self.input_size[1]
        for i in indices.flatten():
            pk = kpts[i].reshape(-1, 3)
            scaled = [{"x": int(p[0]*sx), "y": int(p[1]*sy), "conf": float(p[2])} for p in pk]
            box = preds[i, :4]
            box_sc = [int((box[0]-box[2]/2)*sx), int((box[1]-box[3]/2)*sy), int(box[2]*sx), int(box[3]*sy)]
            people.append({"keypoints": scaled, "box": box_sc})
        return people

# ==========================================
# 2. SERVICIO PRINCIPAL
# ==========================================
class HitDetectionService:
    def __init__(self, default_model_dirs: List[str] = None):
        self.models_dir = "/app/ai_engine/models"
        self.det_path = os.path.join(self.models_dir, "yolov8n.onnx")       
        self.pose_path = os.path.join(self.models_dir, "yolov8n-pose.onnx")  
        self.midas_path = os.path.join(self.models_dir, "midas_v21_small.onnx") 
        
        self.api = ExternalApiWrapper()
        
        # URLs
        self.det_url = "https://github.com/pellit/video-analytics-saas/raw/796d243e692b5b18f0344b033a152dcdd6326f36/ai_engine/yolov8n.onnx"
        self.pose_url = "https://huggingface.co/Xenova/yolov8-pose-onnx/resolve/main/yolov8n-pose.onnx?download=true"
        self.midas_url = "https://github.com/isl-org/MiDaS/releases/download/v2_1/model-small.onnx"

        self._check_and_download_models()
        
        self.det_model = YoloDetWrapper(self.det_path, conf_thres=0.20) # Umbral MUY sensible para pelota
        self.det_model.load_model("BALL")
        self.pose_model = YoloPoseWrapper(self.pose_path, conf_thres=0.5)
        self.pose_model.load_model("POSE")
        
        self.midas_net = None
        if os.path.exists(self.midas_path):
            try:
                self.midas_net = cv2.dnn.readNet(self.midas_path)
                self.midas_net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
                self.midas_net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
            except: pass

        # Variables Estado
        self.juggles_count = 0        
        self.dribble_state = "Parado" 
        self.prev_ball_y = None   
        self.ball_velocity_y = 0  
        self.last_hit_frame = -100 
        
        # Buffer Caras
        self.faces_start = []
        self.faces_middle = []
        self.scene_segmentation = None

    def _check_and_download_models(self):
        os.makedirs(self.models_dir, exist_ok=True)
        downloads = [(self.det_url, self.det_path), (self.pose_url, self.pose_path), (self.midas_url, self.midas_path)]
        for url, path in downloads:
            if not os.path.exists(path) or os.path.getsize(path) < 100000:
                try: urllib.request.urlretrieve(url, path)
                except: pass

    def get_depth_map(self, frame):
        if self.midas_net is None: return None
        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(frame, 1/255.0, (256, 256), (123.675, 116.28, 103.53), True, False)
        self.midas_net.setInput(blob)
        depth = self.midas_net.forward()
        return cv2.normalize(cv2.resize(depth[0,0], (w, h)), None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)

    def extract_face(self, frame, kpts):
        pts = [kpts[i] for i in range(5) if kpts[i]['conf'] > 0.4]
        if len(pts) < 3: return None
        xs, ys = [p['x'] for p in pts], [p['y'] for p in pts]
        pad = 40
        x1, y1 = max(0, min(xs)-pad), max(0, min(ys)-pad*2)
        x2, y2 = min(frame.shape[1], max(xs)+pad), min(frame.shape[0], max(ys)+pad)
        if x2-x1 < 20: return None
        _, buf = cv2.imencode('.jpg', frame[y1:y2, x1:x2])
        return base64.b64encode(buf).decode('utf-8')

    def analyze_football(self, ball_box, person_kpts, depth_map, frame_idx):
        bx, by, bw, bh = ball_box[:4]
        ball_cx = bx + bw//2
        ball_cy = by + bh//2
        ball_bottom_y = by + bh 

        try: ball_z = depth_map[ball_cy, ball_cx]
        except: return ""

        feet = [person_kpts[15], person_kpts[16]]
        valid_feet = [f for f in feet if f['conf'] > 0.5]
        if not valid_feet: return ""

        # Velocidad
        curr_vel = 0
        if self.prev_ball_y is not None:
            curr_vel = ball_bottom_y - self.prev_ball_y
        
        # Detectar aceleración hacia arriba (Golpe) O Pelota estable
        # Relajamos: Ya no exigimos que baje antes. Solo que suba de golpe o esté quieta y suba.
        is_moving_up = (curr_vel < -2) 
        
        self.prev_ball_y = ball_bottom_y
        self.ball_velocity_y = curr_vel

        event = ""
        ground_y = max([f['y'] for f in valid_feet])
        ball_height = ground_y - ball_bottom_y

        # JUGGLING (Aire > 20px)
        if ball_height > 20:
            for foot in valid_feet:
                dist_x = abs(foot['x'] - ball_cx)
                dist_y = abs(foot['y'] - ball_bottom_y) # Distancia vertical pie-pelota
                
                # Z Check
                try: foot_z = depth_map[foot['y'], foot['x']]
                except: foot_z = 0
                dist_z = abs(int(ball_z) - int(foot_z))

                # LÓGICA HÍBRIDA:
                # 1. Golpe Fuerte: Sube rápido (is_moving_up) Y está cerca
                # 2. Toque Suave/Control: Está MUY cerca (dist_y < 30) aunque no suba rápido
                hit_condition_strong = is_moving_up and dist_x < 70 and dist_y < 80
                hit_condition_soft = dist_x < 50 and dist_y < 40 # Pie "dentro" de la pelota visualmente
                
                if (hit_condition_strong or hit_condition_soft) and dist_z < 60:
                    if (frame_idx - self.last_hit_frame) > 8: # Debounce un poco más rápido
                        self.juggles_count += 1
                        self.last_hit_frame = frame_idx
                        event = "JUGGLE!"
                        break

        # DRIBBLE (Piso <= 20px)
        elif ball_height <= 20:
            closest = 999
            for f in valid_feet:
                d = np.sqrt((f['x']-ball_cx)**2 + (f['y']-ball_bottom_y)**2)
                if d < closest: closest = d
            
            if closest < 90:
                cx = (feet[0]['x'] + feet[1]['x']) / 2
                if ball_cx > cx + 20: self.dribble_state = "Derecha >>"
                elif ball_cx < cx - 20: self.dribble_state = "<< Izquierda"
                else: self.dribble_state = "Control"
                event = self.dribble_state

        return event

    def draw_debug_panel(self, frame, kpts, ball_box, depth_map):
        h, w = frame.shape[:2]
        panel = np.zeros((h, 300, 3), dtype=np.uint8)
        panel[:] = (30, 30, 30)
        
        bx, by, bw, bh = ball_box[:4]
        bcx, bcy = bx+bw//2, by+bh//2
        try: bz = int(depth_map[bcy, bcx])
        except: bz = 128
        feet = [kpts[15], kpts[16]]

        # Vista Aerea (XZ)
        cv2.putText(panel, "VISTA AEREA (XZ)", (10,30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)
        cv2.rectangle(panel, (20,50), (280,200), (50,50,50), -1)
        
        def map_xz(x, z): return (20+int(x/w*260), 50+int(z/255.0*150))
        
        b_xz = map_xz(bcx, bz)
        cv2.circle(panel, b_xz, 6, (0,140,255), -1) # Pelota Naranja
        for f in feet:
            if f['conf']>0.5:
                try: fz = int(depth_map[f['y'], f['x']])
                except: fz=128
                f_xz = map_xz(f['x'], fz)
                cv2.circle(panel, f_xz, 5, (0,255,0), -1) # Pie Verde
                cv2.line(panel, b_xz, f_xz, (100,100,100), 1)

        # Vista Lateral (ZY)
        cv2.putText(panel, "VISTA LATERAL (ZY)", (10,240), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)
        cv2.rectangle(panel, (20,260), (280,410), (50,50,50), -1)

        def map_zy(z, y): return (20+int(z/255.0*260), 260+int(y/h*150))

        b_zy = map_zy(bz, by+bh) # Usamos base pelota
        cv2.circle(panel, b_zy, 6, (0,140,255), -1)
        for f in feet:
            if f['conf']>0.5:
                try: fz = int(depth_map[f['y'], f['x']])
                except: fz=128
                f_zy = map_zy(fz, f['y'])
                cv2.circle(panel, f_zy, 5, (0,255,0), -1)
                cv2.line(panel, (20, f_zy[1]), (280, f_zy[1]), (0,100,0), 1) # Linea suelo

        # Stats
        cv2.putText(panel, f"Juggles: {self.juggles_count}", (10, 450), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2)
        cv2.putText(panel, f"Accion: {self.dribble_state}", (10, 480), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200,200,200), 1)

        return np.hstack((frame, panel))

    def run_on_video(self, video_path, frame_stride=3, max_frames=300, hit_threshold=0.4, return_images=True):
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        dur_s = total_frames / fps if fps > 0 else 0
        
        frame_idx = 0
        processed = 0
        images_output = []
        
        start_t = time.time()
        self.faces_start, self.faces_middle = [], []
        
        while processed < max_frames:
            ret, frame = cap.read()
            if not ret: break
            if frame_idx % frame_stride != 0:
                frame_idx += 1
                continue
            
            h, w = frame.shape[:2]
            
            # Feature: Segmentación al inicio
            if processed == 30:
                _, b = cv2.imencode('.jpg', frame)
                self.scene_segmentation = self.api.segment_image(base64.b64encode(b).decode('utf-8'))

            # Inferencia
            det_blob = self.det_model.preprocess(frame)
            pose_blob = self.pose_model.preprocess(frame)
            balls = self.det_model.detect_ball(det_blob, w, h)
            people = self.pose_model.detect_pose(pose_blob, w, h)
            
            event = ""
            vis_frame = frame.copy()
            
            if len(balls) > 0 and len(people) > 0:
                ball = sorted(balls, key=lambda x: x[4])[-1]
                person = sorted(people, key=lambda x: (x['box'][2]*x['box'][3]))[-1]
                
                # Recolectar caras
                if processed < 50 and len(self.faces_start) < 4:
                    f = self.extract_face(frame, person['keypoints'])
                    if f: self.faces_start.append(f)
                if processed > (max_frames//2) and len(self.faces_middle) < 4:
                    f = self.extract_face(frame, person['keypoints'])
                    if f: self.faces_middle.append(f)

                depth_map = self.get_depth_map(frame)
                if depth_map is not None:
                    event = self.analyze_football(ball, person['keypoints'], depth_map, frame_idx)
                    if return_images:
                        vis_frame = self.draw_debug_panel(vis_frame, person['keypoints'], ball, depth_map)
                
                if not return_images:
                    cv2.rectangle(vis_frame, (ball[0], ball[1]), (ball[0]+ball[2], ball[1]+ball[3]), (0,0,255), 2)
            
            # --- CORRECCIÓN CLAVE: Lógica de guardado de imágenes ---
            # 1. SIEMPRE guardar si hay evento (Juggle o cambio de dribble importante)
            is_important_event = (event != "" and event != "Parado")
            
            # 2. Guardar muestras regulares (cada 10 frames procesados) para contexto
            is_sample = (processed % 10 == 0)
            
            # Guardamos si es importante O si es muestra (respetando límite total)
            if return_images:
                if (is_important_event) or (is_sample and len(images_output) < 30):
                    # Dibujar evento si no está en panel
                    if not event and not is_important_event:
                        cv2.putText(vis_frame, f"Juggles: {self.juggles_count}", (30,50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2)
                    
                    _, buf = cv2.imencode('.jpg', vis_frame)
                    b64 = base64.b64encode(buf).decode('utf-8')
                    images_output.append({
                        "image_id": str(frame_idx),
                        "image_base64": f"data:image/jpeg;base64,{b64}"
                    })

            processed += 1
            frame_idx += 1

        cap.release()
        
        # Comparación Facial Final
        face_res = "N/A"
        if self.faces_start and self.faces_middle:
            face_res = self.api.compare_faces(self.faces_start[0], self.faces_middle[0])

        total_t = time.time() - start_t
        
        return {
            "id": int(time.time()),
            "hit_images": images_output,
            "meta": {
                "performance": {
                    "fps_analysis": round(processed/total_t, 2) if total_t>0 else 0,
                    "total_processing_time_s": round(total_t, 2),
                    "video_duration_s": round(dur_s, 2),
                    "load_pct": round(total_t/dur_s*100, 2) if dur_s>0 else 0,
                    "frames_processed": processed
                },
                "stats": {
                    "total_juggles": self.juggles_count,
                    "final_state": self.dribble_state
                },
                "face_verification": face_res,
                "scene_context": self.scene_segmentation
            }
        }