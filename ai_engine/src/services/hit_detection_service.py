import cv2
import numpy as np
import os
import traceback
import urllib.request
from typing import Any, Dict, List
from fastapi import HTTPException

class HitDetectionService:
    def __init__(self, default_model_dirs: List[str] = None):
        # Ruta del modelo
        self.model_path = os.getenv("NANODET_MODEL_PATH", "/app/ai_engine/models/nanodet-plus-m_416.onnx")
        self.input_shape = (416, 416) 
        self.prob_threshold = 0.40
        self.iou_threshold = 0.50

        # URL de respaldo por si el archivo está roto (Usamos un mirror confiable o el repo oficial)
        self.model_url = "https://github.com/RangiLyu/nanodet/releases/download/v1.0.0-alpha/nanodet-plus-m_416.onnx"
        
        self._net = None
        self._check_and_download_model() # <--- VERIFICACIÓN AUTOMÁTICA
        self._load_model()

    def _check_and_download_model(self):
        """
        Verifica si el modelo existe y es un archivo ONNX válido (por tamaño).
        Si es muy pequeño (<100KB), asume que es un error HTML y lo descarga de nuevo.
        """
        download_needed = False
        
        if not os.path.exists(self.model_path):
            print(f"[HitDetect] ⚠️ Modelo no encontrado en {self.model_path}")
            download_needed = True
        else:
            # Verificar tamaño (NanoDet-Plus-m pesa aprox 4.7 MB)
            size_mb = os.path.getsize(self.model_path) / (1024 * 1024)
            if size_mb < 1.0: # Si pesa menos de 1MB, seguro es basura HTML
                print(f"[HitDetect] ⚠️ El archivo del modelo parece corrupto ({size_mb:.2f} MB). Eliminando...")
                os.remove(self.model_path)
                download_needed = True
            else:
                print(f"[HitDetect] ✅ Archivo de modelo válido detectado ({size_mb:.2f} MB).")

        if download_needed:
            print(f"[HitDetect] ⏳ Descargando NanoDet-Plus desde {self.model_url}...")
            try:
                # Asegurar que el directorio existe
                os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
                
                # Descarga usando urllib (más robusto que curl en algunos entornos)
                urllib.request.urlretrieve(self.model_url, self.model_path)
                
                # Verificar de nuevo
                if os.path.exists(self.model_path) and os.path.getsize(self.model_path) > 1000000:
                     print(f"[HitDetect] ✅ Descarga completada exitosamente.")
                else:
                     raise RuntimeError("La descarga finalizó pero el archivo sigue siendo demasiado pequeño.")
            except Exception as e:
                print(f"[HitDetect] ❌ Error fatal descargando el modelo: {e}")
                raise RuntimeError(f"No se pudo descargar el modelo. Verifica tu conexión a internet en el contenedor.")

    def _load_model(self):
        print(f"[HitDetect] Cargando red neuronal...")
        try:
            self._net = cv2.dnn.readNet(self.model_path)
            self._net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
            self._net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
            print("[HitDetect] 🚀 Modelo cargado exitosamente en GPU (CUDA).")
        except Exception as e:
            print(f"[HitDetect] Error crítico en OpenCV: {e}")
            # Si falla aquí, es posible que el archivo siga corrupto o incompatible
            raise e

    def _preprocess(self, image):
        blob = cv2.dnn.blobFromImage(
            image, 
            scalefactor=1.0, 
            size=self.input_shape,
            mean=(103.53, 116.28, 123.675),
            swapRB=False,
            crop=False
        )
        return blob

    def _postprocess(self, outputs, img_w, img_h):
        # Adaptación para la salida de NanoDet-Plus
        # Flattening simple para gestionar diferentes tipos de salida
        preds = outputs[0]
        if len(preds.shape) == 3:
            preds = preds[0]
        
        scale_w = img_w / self.input_shape[0]
        scale_h = img_h / self.input_shape[1]

        class_ids = []
        confidences = []
        boxes = []

        for det in preds:
            # NanoDet format: [cx, cy, w, h, scores...]
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

    def run_on_video(
        self,
        video_path: str,
        frame_stride: int,
        max_frames: int,
        hit_threshold: float 
    ) -> Dict[str, Any]:
        
        if self._net is None:
            self._load_model()

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise HTTPException(400, "Unable to open uploaded video")

        frame_idx = 0
        processed = 0
        hits_detected = 0
        hit_frames = []
        debug_logs = []

        while processed < max_frames:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % frame_stride != 0:
                frame_idx += 1
                continue

            img_h, img_w = frame.shape[:2]
            
            blob = self._preprocess(frame)
            self._net.setInput(blob)
            outputs = self._net.forward(self._net.getUnconnectedOutLayersNames())
            
            detections = self._postprocess(outputs, img_w, img_h)
            
            # Lógica de HIT: detección con confianza mayor al umbral
            max_conf = 0.0
            if detections:
                max_conf = max([d['confidence'] for d in detections])

            is_hit = max_conf >= hit_threshold
            
            if is_hit:
                hits_detected += 1
                hit_frames.append(frame_idx)

            if len(debug_logs) < 5:
                debug_logs.append({
                    "frame": frame_idx,
                    "hit_conf": round(max_conf, 4),
                    "is_hit": is_hit
                })

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