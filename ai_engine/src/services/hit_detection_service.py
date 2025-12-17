import cv2
import numpy as np
import os
import urllib.request
import time
import base64
from typing import Any, Dict, List

class YoloPoseWrapper:
    """
    Clase auxiliar para manejar YOLOv8-Pose en OpenCV puro.
    Detecta personas y sus esqueletos (17 Keypoints).
    """
    def __init__(self, model_path, confidence_thres=0.5, iou_thres=0.5):
        self.model_path = model_path
        self.conf_thres = confidence_thres
        self.iou_thres = iou_thres
        self.net = None
        self.input_width = 640
        self.input_height = 640
        
        # Mapa de Keypoints (Formato COCO)
        self.keypoints_map = {
            0: 'nose', 1: 'left_eye', 2: 'right_eye', 3: 'left_ear', 4: 'right_ear',
            5: 'left_shoulder', 6: 'right_shoulder', 7: 'left_elbow', 8: 'right_elbow',
            9: 'left_wrist', 10: 'right_wrist', 11: 'left_hip', 12: 'right_hip',
            13: 'left_knee', 14: 'right_knee', 15: 'left_ankle', 16: 'right_ankle'
        }

    def load_model(self):
        print(f"[Pose] Cargando YOLOv8-Pose: {self.model_path}")
        self.net = cv2.dnn.readNet(self.model_path)
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
        self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)

    def preprocess(self, img):
        self.img_h, self.img_w = img.shape[:2]
        # YOLOv8 espera RGB y 1/255.0
        blob = cv2.dnn.blobFromImage(img, 1/255.0, (self.input_width, self.input_height), swapRB=True, crop=False)
        return blob

    def postprocess(self, outputs):
        # La salida de YOLOv8-Pose es [Batch, 56, 8400]
        # 56 canales = 4 (box) + 1 (score) + 17*3 (keypoints x,y,conf)
        predictions = np.squeeze(outputs[0]).T
        
        # Filtrar por confianza
        scores = predictions[:, 4]
        keep_idxs = scores > self.conf_thres
        predictions = predictions[keep_idxs]
        scores = scores[keep_idxs]

        if len(scores) == 0: return []

        # Obtener Cajas
        boxes = predictions[:, :4]
        # Convertir cx,cy,w,h a x,y,w,h
        boxes_xywh = boxes.copy()
        boxes_xywh[:, 0] = boxes[:, 0] - boxes[:, 2] / 2
        boxes_xywh[:, 1] = boxes[:, 1] - boxes[:, 3] / 2
        
        # Obtener Keypoints (los canales del 5 en adelante)
        kpts = predictions[:, 5:]

        # NMS
        indices = cv2.dnn.NMSBoxes(boxes_xywh.tolist(), scores.tolist(), self.conf_thres, self.iou_thres)
        
        results = []
        scale_w = self.img_w / self.input_width
        scale_h = self.img_h / self.input_height

        for i in indices.flatten():
            # Escalar caja
            box = boxes_xywh[i]
            x = int(box[0] * scale_w)
            y = int(box[1] * scale_h)
            w = int(box[2] * scale_w)
            h = int(box[3] * scale_h)
            
            # Escalar Keypoints
            person_kpts = kpts[i].reshape(-1, 3) # [17, 3] -> x, y, conf
            kpts_scaled = []
            for kp in person_kpts:
                kx, ky, kconf = kp
                kpts_scaled.append({
                    "x": int(kx * scale_w),
                    "y": int(ky * scale_h),
                    "conf": float(kconf)
                })

            results.append({
                "class_id": 0, # Persona
                "confidence": float(scores[i]),
                "box": [x, y, w, h],
                "keypoints": kpts_scaled
            })
            
        return results

class HitDetectionService:
    def __init__(self, default_model_dirs: List[str] = None):
        # 1. Configuración DUAL: NanoDet (Pelota) + YOLO-Pose (Persona/Postura)
        self.ball_model_path = "/app/ai_engine/models/nanodet-plus-m_416.onnx"
        self.pose_model_path = "/app/ai_engine/models/yolov8n-pose.onnx"
        
        # URL oficial de Ultralytics para YOLOv8n-Pose ONNX
        self.pose_url = "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n-pose.onnx"
        # URL de NanoDet (tu mirror)
        self.ball_url = "https://github.com/RangiLyu/nanodet/releases/download/v1.0.0-alpha-1/nanodet-plus-m_416.onnx"

        self.nanodet_net = None
        self.pose_wrapper = None
        
        self._check_and_download_models()
        self._load_models()

    def _check_and_download_models(self):
        os.makedirs("/app/ai_engine/models", exist_ok=True)
        
        # Descargar YOLO Pose
        if not os.path.exists(self.pose_model_path):
            print("⏳ Descargando YOLOv8n-Pose...")
            urllib.request.urlretrieve(self.pose_url, self.pose_model_path)
            
        # Descargar NanoDet
        if not os.path.exists(self.ball_model_path):
            print("⏳ Descargando NanoDet...")
            opener = urllib.request.build_opener()
            opener.addheaders = [('User-Agent', 'Mozilla/5.0')]
            urllib.request.install_opener(opener)
            urllib.request.urlretrieve(self.ball_url, self.ball_model_path)

    def _load_models(self):
        # Cargar NanoDet (Para la pelota)
        self.nanodet_net = cv2.dnn.readNet(self.ball_model_path)
        self.nanodet_net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
        self.nanodet_net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
        
        # Cargar Pose (Para la persona)
        self.pose_wrapper = YoloPoseWrapper(self.pose_model_path)
        self.pose_wrapper.load_model()
        print("🚀 Modelos (Pelota + Postura) cargados en GPU.")

    def detect_ball_nanodet(self, frame):
        # Lógica simplificada de NanoDet solo para detectar objetos pequeños (pelotas)
        # Nota: NanoDet detecta 80 clases COCO. La pelota deportiva es clase 32.
        # Aquí asumimos que usas el NanoDet genérico.
        blob = cv2.dnn.blobFromImage(frame, 0.017429, (416,416), (103.53, 116.28, 123.675), False, False)
        self.nanodet_net.setInput(blob)
        outputs = self.nanodet_net.forward(self.nanodet_net.getUnconnectedOutLayersNames())
        
        # Postproceso rápido NanoDet (simplificado del código anterior)
        # ... (Tu lógica anterior de NanoDet va aquí, filtrando clase 32 'sports ball') ...
        # Para el ejemplo, retornaremos una lista vacía o simulada si no implementamos todo el decode aquí.
        # IMPLEMENTACIÓN RÁPIDA:
        preds = outputs[0][0]
        h, w = frame.shape[:2]
        scale_w, scale_h = w/416, h/416
        balls = []
        for det in preds:
            scores = det[4:]
            cls = np.argmax(scores)
            if cls == 32 and scores[cls] > 0.35: # 32 = Sports ball en COCO
                 cx, cy, bw, bh = det[:4]
                 balls.append([
                     int((cx - bw/2)*scale_w), int((cy - bh/2)*scale_h),
                     int(bw*scale_w), int(bh*scale_h)
                 ])
        return balls

    def analyze_hit(self, pose_results, ball_boxes):
        """
        El corazón de la lógica: Detecta QUÉ parte golpea.
        """
        hit_events = []
        
        if not ball_boxes or not pose_results:
            return hit_events

        # Tomamos la primera pelota encontrada (simplificación)
        bx, by, bw, bh = ball_boxes[0]
        ball_center = (bx + bw//2, by + bh//2)

        for person in pose_results:
            kpts = person['keypoints']
            
            # Índices COCO: 9=MuñecaIzq, 10=MuñecaDer, 15=TobilloIzq, 16=TobilloDer
            right_wrist = kpts[10]
            left_wrist = kpts[9]
            
            # Calcular distancias
            dist_r = np.linalg.norm(np.array([right_wrist['x'], right_wrist['y']]) - np.array(ball_center))
            dist_l = np.linalg.norm(np.array([left_wrist['x'], left_wrist['y']]) - np.array(ball_center))
            
            # Umbral de "toque" (en pixeles, depende de la resolución)
            HIT_THRESHOLD = 80 
            
            if dist_r < HIT_THRESHOLD and right_wrist['conf'] > 0.5:
                hit_events.append("Golpe Mano Derecha")
            elif dist_l < HIT_THRESHOLD and left_wrist['conf'] > 0.5:
                hit_events.append("Golpe Mano Izquierda")
                
        return hit_events

    def draw_skeleton(self, frame, kpts):
        # Dibujar esqueleto básico
        skeleton = [
            (5,7), (7,9), (6,8), (8,10), # Brazos
            (11,13), (13,15), (12,14), (14,16), # Piernas
            (5,6), (11,12), (5,11), (6,12) # Torso
        ]
        for p1, p2 in skeleton:
            if kpts[p1]['conf'] > 0.5 and kpts[p2]['conf'] > 0.5:
                pt1 = (kpts[p1]['x'], kpts[p1]['y'])
                pt2 = (kpts[p2]['x'], kpts[p2]['y'])
                cv2.line(frame, pt1, pt2, (0, 255, 255), 2)
        return frame

    def run_on_video(self, video_path, frame_stride=3, max_frames=300, hit_threshold=0.4, return_images=False):
        cap = cv2.VideoCapture(video_path)
        frame_idx = 0
        processed = 0
        hits_detected = 0
        logs = []
        images_b64 = []

        start_time = time.time()

        while processed < max_frames:
            ret, frame = cap.read()
            if not ret: break

            if frame_idx % frame_stride != 0:
                frame_idx += 1
                continue

            # 1. Detectar Postura (YOLO)
            pose_blob = self.pose_wrapper.preprocess(frame)
            self.pose_wrapper.net.setInput(pose_blob)
            pose_out = self.pose_wrapper.net.forward()
            people = self.pose_wrapper.postprocess(pose_out)

            # 2. Detectar Pelota (NanoDet)
            balls = self.detect_ball_nanodet(frame)

            # 3. Analizar Lógica de Golpe
            events = self.analyze_hit(people, balls)
            
            is_hit = len(events) > 0
            if is_hit: hits_detected += 1

            # Generar visualización
            if return_images and is_hit:
                vis_frame = frame.copy()
                # Dibujar esqueleto
                for p in people:
                    vis_frame = self.draw_skeleton(vis_frame, p['keypoints'])
                # Dibujar pelota
                for b in balls:
                    cv2.rectangle(vis_frame, (b[0], b[1]), (b[0]+b[2], b[1]+b[3]), (0,0,255), 2)
                
                # Texto del evento
                cv2.putText(vis_frame, f"HIT: {events[0]}", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

                _, buffer = cv2.imencode('.jpg', vis_frame)
                img_b64 = base64.b64encode(buffer).decode('utf-8')
                images_b64.append({"frame": frame_idx, "event": events[0], "image": img_b64})

            processed += 1
            frame_idx += 1

        cap.release()
        total_time = time.time() - start_time
        
        return {
            "hits_detected": hits_detected,
            "performance": {"fps": round(processed/total_time, 2), "total_time": total_time},
            "hit_images": images_b64
        }