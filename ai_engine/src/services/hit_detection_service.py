import cv2
import numpy as np
import os
import urllib.request
import time
import base64
from typing import Any, Dict, List

# --- WRAPPER POSE (Igual que antes) ---
class YoloPoseWrapper:
    def __init__(self, model_path, confidence_thres=0.5):
        self.model_path = model_path
        self.conf_thres = confidence_thres
        self.net = None
        self.input_width = 640
        self.input_height = 640

    def load_model(self):
        print(f"[Pose] Cargando YOLOv8-Pose...")
        try:
            self.net = cv2.dnn.readNet(self.model_path)
            self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
            self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
        except Exception as e:
            print(f"[Pose] Error fatal: {e}")

    def preprocess(self, img):
        self.img_h, self.img_w = img.shape[:2]
        blob = cv2.dnn.blobFromImage(img, 1/255.0, (self.input_width, self.input_height), swapRB=True, crop=False)
        return blob

    def postprocess(self, outputs):
        predictions = np.squeeze(outputs[0]).T
        scores = predictions[:, 4]
        keep_idxs = scores > self.conf_thres
        predictions = predictions[keep_idxs]
        scores = scores[keep_idxs]

        if len(scores) == 0: return []

        boxes = predictions[:, :4]
        # xywh a xyxy para nms
        boxes_xywh = boxes.copy()
        boxes_xywh[:, 0] = boxes[:, 0] - boxes[:, 2] / 2
        boxes_xywh[:, 1] = boxes[:, 1] - boxes[:, 3] / 2
        
        kpts = predictions[:, 5:]
        indices = cv2.dnn.NMSBoxes(boxes_xywh.tolist(), scores.tolist(), self.conf_thres, 0.5)
        
        results = []
        scale_w = self.img_w / self.input_width
        scale_h = self.img_h / self.input_height

        for i in indices.flatten():
            box = boxes_xywh[i]
            x = int(box[0] * scale_w)
            y = int(box[1] * scale_h)
            w = int(box[2] * scale_w)
            h = int(box[3] * scale_h)
            
            person_kpts = kpts[i].reshape(-1, 3)
            kpts_scaled = []
            for kp in person_kpts:
                kx, ky, kconf = kp
                kpts_scaled.append({
                    "x": int(kx * scale_w),
                    "y": int(ky * scale_h),
                    "conf": float(kconf)
                })

            results.append({
                "box": [x, y, w, h],
                "keypoints": kpts_scaled
            })
        return results

# --- SERVICIO DE DETECCIÓN CON DEBUG ---
class HitDetectionService:
    def __init__(self, default_model_dirs: List[str] = None):
        self.models_dir = "/app/ai_engine/models"
        self.nanodet_path = os.path.join(self.models_dir, "nanodet-plus-m_416.onnx")
        self.pose_path = os.path.join(self.models_dir, "yolov8n-pose.onnx")
        self.midas_path = os.path.join(self.models_dir, "midas_v21_small.onnx")
        self.yolov8_path = os.path.join(self.models_dir, "yolov8n.onnx")

        # 1. VERIFICACIÓN DE CUDA AL INICIO
        cuda_count = cv2.cuda.getCudaEnabledDeviceCount()
        print(f"\n[DEBUG SISTEMA] --------------------------------------")
        print(f"[DEBUG SISTEMA] Dispositivos CUDA detectados: {cuda_count}")
        if cuda_count > 0:
            cv2.cuda.printCudaDeviceInfo(0)
            print(f"[DEBUG SISTEMA] ¡ACELERACIÓN GPU ACTIVA!")
        else:
            print(f"[DEBUG SISTEMA] ❌ ALERTA: NO SE DETECTA GPU. TODO IRÁ LENTO.")
        print(f"[DEBUG SISTEMA] --------------------------------------\n")

        self.nanodet_net = None
        self.pose_wrapper = None
        self.midas_net = None
        
        self._check_and_download_models()
        self._load_models()

    def _download_file(self, url, path):
        if not os.path.exists(path) or os.path.getsize(path) < 1000:
            print(f"⏳ Descargando {os.path.basename(path)}...")
            try:
                opener = urllib.request.build_opener()
                opener.addheaders = [('User-Agent', 'Mozilla/5.0')]
                urllib.request.install_opener(opener)
                urllib.request.urlretrieve(url, path)
            except Exception as e:
                print(f"❌ Error descarga: {e}")

    def _check_and_download_models(self):
        os.makedirs(self.models_dir, exist_ok=True)
        self._download_file("https://github.com/RangiLyu/nanodet/releases/download/v1.0.0-alpha-1/nanodet-plus-m_416.onnx", self.nanodet_path)
        self._download_file("https://huggingface.co/Xenova/yolov8-pose-onnx/resolve/main/yolov8n-pose.onnx?download=true", self.pose_path)
        self._download_file("https://github.com/isl-org/MiDaS/releases/download/v2_1/model-small.onnx", self.midas_path)
        self._download_file("https://huggingface.co/SpotLab/YOLOv8Detection/resolve/3005c6751fb19cdeb6b10c066185908faf66a097/yolov8n.onnx?download=true", self.yolov8_path)

    def _load_models(self):
        # NanoDet
        self.nanodet_net = cv2.dnn.readNet(self.yolov8_path)
        self.nanodet_net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
        self.nanodet_net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
        # Pose
        self.pose_wrapper = YoloPoseWrapper(self.pose_path)
        self.pose_wrapper.load_model()
        # MiDaS
        self.midas_net = cv2.dnn.readNet(self.midas_path)
        self.midas_net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
        self.midas_net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)

    def detect_ball(self, frame):
        blob = cv2.dnn.blobFromImage(frame, 0.017429, (416,416), (103.53, 116.28, 123.675), False, False)
        self.nanodet_net.setInput(blob)
        outputs = self.nanodet_net.forward(self.nanodet_net.getUnconnectedOutLayersNames())
        preds = outputs[0][0]
        h, w = frame.shape[:2]
        scale_w, scale_h = w/416, h/416
        balls = []
        for det in preds:
            scores = det[4:]
            cls = np.argmax(scores)
            # 32 = Sports ball. 
            # DEBUG: Bajamos el umbral a 0.25 para ver si detecta algo
            if cls == 32 and scores[cls] > 0.25: 
                 cx, cy, bw, bh = det[:4]
                 x = int((cx - bw/2)*scale_w)
                 y = int((cy - bh/2)*scale_h)
                 balls.append([x, y, int(bw*scale_w), int(bh*scale_h), float(scores[cls])])
        return balls

    def get_depth_map(self, frame):
        img_h, img_w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(frame, 1/255.0, (256, 256), (123.675, 116.28, 103.53), True, False)
        self.midas_net.setInput(blob)
        depth = self.midas_net.forward()
        depth = depth[0,0]
        depth = cv2.resize(depth, (img_w, img_h))
        # Normalizar 0-255 (0=lejos, 255=cerca)
        depth = cv2.normalize(depth, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)
        return depth

    def run_on_video(self, video_path, frame_stride=3, max_frames=200, hit_threshold=0.4, return_images=True):
        cap = cv2.VideoCapture(video_path)
        frame_idx = 0
        processed = 0
        images_b64 = []
        debug_logs = []

        start_time = time.time()

        # Procesaremos máximo 20 frames con imágenes para no saturar el JSON
        # pero analizaremos métricas de todos.
        frames_with_images_limit = 20 
        saved_images = 0

        while processed < max_frames:
            ret, frame = cap.read()
            if not ret: break

            if frame_idx % frame_stride != 0:
                frame_idx += 1
                continue

            # 1. Detecciones
            balls = self.detect_ball(frame)
            
            # Solo corremos Pose/Depth si queremos debuggear o si hay pelotas
            # Para DEBUG: Corremos SIEMPRE para ver si detecta personas aunque no haya pelota
            pose_blob = self.pose_wrapper.preprocess(frame)
            self.pose_wrapper.net.setInput(pose_blob)
            pose_out = self.pose_wrapper.net.forward()
            people = self.pose_wrapper.postprocess(pose_out)
            
            depth_map = None
            if len(balls) > 0 and len(people) > 0:
                depth_map = self.get_depth_map(frame)

            # 2. Análisis Lógico (DEBUGGING)
            frame_log = {
                "frame": frame_idx, 
                "balls_count": len(balls), 
                "people_count": len(people),
                "details": []
            }

            is_hit = False
            vis_frame = frame.copy()

            # Dibujar pelotas (Rojo)
            for b in balls:
                cv2.rectangle(vis_frame, (b[0], b[1]), (b[0]+b[2], b[1]+b[3]), (0,0,255), 2)
                cv2.putText(vis_frame, f"B:{b[4]:.2f}", (b[0], b[1]-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,255), 1)

            # Dibujar Personas (Verde) y analizar distancia
            if len(balls) > 0 and len(people) > 0 and depth_map is not None:
                # Tomar pelota principal
                bx, by, bw, bh, _ = balls[0]
                ball_center = (bx + bw//2, by + bh//2)
                ball_z = depth_map[ball_center[1], ball_center[0]]

                for p_idx, person in enumerate(people):
                    kpts = person['keypoints']
                    # Muñeca Derecha (10)
                    rw = kpts[10]
                    if rw['conf'] > 0.5:
                        # Distancias
                        dist_2d = np.linalg.norm(np.array([rw['x'], rw['y']]) - np.array(ball_center))
                        try:
                            wrist_z = depth_map[rw['y'], rw['x']]
                            dist_z = abs(int(ball_z) - int(wrist_z))
                        except:
                            dist_z = 999

                        # Dibujar línea a la muñeca
                        color = (0, 255, 255) # Amarillo (Lejos)
                        if dist_2d < 150: color = (0, 165, 255) # Naranja (Cerca 2D)
                        if dist_2d < 100 and dist_z < 50: 
                            color = (0, 255, 0) # Verde (HIT POTENCIAL)
                            is_hit = True
                            frame_log["details"].append(f"HIT DETECTADO! Dist2D:{dist_2d:.1f}, DistZ:{dist_z}")
                        else:
                            frame_log["details"].append(f"P{p_idx}: Dist2D:{dist_2d:.1f} (Umbral 100), DistZ:{dist_z} (Umbral 50)")

                        cv2.line(vis_frame, ball_center, (rw['x'], rw['y']), color, 2)
                        cv2.circle(vis_frame, (rw['x'], rw['y']), 5, (255,0,0), -1)

            elif len(balls) == 0:
                frame_log["details"].append("No se detectó pelota")
            elif len(people) == 0:
                frame_log["details"].append("No se detectó persona")

            # Guardar Logs
            debug_logs.append(frame_log)

            # 3. Guardar Imágenes de Muestra (Primeras 20 o si hay Hit)
            if saved_images < frames_with_images_limit or is_hit:
                _, buffer = cv2.imencode('.jpg', vis_frame)
                img_b64 = base64.b64encode(buffer).decode('utf-8')
                images_b64.append({
                    "frame": frame_idx, 
                    "log": frame_log["details"],
                    "image": img_b64
                })
                saved_images += 1

            processed += 1
            frame_idx += 1

        cap.release()
        total_time = time.time() - start_time
        
        return {
            "success": True,
            "performance": {
                "fps": round(processed/total_time, 2), 
                "total_time": total_time,
                "frames_processed": processed
            },
            "debug_logs": debug_logs, # <--- AQUÍ ESTÁ LA INFORMACIÓN CLAVE
            "debug_images": images_b64
        }