import cv2
import numpy as np
import os
import traceback
import urllib.request
import time
from typing import Any, Dict, List
from fastapi import HTTPException

class HitDetectionService:
    def __init__(self, default_model_dirs: List[str] = None):
        # Ruta destino
        self.model_path = os.getenv("NANODET_MODEL_PATH", "/app/ai_engine/models/nanodet-plus-m_416.onnx")
        self.input_shape = (416, 416)
        self.prob_threshold = 0.40
        self.iou_threshold = 0.50

        # LISTA DE MIRRORS (Intentaremos uno por uno)
        self.mirrors = [
            "https://github.com/RangiLyu/nanodet/releases/download/v1.0.0-alpha/nanodet-plus-m_416.onnx",
            "https://raw.githubusercontent.com/RangiLyu/nanodet/main/demo_ncnn/nanodet-plus-m_416.onnx",
            "https://github.com/hpc203/nanodet-plus-opencv/raw/main/nanodet-plus-m_416.onnx"
        ]
        
        self._net = None
        self._check_and_download_model()
        self._load_model()

    def _check_and_download_model(self):
        # 1. Verificar si el archivo actual es válido
        if os.path.exists(self.model_path):
            size_mb = os.path.getsize(self.model_path) / (1024 * 1024)
            if size_mb > 1.0:
                print(f"[HitDetect] ✅ Modelo encontrado y válido ({size_mb:.2f} MB).")
                return
            else:
                print(f"[HitDetect] ⚠️ Archivo corrupto ({size_mb:.2f} MB). Eliminando...")
                try: os.remove(self.model_path)
                except: pass

        # 2. Intentar descargar desde los mirrors
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        
        success = False
        for url in self.mirrors:
            print(f"[HitDetect] ⏳ Intentando descargar desde: {url} ...")
            try:
                # Headers para evitar bloqueo 403/404 de GitHub
                opener = urllib.request.build_opener()
                opener.addheaders = [('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')]
                urllib.request.install_opener(opener)
                
                urllib.request.urlretrieve(url, self.model_path)
                
                # Verificar descarga
                if os.path.exists(self.model_path) and os.path.getsize(self.model_path) > 1000000:
                    print(f"[HitDetect] ✅ Descarga exitosa!")
                    success = True
                    break
            except Exception as e:
                print(f"[HitDetect] ❌ Falló mirror: {e}")
                time.sleep(1) # Esperar un poco antes del siguiente

        if not success:
            raise RuntimeError(
                f"\n\n🛑 ERROR FATAL: No se pudo descargar el modelo de ningún mirror.\n"
                f"SOLUCIÓN MANUAL:\n"
                f"1. Descarga 'nanodet-plus-m_416.onnx' en tu PC desde: https://github.com/RangiLyu/nanodet/releases\n"
                f"2. Copialo al contenedor con: docker cp nanodet-plus-m_416.onnx <ID_CONTENEDOR>:{self.model_path}\n"
            )

    def _load_model(self):
        try:
            print(f"[HitDetect] Cargando red neuronal en CUDA...")
            self._net = cv2.dnn.readNet(self.model_path)
            self._net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
            self._net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
            print("[HitDetect] 🚀 Modelo cargado OK.")
        except Exception as e:
            print(f"[HitDetect] Error cargando modelo: {e}")
            raise e

    def _preprocess(self, image):
        blob = cv2.dnn.blobFromImage(
            image, 1.0, self.input_shape, (103.53, 116.28, 123.675), swapRB=False, crop=False
        )
        return blob

    def _postprocess(self, outputs, img_w, img_h):
        # Lógica de post-proceso NanoDet
        preds = outputs[0]
        if len(preds.shape) == 3: preds = preds[0]
        
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
                boxes.append([
                    int((cx - w/2) * scale_w),
                    int((cy - h/2) * scale_h),
                    int(w * scale_w),
                    int(h * scale_h)
                ])
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
        if not cap.isOpened(): raise HTTPException(400, "Error abriendo video")

        frame_idx = 0
        processed = 0
        hits_detected = 0
        hit_frames = []
        debug_logs = []

        while processed < max_frames:
            ret, frame = cap.read()
            if not ret: break

            if frame_idx % frame_stride != 0:
                frame_idx += 1
                continue

            # Inferencia
            blob = self._preprocess(frame)
            self._net.setInput(blob)
            outputs = self._net.forward(self._net.getUnconnectedOutLayersNames())
            detections = self._postprocess(outputs, frame.shape[1], frame.shape[0])

            # Detectar Hit
            max_conf = max([d['confidence'] for d in detections]) if detections else 0.0
            is_hit = max_conf >= hit_threshold
            
            if is_hit:
                hits_detected += 1
                hit_frames.append(frame_idx)

            if len(debug_logs) < 5:
                debug_logs.append({"frame": frame_idx, "hit_conf": round(max_conf, 4), "is_hit": is_hit})

            processed += 1
            frame_idx += 1

        cap.release()
        return {
            "frames_analyzed": processed, 
            "hits_detected": hits_detected, 
            "hit_threshold": hit_threshold,
            "hit_frames": hit_frames, 
            "debug_logs": debug_logs
        }