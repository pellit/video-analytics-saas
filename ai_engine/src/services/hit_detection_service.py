import cv2
import numpy as np
import os
import urllib.request
import time
import base64
from typing import Any, Dict, List
from fastapi import HTTPException

class HitDetectionService:
    def __init__(self, default_model_dirs: List[str] = None):
        # Configuración del modelo (416x416 balanceado)
        self.model_path = os.getenv("NANODET_MODEL_PATH", "/app/ai_engine/models/nanodet-plus-m_416.onnx")
        self.input_shape = (416, 416)
        
        # Umbrales
        self.prob_threshold = 0.35
        self.iou_threshold = 0.50

        # URL del modelo (Mirror estable)
        self.model_url = "https://github.com/hpc203/nanodet-plus-opencv/raw/main/nanodet-plus-m_416.onnx"
        
        self._net = None
        self._check_and_download_model()
        self._load_model()

    def _check_and_download_model(self):
        if not os.path.exists(self.model_path) or os.path.getsize(self.model_path) < 1000000:
            print(f"[HitDetect] ⏳ Descargando modelo NanoDet-Plus...")
            try:
                os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
                opener = urllib.request.build_opener()
                opener.addheaders = [('User-Agent', 'Mozilla/5.0')]
                urllib.request.install_opener(opener)
                urllib.request.urlretrieve(self.model_url, self.model_path)
                print("[HitDetect] ✅ Descarga completada.")
            except Exception as e:
                print(f"[HitDetect] ❌ Error descargando: {e}")

    def _load_model(self):
        print(f"[HitDetect] Cargando red en CUDA...")
        try:
            self._net = cv2.dnn.readNet(self.model_path)
            self._net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
            self._net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
            
            # Warm-up
            dummy = np.zeros((1, 3, 416, 416), dtype=np.float32)
            self._net.setInput(dummy)
            self._net.forward(self._net.getUnconnectedOutLayersNames())
            print("[HitDetect] 🚀 Modelo listo y calentado en GPU.")
        except Exception as e:
            print(f"[HitDetect] Error fatal cargando modelo: {e}")
            raise e

    def _preprocess(self, image):
        # NanoDet-Plus: (Input - Mean) / Std
        # scalefactor = 1 / 57.375 ≈ 0.017429
        blob = cv2.dnn.blobFromImage(
            image, 
            scalefactor=0.017429, 
            size=self.input_shape,
            mean=(103.53, 116.28, 123.675),
            swapRB=False,
            crop=False
        )
        return blob

    def _postprocess(self, outputs, img_w, img_h):
        preds = outputs[0]
        if len(preds.shape) == 3:
            preds = preds[0]
        
        scale_w = img_w / self.input_shape[0]
        scale_h = img_h / self.input_shape[1]

        class_ids = []
        confidences = []
        boxes = []

        for det in preds:
            scores = det[4:]
            class_id = np.argmax(scores)
            confidence = scores[class_id]

            if confidence > self.prob_threshold:
                cx, cy, w, h = det[0], det[1], det[2], det[3]
                x = int((cx - w/2) * scale_w)
                y = int((cy - h/2) * scale_h)
                width = int(w * scale_w)
                height = int(h * scale_h)

                boxes.append([x, y, width, height])
                confidences.append(float(confidence))
                class_ids.append(class_id)

        indices = cv2.dnn.NMSBoxes(boxes, confidences, self.prob_threshold, self.iou_threshold)
        
        results = []
        if len(indices) > 0:
            for i in indices.flatten():
                results.append({
                    "box": boxes[i],
                    "confidence": confidences[i],
                    "class_id": class_ids[i]
                })
        return results

    def _draw_detections(self, frame, detections):
        """Dibuja cajas simples en el frame para visualización"""
        for det in detections:
            box = det['box']
            x, y, w, h = box[0], box[1], box[2], box[3]
            conf = det['confidence']
            
            # Caja Verde
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
            
            # Etiqueta
            label = f"{conf:.2f}"
            cv2.putText(frame, label, (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        return frame

    def run_on_video(
        self, 
        video_path: str, 
        frame_stride: int, 
        max_frames: int, 
        hit_threshold: float,
        return_images: bool = False  # <--- NUEVO PARÁMETRO QUE FALTABA
    ) -> Dict[str, Any]:
        
        if self._net is None: self._load_model()
        cap = cv2.VideoCapture(video_path)
        
        actual_stride = max(3, frame_stride) 

        frame_idx = 0
        processed = 0
        hits_detected = 0
        debug_logs = []
        hit_images_b64 = [] # Lista para guardar imágenes si se solicitan
        
        # Métricas
        start_time = time.time()
        inference_times = []

        while processed < max_frames:
            ret, frame = cap.read()
            if not ret: break

            if frame_idx % actual_stride != 0:
                frame_idx += 1
                continue

            # Inferencia
            t0 = time.time()
            blob = self._preprocess(frame)
            self._net.setInput(blob)
            outputs = self._net.forward(self._net.getUnconnectedOutLayersNames())
            detections = self._postprocess(outputs, frame.shape[1], frame.shape[0])
            t1 = time.time()
            inference_times.append(t1 - t0)

            # Lógica de Hit
            max_conf = max([d['confidence'] for d in detections]) if detections else 0.0
            is_hit = max_conf >= hit_threshold
            
            if is_hit: 
                hits_detected += 1
                
                # Si se solicitan imágenes, las dibujamos y codificamos
                if return_images:
                    # Dibujar detección sobre una copia para no afectar (si quisieras seguir usando el original)
                    visual_frame = self._draw_detections(frame.copy(), detections)
                    
                    # Codificar a JPG -> Base64
                    _, buffer = cv2.imencode('.jpg', visual_frame)
                    img_base64 = base64.b64encode(buffer).decode('utf-8')
                    
                    hit_images_b64.append({
                        "frame": frame_idx,
                        "hit_score": float(max_conf),
                        "image_base64": img_base64
                    })
            
            if len(debug_logs) < 10: 
                debug_logs.append({"frame": frame_idx, "max_conf": float(max_conf), "detections": len(detections)})

            processed += 1
            frame_idx += 1

        cap.release()
        
        end_time = time.time()
        total_duration = end_time - start_time
        
        avg_fps = processed / total_duration if processed > 0 else 0
        avg_inference_ms = (sum(inference_times) / len(inference_times)) * 1000 if inference_times else 0

        result = {
            "hits_detected": hits_detected,
            "debug_logs": debug_logs,
            "performance": {
                "total_time_sec": round(total_duration, 2),
                "frames_processed": processed,
                "fps": round(avg_fps, 2),
                "avg_inference_time_ms": round(avg_inference_ms, 2)
            }
        }

        # Solo adjuntamos las imágenes si se pidieron
        if return_images:
            result["hit_images"] = hit_images_b64

        return result