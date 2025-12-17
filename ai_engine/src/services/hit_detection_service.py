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
        
        # Validación de archivo
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
        
        # [1, 84, 8400]
        preds = np.squeeze(outputs[0]).T
        
        # Validación de dimensiones
        if preds.shape[1] > 36: 
            # Clase 32 = Sports Ball (Score en índice 32+4)
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

# --- SERVICIO PRINCIPAL ---
class HitDetectionService:
    def __init__(self, default_model_dirs: List[str] = None):
        self.models_dir = "/app/ai_engine/models"
        
        # Rutas locales
        self.det_path = os.path.join(self.models_dir, "yolov8n.onnx")       
        self.pose_path = os.path.join(self.models_dir, "yolov8n-pose.onnx")  
        self.midas_path = os.path.join(self.models_dir, "midas_v21_small.onnx") 

        # --- URLs NUEVAS (HuggingFace Mirrors - Mucho más estables) ---
        self.det_url = "https://github.com/pellit/video-analytics-saas/raw/796d243e692b5b18f0344b033a152dcdd6326f36/ai_engine/yolov8n.onnx"
        self.pose_url = "https://huggingface.co/Xenova/yolov8-pose-onnx/resolve/main/yolov8n-pose.onnx?download=true"
        # MiDaS suele ser estable en Github
        self.midas_url = "https://github.com/isl-org/MiDaS/releases/download/v2_1/model-small.onnx"

        print(f"\n[DEBUG] Iniciando HitDetectionService (Mirrors HF)...")
        
        # 1. Descargar
        self._check_and_download_models()

        # 2. Cargar Modelos
        self.det_model = YoloDetWrapper(self.det_path, conf_thres=0.30)
        self.det_model.load_model("YOLO-BALL")
        
        self.pose_model = YoloPoseWrapper(self.pose_path, conf_thres=0.5)
        self.pose_model.load_model("YOLO-POSE")
        
        self.midas_net = None
        if os.path.exists(self.midas_path):
            try:
                print(f"[MiDaS] Cargando {os.path.basename(self.midas_path)}...")
                self.midas_net = cv2.dnn.readNet(self.midas_path)
                self.midas_net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
                self.midas_net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
                print("[MiDaS] ✅ Cargado en GPU.")
            except Exception as e:
                print(f"[MiDaS] ❌ Error cargando: {e}")

    def _download_file(self, url, path):
        """Función unificada para descargar archivos"""
        # Si existe y tiene tamaño lógico (>100KB), asumimos que está bien
        if os.path.exists(path) and os.path.getsize(path) > 100000:
            return 
            
        print(f"⏳ Descargando {os.path.basename(path)} desde espejo...")
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

    def analyze_scene(self, balls, people, depth_map):
        events = []
        if not balls or not people or depth_map is None: return events

        # Pelota más probable
        balls.sort(key=lambda x: x[4], reverse=True)
        bx, by, bw, bh, _ = balls[0]
        ball_center = (bx + bw//2, by + bh//2)
        
        try: ball_z = depth_map[ball_center[1], ball_center[0]]
        except: return events

        for p in people:
            kpts = p['keypoints']
            # 9: Wrist L, 10: Wrist R
            wrists = [("Izquierda", kpts[9]), ("Derecha", kpts[10])]

            for side, w in wrists:
                if w['conf'] < 0.5: continue
                
                dist_2d = np.linalg.norm(np.array([w['x'], w['y']]) - np.array(ball_center))
                try: 
                    wrist_z = depth_map[w['y'], w['x']]
                    dist_z = abs(int(ball_z) - int(wrist_z))
                except: continue

                # LÓGICA DE GOLPE
                if dist_2d < 120 and dist_z < 40:
                    events.append(f"Golpe Mano {side}")

        return events

    def run_on_video(self, video_path, frame_stride=3, max_frames=200, hit_threshold=0.4, return_images=True):
        cap = cv2.VideoCapture(video_path)
        
        # --- NUEVO: Obtener duración del video para el cálculo de porcentaje ---
        fps_video = cap.get(cv2.CAP_PROP_FPS)
        total_frames_video = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if fps_video > 0:
            video_duration_s = total_frames_video / fps_video
        else:
            video_duration_s = 0
            
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

            # 1. BLOB compartido
            shared_blob = self.det_model.preprocess(frame)
            
            # 2. Inferencia (Con protección si los modelos no cargaron)
            balls = self.det_model.detect_ball(shared_blob, w, h)
            people = self.pose_model.detect_pose(shared_blob, w, h)
            
            events = []
            if len(balls) > 0 and len(people) > 0:
                depth_map = self.get_depth_map(frame)
                events = self.analyze_scene(balls, people, depth_map)

            # Debug logs
            hit_found = len(events) > 0
            debug_logs.append({
                "frame": frame_idx,
                "balls": len(balls),
                "people": len(people),
                "hit": hit_found,
                "events": events
            })

            # Generar imagen si se pide
            if return_images and (hit_found or len(images_b64) < 5):
                vis = frame.copy()
                for b in balls:
                    cv2.rectangle(vis, (b[0], b[1]), (b[0]+b[2], b[1]+b[3]), (0,0,255), 2)
                for p in people:
                    kpts = p['keypoints']
                    rw, lw = kpts[10], kpts[9]
                    if rw['conf']>0.5: cv2.circle(vis, (rw['x'], rw['y']), 5, (0,255,0), -1)
                    if lw['conf']>0.5: cv2.circle(vis, (lw['x'], lw['y']), 5, (0,255,0), -1)
                
                if hit_found:
                    cv2.putText(vis, events[0], (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2)

                _, buf = cv2.imencode('.jpg', vis)
                b64 = base64.b64encode(buf).decode('utf-8')
                images_b64.append({"frame": frame_idx, "image": b64})

            processed += 1
            frame_idx += 1

        cap.release()
        
        # --- CÁLCULOS FINALES ---
        end_time = time.time()
        total_processing_time = end_time - start_time
        
        # Calculo del porcentaje solicitado
        # (Tiempo Proceso / Duración Video) * 100
        # Ejemplo: Video 10s, Proceso 60s -> 600%
        processing_load_percent = 0
        if video_duration_s > 0:
            processing_load_percent = (total_processing_time / video_duration_s) * 100

        return {
            "success": True,
            "performance": {
                "fps_analysis": round(processed/total_processing_time, 2) if total_processing_time > 0 else 0,
                "total_processing_time_s": round(total_processing_time, 2),
                "video_duration_s": round(video_duration_s, 2),
                "processing_load_percent": round(processing_load_percent, 2) # <--- TU NUEVO PARAMETRO
            },
            "hits_detected": sum(1 for l in debug_logs if l['hit']),
            "hit_images": images_b64,
            "logs": debug_logs[:20]
        }