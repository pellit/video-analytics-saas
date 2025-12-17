import cv2
import numpy as np
import os
import urllib.request
import time  # <--- IMPORTANTE: Necesario para medir el tiempo
from typing import Any, Dict, List
from fastapi import HTTPException

class HitDetectionService:
    def __init__(self, default_model_dirs: List[str] = None):
        # Usamos el modelo 416x416 (Mejor balance para Jetson Nano)
        self.model_path = os.getenv("NANODET_MODEL_PATH", "/app/ai_engine/models/nanodet-plus-m_416.onnx")
        self.input_shape = (416, 416)
        
        # Umbrales
        self.prob_threshold = 0.35
        self.iou_threshold = 0.50

        # URL del modelo (Mirror estable)
        self.model_url = "https://github.com/RangiLyu/nanodet/releases/download/v1.0.0-alpha-1/nanodet-plus-m_416.onnx"
        
        self._net = None
        self._check_and_download_model()
        self._load_model()

    def _check_and_download_model(self):
        if not os.path.exists(self.model_path) or os.path.getsize(self.model_path) < 1000000:
            print(f"[HitDetect] ⏳ Descargando modelo NanoDet-Plus desde mirror...")
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
            
            # Calentamiento (Warm-up)
            dummy = np.zeros((1, 3, 416, 416), dtype=np.float32)
            self._net.setInput(dummy)
            self._net.forward(self._net.getUnconnectedOutLayersNames())
            print("[HitDetect] 🚀 Modelo listo y calentado en GPU.")
        except Exception as e:
            print(f"[HitDetect] Error fatal cargando modelo: {e}")
            raise e

    def _preprocess(self, image):
        # NanoDet-Plus requiere: (Input - Mean) / Std
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

    def run_on_video(self, video_path: str, frame_stride: int, max_frames: int, hit_threshold: float) -> Dict[str, Any]:
        if self._net is None: self._load_model()
        cap = cv2.VideoCapture(video_path)
        
        actual_stride = max(3, frame_stride) 

        frame_idx = 0
        processed = 0
        hits_detected = 0
        debug_logs = []
        
        # --- MÉTRICAS DE RENDIMIENTO ---
        start_time = time.time()  # Hora de inicio global
        inference_times = []      # Lista para guardar tiempos individuales por frame

        while processed < max_frames:
            ret, frame = cap.read()
            if not ret: break

            if frame_idx % actual_stride != 0:
                frame_idx += 1
                continue

            # Cronometrar inferencia (Preproceso + IA + Postproceso)
            t0 = time.time()
            
            blob = self._preprocess(frame)
            self._net.setInput(blob)
            outputs = self._net.forward(self._net.getUnconnectedOutLayersNames())
            detections = self._postprocess(outputs, frame.shape[1], frame.shape[0])
            
            t1 = time.time()
            inference_times.append(t1 - t0) # Guardamos cuánto tardó este frame

            # Detectar Hit
            max_conf = max([d['confidence'] for d in detections]) if detections else 0.0
            is_hit = max_conf >= hit_threshold
            
            if is_hit: hits_detected += 1
            
            if len(debug_logs) < 10: 
                debug_logs.append({"frame": frame_idx, "max_conf": float(max_conf), "detections": len(detections)})

            processed += 1
            frame_idx += 1

        cap.release()
        
        # --- CÁLCULO DE RESULTADOS FINALES ---
        end_time = time.time()
        total_duration = end_time - start_time
        
        # Evitar división por cero si no se procesó nada
        if processed > 0:
            avg_fps = processed / total_duration
            avg_inference_ms = (sum(inference_times) / len(inference_times)) * 1000
        else:
            avg_fps = 0
            avg_inference_ms = 0

        return {
            "hits_detected": hits_detected,
            "debug_logs": debug_logs,
            "performance": {
                "total_time_sec": round(total_duration, 2),
                "frames_processed": processed,
                "fps": round(avg_fps, 2),
                "avg_inference_time_ms": round(avg_inference_ms, 2)
            }
        }