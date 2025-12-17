import cv2
import numpy as np
import os
import urllib.request
import time
import base64
from typing import Any, Dict, List

# --- CLASE BASE YOLOV8 (Compartida) ---
class YoloBaseWrapper:
    def __init__(self, model_path, conf_thres=0.4, iou_thres=0.5):
        self.model_path = model_path
        self.conf_thres = conf_thres
        self.iou_thres = iou_thres
        self.net = None
        self.input_size = (640, 640)

    def load_model(self, name="YOLO"):
        print(f"[{name}] 📂 Cargando modelo: {os.path.basename(self.model_path)}...")
        if not os.path.exists(self.model_path) or os.path.getsize(self.model_path) < 1000:
            print(f"[{name}] ❌ Archivo no encontrado o corrupto: {self.model_path}")
            return False

        try:
            self.net = cv2.dnn.readNet(self.model_path)
            self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
            self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
            
            # Warmup
            dummy = np.zeros((1, 3, 640, 640), dtype=np.float32)
            self.net.setInput(dummy)
            self.net.forward()
            print(f"[{name}] ✅ Modelo cargado en GPU.")
            return True
        except Exception as e:
            print(f"[{name}] ❌ Error crítico cargando modelo: {e}")
            self.net = None
            return False

    def preprocess(self, img):
        return cv2.dnn.blobFromImage(img, 1/255.0, self.input_size, swapRB=True, crop=False)

# --- WRAPPER DETECCIÓN (Pelota) ---
class YoloDetWrapper(YoloBaseWrapper):
    def detect_ball(self, blob, img_w, img_h):
        if self.net is None: return []

        self.net.setInput(blob)
        outputs = self.net.forward()
        
        preds = np.squeeze(outputs[0]).T
        
        if preds.shape[1] > 36: 
            # Clase 32 = Sports Ball
            ball_scores = preds[:, 32+4] 
            keep_idxs = ball_scores > self.conf_thres
            preds = preds[keep_idxs]
            scores = ball_scores[keep_idxs]
        else:
            return []
        
        if len(scores) == 0: return []

        boxes = preds[:, :4]
        boxes_xywh = boxes.copy()
        boxes_xywh[:, 0] = boxes[:, 0] - boxes[:, 2] / 2
        boxes_xywh[:, 1] = boxes[:, 1] - boxes[:, 3] / 2
        
        indices = cv2.dnn.NMSBoxes(boxes_xywh.tolist(), scores.tolist(), self.conf_thres, self.iou_thres)
        
        balls = []
        scale_w = img_w / self.input_size[0]
        scale_h = img_h / self.input_size[1]

        for i in indices.flatten():
            box = boxes_xywh[i]
            x = int(box[0] * scale_w)
            y = int(box[1] * scale_h)
            w = int(box[2] * scale_w)
            h = int(box[3] * scale_h)
            balls.append([x, y, w, h, float(scores[i])])
            
        return balls

# --- WRAPPER POSE (Persona) ---
class YoloPoseWrapper(YoloBaseWrapper):
    def detect_pose(self, blob, img_w, img_h):
        if self.net is None: return []

        self.net.setInput(blob)
        outputs = self.net.forward()
        
        preds = np.squeeze(outputs[0]).T
        scores = preds[:, 4]
        keep_idxs = scores > self.conf_thres
        preds = preds[keep_idxs]
        scores = scores[keep_idxs]

        if len(scores) == 0: return []

        boxes = preds[:, :4]
        boxes_xywh = boxes.copy()
        boxes_xywh[:, 0] = boxes[:, 0] - boxes[:, 2] / 2
        boxes_xywh[:, 1] = boxes[:, 1] - boxes[:, 3] / 2
        
        kpts = preds[:, 5:]
        indices = cv2.dnn.NMSBoxes(boxes_xywh.tolist(), scores.tolist(), self.conf_thres, self.iou_thres)
        
        people = []
        scale_w = img_w / self.input_size[0]
        scale_h = img_h / self.input_size[1]

        for i in indices.flatten():
            person_kpts = kpts[i].reshape(-1, 3)
            kpts_scaled = []
            for kp in person_kpts:
                kx, ky, kconf = kp
                kpts_scaled.append({
                    "x": int(kx * scale_w),
                    "y": int(ky * scale_h),
                    "conf": float(kconf)
                })
            people.append({"keypoints": kpts_scaled})
        return people

# --- SERVICIO PRINCIPAL (FÚTBOL) ---
class HitDetectionService:
    def __init__(self, default_model_dirs: List[str] = None):
        self.models_dir = "/app/ai_engine/models"
        self.det_path = os.path.join(self.models_dir, "yolov8n.onnx")       
        self.pose_path = os.path.join(self.models_dir, "yolov8n-pose.onnx")  
        self.midas_path = os.path.join(self.models_dir, "midas_v21_small.onnx") 

        # --- URLs NUEVAS (HuggingFace Mirrors - Mucho más estables) ---
        self.det_url = "https://github.com/pellit/video-analytics-saas/raw/796d243e692b5b18f0344b033a152dcdd6326f36/ai_engine/yolov8n.onnx"
        self.pose_url = "https://huggingface.co/Xenova/yolov8-pose-onnx/resolve/main/yolov8n-pose.onnx?download=true"
        # MiDaS suele ser estable en Github
        self.midas_url = "https://github.com/isl-org/MiDaS/releases/download/v2_1/model-small.onnx"

        print(f"\n[DEBUG] Iniciando Servicio de Fútbol (YOLOv8n + Pose + MiDaS)...")
        
        self._check_and_download_models()

        # Cargar Modelos
        self.det_model = YoloDetWrapper(self.det_path, conf_thres=0.30)
        self.det_model.load_model("YOLO-BALL")
        
        self.pose_model = YoloPoseWrapper(self.pose_path, conf_thres=0.5)
        self.pose_model.load_model("YOLO-POSE")
        
        self.midas_net = None
        if os.path.exists(self.midas_path):
            try:
                self.midas_net = cv2.dnn.readNet(self.midas_path)
                self.midas_net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
                self.midas_net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
                print("[MiDaS] ✅ Cargado.")
            except Exception as e:
                print(f"[MiDaS] ❌ Error cargando: {e}")

    def _download_file(self, url, path):
        if os.path.exists(path) and os.path.getsize(path) > 100000:
            return 
        print(f"⏳ Descargando {os.path.basename(path)}...")
        try:
            opener = urllib.request.build_opener()
            opener.addheaders = [('User-Agent', 'Mozilla/5.0')]
            urllib.request.install_opener(opener)
            urllib.request.urlretrieve(url, path)
            print("✅ Descarga OK.")
        except Exception as e:
            print(f"❌ Error descargando {url}: {e}")

    def _check_and_download_models(self):
        os.makedirs(self.models_dir, exist_ok=True)
        self._download_file(self.det_url, self.det_path)
        self._download_file(self.pose_url, self.pose_path)
        self._download_file(self.midas_url, self.midas_path)

    def get_depth_map(self, frame):
        if self.midas_net is None: return None
        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(frame, 1/255.0, (256, 256), (123.675, 116.28, 103.53), True, False)
        self.midas_net.setInput(blob)
        depth = self.midas_net.forward()
        depth = depth[0,0]
        depth = cv2.resize(depth, (w, h))
        return cv2.normalize(depth, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)

    def analyze_soccer_scene(self, balls, people, depth_map):
        """
        Lógica de Fútbol: Pies (OK), Manos (Falta), Control (Proximidad).
        """
        events = []
        if not balls or not people or depth_map is None: return events

        # Pelota principal
        balls.sort(key=lambda x: x[4], reverse=True)
        bx, by, bw, bh, _ = balls[0]
        ball_center = (bx + bw//2, by + bh//2)
        
        try: ball_z = depth_map[ball_center[1], ball_center[0]]
        except: return events

        for p in people:
            kpts = p['keypoints']
            
            # --- ZONA DE IMPACTO (Pies y Rodillas) ---
            # 15: Tobillo Izq, 16: Tobillo Der
            # 13: Rodilla Izq, 14: Rodilla Der
            impact_points = [
                ("Pie Izq", kpts[15]), ("Pie Der", kpts[16]),
                ("Rodilla Izq", kpts[13]), ("Rodilla Der", kpts[14])
            ]

            # --- ZONA PROHIBIDA (Manos) ---
            # 9: Muñeca Izq, 10: Muñeca Der
            hands = [("MANO Izq", kpts[9]), ("MANO Der", kpts[10])]

            # 1. Chequear PIES (Toque/Control)
            for part_name, kp in impact_points:
                if kp['conf'] < 0.5: continue
                
                dist_2d = np.linalg.norm(np.array([kp['x'], kp['y']]) - np.array(ball_center))
                try: 
                    kp_z = depth_map[kp['y'], kp['x']]
                    dist_z = abs(int(ball_z) - int(kp_z))
                except: continue

                # Umbrales
                if dist_2d < 80 and dist_z < 40:
                    events.append(f"Toque {part_name}")
                elif dist_2d < 150 and dist_z < 50:
                    events.append(f"Control {part_name} (Cerca)")

            # 2. Chequear MANOS (Faltas)
            for part_name, kp in hands:
                if kp['conf'] < 0.5: continue
                dist_2d = np.linalg.norm(np.array([kp['x'], kp['y']]) - np.array(ball_center))
                try: 
                    kp_z = depth_map[kp['y'], kp['x']]
                    dist_z = abs(int(ball_z) - int(kp_z))
                except: continue

                if dist_2d < 90 and dist_z < 40:
                    events.append(f"⚠️ {part_name} (FALTA)")

        return events

    def run_on_video(self, video_path, frame_stride=3, max_frames=200, hit_threshold=0.4, return_images=True):
        cap = cv2.VideoCapture(video_path)
        
        # Stats Video
        fps_video = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        video_duration_s = total_frames / fps_video if fps_video > 0 else 0
            
        frame_idx = 0
        processed = 0
        images_b64 = []
        debug_logs = []
        
        start_time = time.time()
        
        while processed < max_frames:
            ret, frame = cap.read()
            if not ret: break

            if frame_idx % frame_stride != 0:
                frame_idx += 1
                continue
            
            h, w = frame.shape[:2]

            # 1. Detección (Blob compartido)
            shared_blob = self.det_model.preprocess(frame)
            balls = self.det_model.detect_ball(shared_blob, w, h)
            people = self.pose_model.detect_pose(shared_blob, w, h)
            
            # 2. Análisis Lógico
            events = []
            depth_map = None
            if len(balls) > 0 and len(people) > 0:
                depth_map = self.get_depth_map(frame)
                events = self.analyze_soccer_scene(balls, people, depth_map)

            # Detectamos "Acción" si hay eventos (Toque, Control o Mano)
            action_detected = len(events) > 0
            
            debug_logs.append({
                "frame": frame_idx,
                "balls": len(balls),
                "people": len(people),
                "action": action_detected,
                "events": events
            })

            # Generar imagen si hay acción o para muestreo
            if return_images and (action_detected or len(images_b64) < 5):
                vis = frame.copy()
                
                # Pelota
                for b in balls:
                    cv2.rectangle(vis, (b[0], b[1]), (b[0]+b[2], b[1]+b[3]), (0,0,255), 2)
                    # cv2.putText(vis, "Ball", (b[0], b[1]-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,255), 1)

                # Esqueleto Fútbol
                for p in people:
                    kpts = p['keypoints']
                    # Pies (15, 16) - Verde
                    for idx in [15, 16]: 
                        kp = kpts[idx]
                        if kp['conf']>0.5: cv2.circle(vis, (kp['x'], kp['y']), 6, (0,255,0), -1)
                    # Manos (9, 10) - Rojo (Alerta)
                    for idx in [9, 10]: 
                        kp = kpts[idx]
                        if kp['conf']>0.5: cv2.circle(vis, (kp['x'], kp['y']), 5, (0,0,255), 2)

                if action_detected:
                    # Texto del evento
                    color = (0, 255, 0) # Verde por defecto
                    if "FALTA" in events[0]: color = (0, 0, 255) # Rojo si es mano
                    elif "Control" in events[0]: color = (0, 255, 255) # Amarillo si es control
                    
                    cv2.putText(vis, events[0], (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

                _, buf = cv2.imencode('.jpg', vis)
                b64 = base64.b64encode(buf).decode('utf-8')
                images_b64.append({"frame": frame_idx, "image": b64})

            processed += 1
            frame_idx += 1

        cap.release()
        
        end_time = time.time()
        total_time = end_time - start_time
        load_pct = (total_time / video_duration_s) * 100 if video_duration_s > 0 else 0

        return {
            "success": True,
            "performance": {
                "fps_analysis": round(processed/total_time, 2) if total_time > 0 else 0,
                "total_time_s": round(total_time, 2),
                "load_pct": round(load_pct, 2)
            },
            "actions_detected": sum(1 for l in debug_logs if l['action']),
            "events_log": [l for l in debug_logs if l['action']], # Solo frames con acción
            "hit_images": images_b64
        }