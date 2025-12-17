import cv2
import numpy as np
import os
import urllib.request
import time
import base64
from typing import Any, Dict, List

# ==========================================
# 1. CLASES DE IA (WRAPPERS)
# ==========================================

class YoloBaseWrapper:
    def __init__(self, model_path, conf_thres=0.4, iou_thres=0.5):
        self.model_path = model_path
        self.conf_thres = conf_thres
        self.iou_thres = iou_thres
        self.net = None
        self.input_size = (640, 640)

    def load_model(self, name="YOLO"):
        print(f"[{name}] 📂 Verificando: {os.path.basename(self.model_path)}...")
        if not os.path.exists(self.model_path) or os.path.getsize(self.model_path) < 1000:
            print(f"[{name}] ❌ Archivo no encontrado.")
            return False
        try:
            self.net = cv2.dnn.readNet(self.model_path)
            self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
            self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
            dummy = np.zeros((1, 3, 640, 640), dtype=np.float32)
            self.net.setInput(dummy)
            self.net.forward()
            print(f"[{name}] ✅ Cargado en GPU.")
            return True
        except Exception as e:
            print(f"[{name}] ❌ Error: {e}")
            self.net = None
            return False

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
            keep_idxs = scores > self.conf_thres
            preds = preds[keep_idxs]
            scores = scores[keep_idxs]
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
            people.append({"keypoints": scaled, "box": preds[i, :4]})
        return people

# ==========================================
# 2. SERVICIO PRINCIPAL DE FÚTBOL
# ==========================================

class HitDetectionService:
    def __init__(self, default_model_dirs: List[str] = None):
        self.models_dir = "/app/ai_engine/models"
        self.det_path = os.path.join(self.models_dir, "yolov8n.onnx")       
        self.pose_path = os.path.join(self.models_dir, "yolov8n-pose.onnx")  
        self.midas_path = os.path.join(self.models_dir, "midas_v21_small.onnx") 

        self.det_url = "https://github.com/pellit/video-analytics-saas/raw/796d243e692b5b18f0344b033a152dcdd6326f36/ai_engine/yolov8n.onnx"
        self.pose_url = "https://huggingface.co/Xenova/yolov8-pose-onnx/resolve/main/yolov8n-pose.onnx?download=true"
        self.midas_url = "https://github.com/isl-org/MiDaS/releases/download/v2_1/model-small.onnx"

        print(f"\n[FÚTBOL AI] Iniciando servicio...")
        self._check_and_download_models()

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
                print("[MiDaS] ✅ Profundidad activa.")
            except: pass

        # --- VARIABLES DE FÍSICA ---
        self.juggles_count = 0        
        self.dribble_state = "Parado" 
        
        # Historial para calcular velocidad (dy)
        self.prev_ball_y = None   
        self.ball_velocity_y = 0  # + Baja, - Sube
        self.last_hit_frame = -100 # Cooldown por frames

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
        depth = cv2.resize(depth[0,0], (w, h))
        return cv2.normalize(depth, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)

    def analyze_football(self, ball_box, person_kpts, depth_map, frame_idx):
        """
        NUEVA LÓGICA: Borde Inferior + Cambio de Velocidad
        """
        # 1. Datos Geométricos
        bx, by, bw, bh = ball_box[:4]
        ball_center_x = bx + bw//2
        ball_center_y = by + bh//2
        
        # IMPORTANTE: Calcular el "Piso" de la pelota (Bottom Y)
        ball_bottom_y = by + bh 

        # 2. Profundidad (Z)
        try: ball_z = depth_map[ball_center_y, ball_center_x]
        except: return ""

        # 3. Datos Pies
        feet = [person_kpts[15], person_kpts[16]] # L, R
        valid_feet = [f for f in feet if f['conf'] > 0.5]
        if not valid_feet: return ""

        # 4. Cálculo de Velocidad (Física)
        # En imagen: Y aumenta hacia abajo.
        # Si Y crece -> Pelota bajando. Si Y decrece -> Pelota subiendo.
        current_velocity = 0
        if self.prev_ball_y is not None:
            current_velocity = ball_bottom_y - self.prev_ball_y
        
        # Detectar Cambio de Dirección (Bounce)
        # Estaba bajando (vel > 0) o quieta, y ahora sube (vel < 0)
        # Usamos un umbral de -2 para filtrar ruido (tiene que subir con fuerza)
        is_bouncing_up = (self.ball_velocity_y >= -1) and (current_velocity < -3)
        
        # Actualizar estado físico para el siguiente frame
        self.prev_ball_y = ball_bottom_y
        self.ball_velocity_y = current_velocity

        # 5. Lógica de Eventos
        event = ""
        ground_level_y = max([f['y'] for f in valid_feet])
        ball_height = ground_level_y - ball_bottom_y

        # --- JUGGLING (Dominadas) ---
        # Condición: Pelota en el aire Y Rebote detectado Y Pie cerca
        if ball_height > 20: # Está en el aire
            if is_bouncing_up: # ¡Detectamos el golpe físico!
                for foot in valid_feet:
                    # Distancia Horizontal: Pie vs Centro Pelota
                    dist_x = abs(foot['x'] - ball_center_x)
                    
                    # Distancia Vertical: Pie vs Fondo Pelota (Tu idea)
                    # El pie debe estar cerca del fondo de la pelota
                    dist_y = abs(foot['y'] - ball_bottom_y)

                    # Profundidad
                    try: foot_z = depth_map[foot['y'], foot['x']]
                    except: foot_z = 0
                    dist_z = abs(int(ball_z) - int(foot_z))

                    # UMBRALES PRECISOS
                    # X < 60: Pie alineado verticalmente
                    # Y < 50: Pie pegado al fondo de la pelota
                    # Z < 45: Profundidad correcta
                    if dist_x < 60 and dist_y < 50 and dist_z < 45:
                        if (frame_idx - self.last_hit_frame) > 10: # Debounce 10 frames
                            self.juggles_count += 1
                            self.last_hit_frame = frame_idx
                            event = "JUGGLE HIT (Bounce)!"
                            break # Solo contar una vez por frame

        # --- DRIBBLE (Conducción) ---
        elif ball_height <= 20:
            closest_dist = 999
            for foot in valid_feet:
                # Distancia euclidiana simple al pie en 2D
                d = np.sqrt((foot['x'] - ball_center_x)**2 + (foot['y'] - ball_bottom_y)**2)
                if d < closest_dist: closest_dist = d
            
            if closest_dist < 80:
                center_feet_x = (feet[0]['x'] + feet[1]['x']) / 2
                if ball_center_x > center_feet_x + 20: self.dribble_state = "Derecha >>"
                elif ball_center_x < center_feet_x - 20: self.dribble_state = "<< Izquierda"
                else: self.dribble_state = "Control"
                event = self.dribble_state

        return event

    def draw_3d_debug(self, frame, kpts, ball_box, depth_map):
        h, w = frame.shape[:2]
        panel = np.zeros((h, 320, 3), dtype=np.uint8) 
        panel[:] = (30, 30, 30)
        
        c_ball = (0, 140, 255) # Naranja
        c_foot = (0, 255, 0)   # Verde

        bx, by, bw, bh = ball_box[:4]
        # Usamos Bottom Y para la visualización lateral
        ball_cx = bx + bw//2
        ball_bottom_y = by + bh
        
        try: bz = int(depth_map[by+bh//2, bx+bw//2])
        except: bz = 128
        
        feet = [kpts[15], kpts[16]]
        
        # --- VISTA LATERAL (ZY) - CRÍTICA PARA JUGGLING ---
        # Muestra Altura (Y) vs Profundidad (Z)
        cv2.putText(panel, "PERFIL (Altura vs Prof.)", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)
        cv2.rectangle(panel, (20, 50), (300, 250), (20, 20, 20), -1)
        
        def map_side(pt_z, pt_y):
            mx = 20 + int((pt_z / 255.0) * 280)
            my = 50 + int((pt_y / h) * 200)
            return (mx, my)

        # Pelota (Usamos el borde inferior)
        bp_side = map_side(bz, ball_bottom_y)
        cv2.circle(panel, bp_side, 6, c_ball, -1)
        
        for f in feet:
            if f['conf'] > 0.5:
                try: fz = int(depth_map[f['y'], f['x']])
                except: fz = 128
                fp_side = map_side(fz, f['y'])
                cv2.circle(panel, fp_side, 5, c_foot, -1)
                # Línea de suelo referencial
                cv2.line(panel, (20, fp_side[1]), (300, fp_side[1]), (50,50,50), 1)

        # --- VISTA AÉREA (XZ) ---
        cv2.putText(panel, "PLANTA (Desde Arriba)", (10, 300), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)
        cv2.rectangle(panel, (20, 320), (300, 520), (20, 20, 20), -1)
        
        def map_top(pt_x, pt_z):
            mx = 20 + int((pt_x / w) * 280)
            my = 320 + int((pt_z / 255.0) * 200)
            return (mx, my)

        bp_top = map_top(ball_cx, bz)
        cv2.circle(panel, bp_top, 6, c_ball, -1)

        for f in feet:
            if f['conf'] > 0.5:
                try: fz = int(depth_map[f['y'], f['x']])
                except: fz = 128
                fp_top = map_top(f['x'], fz)
                cv2.circle(panel, fp_top, 5, c_foot, -1)
                cv2.line(panel, bp_top, fp_top, (80,80,80), 1)

        # Stats
        cv2.putText(panel, f"Juggles: {self.juggles_count}", (15, 560), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        vel_text = "Subiendo" if self.ball_velocity_y < 0 else "Bajando"
        cv2.putText(panel, f"Vel: {vel_text}", (15, 590), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (150, 150, 150), 1)

        return np.hstack((frame, panel))

    def run_on_video(self, video_path, frame_stride=3, max_frames=300, hit_threshold=0.4, return_images=True):
        cap = cv2.VideoCapture(video_path)
        fps_video = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration_s = total_frames / fps_video if fps_video > 0 else 0
        
        frame_idx = 0
        processed = 0
        images_output = []
        
        start_time = time.time()
        
        while processed < max_frames:
            ret, frame = cap.read()
            if not ret: break

            if frame_idx % frame_stride != 0:
                frame_idx += 1
                continue
            
            h, w = frame.shape[:2]
            
            # IA
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
                    event = self.analyze_football(ball, person['keypoints'], depth_map, frame_idx)
                    if return_images:
                        vis_frame = self.draw_3d_debug(vis_frame, person['keypoints'], ball, depth_map)
                
                if not return_images:
                     cv2.rectangle(vis_frame, (ball[0], ball[1]), (ball[0]+ball[2], ball[1]+ball[3]), (0,0,255), 2)

            if not return_images:
                cv2.putText(vis_frame, f"Count: {self.juggles_count}", (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)

            if return_images and len(images_output) < 60: 
                _, buf = cv2.imencode('.jpg', vis_frame)
                b64 = base64.b64encode(buf).decode('utf-8')
                images_output.append({
                    "image_id": str(frame_idx),
                    "image_base64": f"data:image/jpeg;base64,{b64}"
                })

            processed += 1
            frame_idx += 1

        cap.release()
        
        total_time = time.time() - start_time
        load_pct = (total_time / duration_s * 100) if duration_s > 0 else 0

        return {
            "id": int(time.time()),
            "hit_images": images_output,
            "meta": {
                "performance": {
                    "fps_analysis": round(processed/total_time, 2) if total_time > 0 else 0,
                    "total_processing_time_s": round(total_time, 2),
                    "video_duration_s": round(duration_s, 2),
                    "load_pct": round(load_pct, 2),
                    "frames_processed": processed
                },
                "stats": {
                    "total_juggles": self.juggles_count,
                    "final_state": self.dribble_state
                }
            }
        }