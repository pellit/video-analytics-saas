import cv2
import numpy as np
import os
import urllib.request
import time
import base64
import requests
from collections import deque
from typing import Any, Dict, List, Optional

# ==========================================
# 0. API WRAPPER
# ==========================================
class ExternalApiWrapper:
    def __init__(self, base_url="http://localhost:5050"):
        self.base_url = base_url

    def segment_image(self, image_b64):
        url = f"{self.base_url}/segment/image"
        payload = {"image_base64": f"data:image/jpeg;base64,{image_b64}"}
        try:
            resp = requests.post(url, json=payload, timeout=2.0)
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
        return "Error API"

# ==========================================
# 1. SISTEMA DE CALIBRACIÓN AUTÓNOMA
# ==========================================
class BallCalibrator:
    def __init__(self):
        # Tamaños estándar (Diámetro cm)
        self.SIZES = {
            3: 18.0, # Niños pequeños
            4: 20.0, # Niños 8-12
            5: 22.0  # Estándar
        }
        self.samples = [] 
        self.is_calibrated = False
        self.selected_size_id = 5 # Asunción inicial
        self.real_diameter_cm = 22.0
        self.px_per_cm = 1.0 # Valor seguro inicial

    def add_sample(self, ball_width_px, is_near_feet):
        # Solo tomamos muestras fiables (cerca del suelo/pies)
        if is_near_feet and ball_width_px > 8:
            self.samples.append(ball_width_px)

    def finalize_calibration(self, player_height_px):
        """
        Algoritmo de Inferencia Biológica:
        Deduce el tamaño de la pelota según la altura lógica del jugador.
        """
        if not self.samples: return False
        
        # 1. Obtener la mediana del ancho de la pelota (filtra errores)
        median_ball_px = np.median(self.samples)
        
        # 2. Prueba de Hipótesis: ¿Si la pelota fuera Nº 5, cuánto mide el jugador?
        scale_if_size_5 = median_ball_px / 22.0
        height_if_size_5 = player_height_px / scale_if_size_5
        
        print(f"[AUTO-CALIB] Mediana Pelota: {median_ball_px}px. Altura Jugador (Hipótesis T5): {height_if_size_5:.1f}cm")

        # 3. Árbol de Decisión
        if height_if_size_5 > 155:
            self.selected_size_id = 5 # Es adulto o joven alto
        elif 135 < height_if_size_5 <= 155:
            self.selected_size_id = 4 # Es niño mediano
        else:
            self.selected_size_id = 3 # Es niño pequeño
            
        # 4. Fijar calibración final
        self.real_diameter_cm = self.SIZES[self.selected_size_id]
        self.px_per_cm = median_ball_px / self.real_diameter_cm
        self.is_calibrated = True
        return True

# ==========================================
# 2. CLASES IA (YOLO)
# ==========================================
class YoloBaseWrapper:
    def __init__(self, model_path, conf_thres=0.4, iou_thres=0.5):
        self.model_path = model_path
        self.conf_thres = conf_thres
        self.iou_thres = iou_thres
        self.net = None
        self.input_size = (640, 640)

    def load_model(self, name="YOLO"):
        if not os.path.exists(self.model_path) or os.path.getsize(self.model_path) < 1000: return False
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
            box_scaled = [int((box[0]-box[2]/2)*sx), int((box[1]-box[3]/2)*sy), int(box[2]*sx), int(box[3]*sy)]
            people.append({"keypoints": scaled, "box": box_scaled})
        return people

# ==========================================
# 2. SERVICIO INTELIGENTE
# ==========================================
class HitDetectionService:
    def __init__(self, default_model_dirs: List[str] = None):
        self.models_dir = "/app/ai_engine/models"
        self.det_path = os.path.join(self.models_dir, "yolov8n.onnx")       
        self.pose_path = os.path.join(self.models_dir, "yolov8n-pose.onnx")  
        self.midas_path = os.path.join(self.models_dir, "midas_v21_small.onnx") 
        
        self.api = ExternalApiWrapper()
        
        # Enlaces HF (Mirrors estables)
        self.det_url = "https://github.com/pellit/video-analytics-saas/raw/796d243e692b5b18f0344b033a152dcdd6326f36/ai_engine/yolov8n.onnx"
        self.pose_url = "https://huggingface.co/Xenova/yolov8-pose-onnx/resolve/main/yolov8n-pose.onnx?download=true"
        self.midas_url = "https://github.com/isl-org/MiDaS/releases/download/v2_1/model-small.onnx"

        self._check_and_download_models()
        
        # Umbral bajo para la pelota (captar movimiento rápido)
        self.det_model = YoloDetWrapper(self.det_path, conf_thres=0.25)
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

        # --- ESTADO ---
        self.juggles_count = 0        
        self.dribble_state = "Calibrando..." 
        self.prev_ball_y = None   
        self.ball_velocity_y = 0  
        self.last_hit_frame = -100 
        
        self.faces_start, self.faces_middle = [], []
        self.detected_floor_y = None 
        
        # Instancia Calibrador Automático
        self.calibrator = BallCalibrator()
        self.player_height_m = 0.0

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

    def check_orientation(self, kpts):
        nose = kpts[0]
        eyes = (kpts[1]['conf'] > 0.5 and kpts[2]['conf'] > 0.5)
        ears = (kpts[3]['conf'] > 0.5 and kpts[4]['conf'] > 0.5)
        if nose['conf'] > 0.6 and eyes: return "Frente"
        elif not nose['conf'] > 0.4 and ears: return "Espalda"
        return "Lado"

    def analyze_football(self, ball_box, person_box, person_kpts, depth_map, frame_idx):
        bx, by, bw, bh = ball_box[:4]
        ball_cx = bx + bw//2
        ball_bottom_y = by + bh 
        
        # --- CALIBRACIÓN AUTOMÁTICA ---
        # 1. Recolectar muestras si la pelota está "abajo" (cerca de los pies)
        feet = [person_kpts[15], person_kpts[16]]
        valid_feet = [f for f in feet if f['conf'] > 0.5]
        
        if valid_feet:
            feet_y_avg = sum([f['y'] for f in valid_feet]) / len(valid_feet)
            is_near_feet = abs(ball_bottom_y - feet_y_avg) < 100 
            
            if not self.calibrator.is_calibrated and is_near_feet:
                self.calibrator.add_sample(bw, True)
                
            # 2. Finalizar calibración en frame 30 (Suficientes muestras)
            if frame_idx == 30 and not self.calibrator.is_calibrated:
                self.calibrator.finalize_calibration(person_box[3]) 

        # Si aún no calibramos, usamos escala genérica, sino la inferida
        scale = self.calibrator.px_per_cm if self.calibrator.is_calibrated else 2.0 
        
        # Cálculo altura jugador en vivo
        if self.calibrator.is_calibrated:
            self.player_height_m = (person_box[3] / scale) / 100.0

        # --- LÓGICA DE JUEGO ---
        try: ball_z = depth_map[by+bh//2, bx+bw//2]
        except: return "", "Indefinido"

        orientation = self.check_orientation(person_kpts)
        if not valid_feet: return "", orientation

        if self.detected_floor_y: ground_y = self.detected_floor_y
        else: ground_y = max([f['y'] for f in valid_feet])

        curr_vel = 0
        if self.prev_ball_y is not None: curr_vel = ball_bottom_y - self.prev_ball_y
        is_moving_up = (curr_vel < -2)
        self.prev_ball_y = ball_bottom_y
        
        event = ""
        ball_height_cm = (ground_y - ball_bottom_y) / scale

        # JUGGLING (> 15cm Aire)
        if ball_height_cm > 15:
            if is_moving_up:
                for foot in valid_feet:
                    dist_x_cm = abs(foot['x'] - ball_cx) / scale
                    dist_y_cm = abs(foot['y'] - ball_bottom_y) / scale
                    try: foot_z = depth_map[foot['y'], foot['x']]
                    except: foot_z = 0
                    dist_z = abs(int(ball_z) - int(foot_z))

                    # Tolerancia de golpe efectiva
                    if dist_x_cm < 30 and dist_y_cm < 30 and dist_z < 60:
                        if (frame_idx - self.last_hit_frame) > 8:
                            self.juggles_count += 1
                            self.last_hit_frame = frame_idx
                            event = "JUGGLE!"
                            break

        # DRIBBLE (<= 15cm Piso)
        elif ball_height_cm <= 15:
            closest_cm = 999
            for f in valid_feet:
                d_px = np.sqrt((f['x']-ball_cx)**2 + (f['y']-ball_bottom_y)**2)
                d_cm = d_px / scale
                if d_cm < closest_cm: closest_cm = d_cm
            
            if closest_cm < 60:
                cx = (feet[0]['x'] + feet[1]['x']) / 2
                side = ""
                if orientation == "Frente":
                    if ball_cx > cx + 10: side = "Izquierda (M)"
                    elif ball_cx < cx - 10: side = "Derecha (M)"
                else:
                    if ball_cx > cx + 10: side = "Derecha"
                    elif ball_cx < cx - 10: side = "Izquierda"
                self.dribble_state = f"Control {side}"
                event = self.dribble_state

        return event, orientation

    def draw_debug_panel(self, frame, kpts, ball_box, depth_map, orientation):
        h, w = frame.shape[:2]
        panel = np.zeros((h, 320, 3), dtype=np.uint8)
        panel[:] = (30, 30, 30)
        
        bx, by, bw, bh = ball_box[:4]
        bcx, bcy = bx+bw//2, by+bh//2
        try: bz = int(depth_map[bcy, bcx])
        except: bz = 128
        feet = [kpts[15], kpts[16]]

        # Planta XZ
        cv2.putText(panel, "PLANTA (XZ)", (10,30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)
        cv2.rectangle(panel, (20,50), (300,200), (50,50,50), -1)
        def map_xz(x, z): return (20+int(x/w*280), 50+int(z/255.0*150))
        b_xz = map_xz(bcx, bz)
        cv2.circle(panel, b_xz, 6, (0,140,255), -1)
        for f in feet:
            if f['conf']>0.5:
                try: fz = int(depth_map[f['y'], f['x']])
                except: fz=128
                f_xz = map_xz(f['x'], fz)
                cv2.circle(panel, f_xz, 5, (0,255,0), -1)

        # Perfil ZY
        cv2.putText(panel, "PERFIL (ZY)", (10,240), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)
        cv2.rectangle(panel, (20,260), (300,410), (50,50,50), -1)
        def map_zy(z, y): return (20+int(z/255.0*280), 260+int(y/h*150))
        b_zy = map_zy(bz, by+bh)
        cv2.circle(panel, b_zy, 6, (0,140,255), -1)
        
        if self.detected_floor_y:
            floor_y_map = map_zy(128, self.detected_floor_y)[1]
            cv2.line(panel, (20, floor_y_map), (300, floor_y_map), (0,0,255), 1)

        # Stats Visuales
        color_calib = (0, 255, 0) if self.calibrator.is_calibrated else (0, 0, 255)
        txt_size = f"N {self.calibrator.selected_size_id} ({self.calibrator.real_diameter_cm}cm)"
        cv2.putText(panel, f"Ball: {txt_size}", (10, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color_calib, 1)
        cv2.putText(panel, f"Playr: {self.player_height_m:.2f}m", (10, 480), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200,200,200), 1)
        cv2.putText(panel, f"Juggl: {self.juggles_count}", (10, 520), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0,255,255), 2)

        return np.hstack((frame, panel))

    # SIN PARÁMETROS MANUALES (100% Autónomo)
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
            
            # Detección Piso (Frame 10)
            if processed == 10:
                _, b = cv2.imencode('.jpg', frame)
                seg_res = self.api.segment_image(base64.b64encode(b).decode('utf-8'))
                if seg_res and 'floor_y' in seg_res: self.detected_floor_y = int(seg_res['floor_y'])

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
                depth_map = self.get_depth_map(frame)
                
                if depth_map is not None:
                    event, orientation = self.analyze_football(ball, person['box'], person['keypoints'], depth_map, frame_idx)
                    
                    # Recolectar Caras (Frente)
                    if orientation == "Frente":
                        if processed < 50 and len(self.faces_start) < 4:
                            f = self.extract_face(frame, person['keypoints'])
                            if f: self.faces_start.append(f)
                        if processed > (max_frames//2) and len(self.faces_middle) < 4:
                            f = self.extract_face(frame, person['keypoints'])
                            if f: self.faces_middle.append(f)

                    if return_images:
                        vis_frame = self.draw_debug_panel(vis_frame, person['keypoints'], ball, depth_map, orientation)
                
                if not return_images:
                    cv2.rectangle(vis_frame, (ball[0], ball[1]), (ball[0]+ball[2], ball[1]+ball[3]), (0,0,255), 2)
            
            # Guardado inteligente de imágenes
            is_important = (event != "" and "Control" not in event and event != "Parado")
            is_sample = (processed % 15 == 0)
            
            if return_images:
                if (is_important) or (is_sample and len(images_output) < 30):
                    if not event and not is_important:
                        cv2.putText(vis_frame, f"Count: {self.juggles_count}", (30,50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2)
                    _, buf = cv2.imencode('.jpg', vis_frame)
                    b64 = base64.b64encode(buf).decode('utf-8')
                    images_output.append({"image_id": str(frame_idx), "image_base64": f"data:image/jpeg;base64,{b64}"})

            processed += 1
            frame_idx += 1

        cap.release()
        face_res = "N/A"
        if self.faces_start and self.faces_middle:
            face_res = self.api.compare_faces(self.faces_start[0], self.faces_middle[0])

        total_t = time.time() - start_t
        
        return {
            "id": int(time.time()),
            "hit_images": images_output,
            "meta": {
                "performance": {
                    "total_time_s": round(total_t, 2),
                    "video_duration_s": round(dur_s, 2),
                    "frames_processed": processed
                },
                "stats": {
                    "total_juggles": self.juggles_count,
                    "final_state": self.dribble_state,
                    # Aquí la IA te dice qué decidió
                    "inferred_ball_size": f"Size {self.calibrator.selected_size_id} ({self.calibrator.real_diameter_cm}cm)",
                    "inferred_player_height_m": round(self.player_height_m, 2)
                },
                "face_verification": face_res
            }
        }