import cv2
import numpy as np
import os
import urllib.request
import time
import base64
from typing import Any, Dict, List

# --- CLASE BASE PARA YOLOV8 (Compartida para optimizar) ---
class YoloBaseWrapper:
    def __init__(self, model_path, conf_thres=0.4, iou_thres=0.5):
        self.model_path = model_path
        self.conf_thres = conf_thres
        self.iou_thres = iou_thres
        self.net = None
        self.input_size = (640, 640) # YOLOv8 estándar

    def load_model(self, name="YOLO"):
        print(f"[{name}] Cargando modelo: {os.path.basename(self.model_path)}...")
        try:
            self.net = cv2.dnn.readNet(self.model_path)
            self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
            self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
            # Warmup
            dummy = np.zeros((1, 3, 640, 640), dtype=np.float32)
            self.net.setInput(dummy)
            self.net.forward()
            print(f"[{name}] ✅ Modelo cargado en GPU.")
        except Exception as e:
            print(f"[{name}] ❌ Error fatal: {e}")

    def preprocess(self, img):
        # YOLOv8: RGB, 1/255.0, 640x640, Centrado
        return cv2.dnn.blobFromImage(img, 1/255.0, self.input_size, swapRB=True, crop=False)

# --- WRAPPER DETECCIÓN (Solo para la Pelota) ---
class YoloDetWrapper(YoloBaseWrapper):
    def detect_ball(self, blob, img_w, img_h):
        self.net.setInput(blob)
        outputs = self.net.forward()
        
        # Salida: [1, 84, 8400] -> (cx,cy,w,h + 80 clases)
        preds = np.squeeze(outputs[0]).T
        
        # Clase 32 es "sports ball" en COCO
        # Filtramos solo detecciones con alta confianza en clase 32
        ball_scores = preds[:, 32+4] # +4 porque los primeros 4 son bbox
        keep_idxs = ball_scores > self.conf_thres
        
        preds = preds[keep_idxs]
        scores = ball_scores[keep_idxs]
        
        if len(scores) == 0: return []

        # Cajas
        boxes = preds[:, :4]
        # xywh -> xyxy para NMS
        boxes_xywh = boxes.copy()
        boxes_xywh[:, 0] = boxes[:, 0] - boxes[:, 2] / 2 # x
        boxes_xywh[:, 1] = boxes[:, 1] - boxes[:, 3] / 2 # y
        
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

# --- WRAPPER POSE (Para la Persona) ---
class YoloPoseWrapper(YoloBaseWrapper):
    def detect_pose(self, blob, img_w, img_h):
        self.net.setInput(blob)
        outputs = self.net.forward()
        
        # Salida: [1, 56, 8400]
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
        self.det_path = os.path.join(self.models_dir, "yolov8n.onnx")       # Detección (Pelota)
        self.pose_path = os.path.join(self.models_dir, "yolov8n-pose.onnx")  # Pose (Persona)
        self.midas_path = os.path.join(self.models_dir, "midas_v21_small.onnx") # Profundidad

        print(f"\n[DEBUG SISTEMA] Iniciando servicio con YOLOv8 (Pelota) + YOLOv8-Pose (Persona)...")
        self._check_and_download_models()

        # Inicializar Modelos
        self.det_model = YoloDetWrapper(self.det_path, conf_thres=0.35) # Umbral bajo para pelota
        self.det_model.load_model("YOLO-BALL")
        
        self.pose_model = YoloPoseWrapper(self.pose_path, conf_thres=0.5)
        self.pose_model.load_model("YOLO-POSE")
        
        print("[MiDaS] Cargando modelo de profundidad...")
        self.midas_net = cv2.dnn.readNet(self.midas_path)
        self.midas_net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
        self.midas_net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)

    def _check_and_download_models(self):
        os.makedirs(self.models_dir, exist_ok=True)
        # 1. YOLOv8n (Detection) - Fuente Oficial
        if not os.path.exists(self.det_path):
            self._download_file("https://huggingface.co/SpotLab/YOLOv8Detection/resolve/3005c6751fb19cdeb6b10c066185908faf66a097/yolov8n.onnx?download=true", self.yolov8_path)
        
        # 2. YOLOv8n-Pose - Fuente Oficial
        if not os.path.exists(self.pose_path):
            self._download_file("https://huggingface.co/Xenova/yolov8-pose-onnx/resolve/main/yolov8n-pose.onnx?download=true", self.pose_path)
            
        # 3. MiDaS
        if not os.path.exists(self.midas_path):
            self._download_file("https://github.com/isl-org/MiDaS/releases/download/v2_1/model-small.onnx", self.midas_path)

    def _download(self, url, path):
        print(f"⏳ Descargando {os.path.basename(path)}...")
        try:
            opener = urllib.request.build_opener()
            opener.addheaders = [('User-Agent', 'Mozilla/5.0')]
            urllib.request.install_opener(opener)
            urllib.request.urlretrieve(url, path)
            print("✅ OK.")
        except Exception as e:
            print(f"❌ Error descarga: {e}")

    def get_depth_map(self, frame):
        # MiDaS v2.1 Small requiere 256x256
        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(frame, 1/255.0, (256, 256), (123.675, 116.28, 103.53), True, False)
        self.midas_net.setInput(blob)
        depth = self.midas_net.forward()
        depth = depth[0,0]
        depth = cv2.resize(depth, (w, h))
        return cv2.normalize(depth, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)

    def analyze_scene(self, balls, people, depth_map):
        """
        Lógica:
        1. Tomar la pelota.
        2. Comparar distancia con muñecas (Wrists).
        3. Comparar profundidad (Z).
        """
        events = []
        if not balls or not people or depth_map is None:
            return events

        # Tomamos la pelota con mayor confianza
        balls.sort(key=lambda x: x[4], reverse=True)
        bx, by, bw, bh, bconf = balls[0]
        ball_center = (bx + bw//2, by + bh//2)
        
        # Profundidad de la pelota
        try: ball_z = depth_map[ball_center[1], ball_center[0]]
        except: return events

        for p in people:
            kpts = p['keypoints']
            # 9: Left Wrist, 10: Right Wrist
            wrists = [("Izquierda", kpts[9]), ("Derecha", kpts[10])]

            for side, w in wrists:
                if w['conf'] < 0.5: continue
                
                # Distancia 2D (Pixeles)
                dist_2d = np.linalg.norm(np.array([w['x'], w['y']]) - np.array(ball_center))
                
                # Distancia Z (Profundidad 0-255)
                try: 
                    wrist_z = depth_map[w['y'], w['x']]
                    dist_z = abs(int(ball_z) - int(wrist_z))
                except: continue

                # UMBRALES DE GOLPE
                # 2D: < 120px (aumentado porque YOLO es preciso)
                # Z: < 40 unidades (cercanía en profundidad)
                if dist_2d < 120 and dist_z < 40:
                    events.append(f"Golpe Mano {side} (D2D:{dist_2d:.0f}, DZ:{dist_z})")

        return events

    def run_on_video(self, video_path, frame_stride=3, max_frames=200, hit_threshold=0.4, return_images=True):
        cap = cv2.VideoCapture(video_path)
        frame_idx = 0
        processed = 0
        images_b64 = []
        debug_logs = []
        
        start_time = time.time()
        
        # Buffer de blobs para optimización (opcional, aquí lo hacemos secuencial por seguridad)
        
        while processed < max_frames:
            ret, frame = cap.read()
            if not ret: break

            if frame_idx % frame_stride != 0:
                frame_idx += 1
                continue
            
            h, w = frame.shape[:2]

            # 1. Preparar BLOB compartido (YOLO usa el mismo preproceso para Det y Pose)
            # Esto ahorra tiempo de CPU
            shared_blob = self.det_model.preprocess(frame)
            
            # 2. Detectar Pelota
            balls = self.det_model.detect_ball(shared_blob, w, h)
            
            # 3. Detectar Personas (Usamos el mismo blob!)
            people = self.pose_model.detect_pose(shared_blob, w, h)
            
            # 4. Profundidad (Solo si hay pelota y persona, es muy pesado)
            depth_map = None
            events = []
            
            if len(balls) > 0 and len(people) > 0:
                depth_map = self.get_depth_map(frame)
                events = self.analyze_scene(balls, people, depth_map)

            # --- VISUALIZACIÓN / DEBUG ---
            frame_log = {
                "frame": frame_idx,
                "balls": len(balls),
                "people": len(people),
                "hit": len(events) > 0,
                "events": events
            }
            debug_logs.append(frame_log)

            # Generar imagen si se pide O si hay HIT (para ver el resultado)
            if return_images or len(events) > 0:
                vis = frame.copy()
                
                # Dibujar pelotas
                for b in balls:
                    cv2.rectangle(vis, (b[0], b[1]), (b[0]+b[2], b[1]+b[3]), (0,0,255), 2)
                    cv2.putText(vis, f"Ball {b[4]:.2f}", (b[0], b[1]-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,255), 1)

                # Dibujar esqueleto (básico)
                for p in people:
                    kpts = p['keypoints']
                    # Línea Muñeca-Codo-Hombro
                    arm_l = [9, 7, 5]
                    arm_r = [10, 8, 6]
                    for arm in [arm_l, arm_r]:
                        for i in range(len(arm)-1):
                            kp1, kp2 = kpts[arm[i]], kpts[arm[i+1]]
                            if kp1['conf']>0.5 and kp2['conf']>0.5:
                                cv2.line(vis, (kp1['x'], kp1['y']), (kp2['x'], kp2['y']), (0,255,0), 2)
                    # Marcar muñecas
                    rw, lw = kpts[10], kpts[9]
                    if rw['conf']>0.5: cv2.circle(vis, (rw['x'], rw['y']), 5, (255,255,0), -1)
                    if lw['conf']>0.5: cv2.circle(vis, (lw['x'], lw['y']), 5, (255,255,0), -1)

                # Si hay HIT, escribirlo grande
                if len(events) > 0:
                    cv2.putText(vis, events[0], (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 3)

                # Guardar imagen (limitado a 30 frames de muestra para no saturar respuesta)
                if len(images_b64) < 30 or len(events) > 0:
                    _, buf = cv2.imencode('.jpg', vis)
                    b64 = base64.b64encode(buf).decode('utf-8')
                    images_b64.append({"frame": frame_idx, "hit": len(events)>0, "image": b64})

            processed += 1
            frame_idx += 1

        cap.release()
        total_time = time.time() - start_time
        
        return {
            "success": True,
            "performance": {
                "fps": round(processed/total_time, 2),
                "total_time": total_time
            },
            "hits_detected": sum(1 for l in debug_logs if l['hit']),
            "logs": debug_logs, # Resumen
            "hit_images": images_b64
        }