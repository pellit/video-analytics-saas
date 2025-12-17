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
        # Directorio donde guardaremos los modelos
        self.models_dir = "/app/ai_engine/models"
        
        # Modelo que usaremos por defecto (416x416 es el mejor balance para Jetson)
        target_model_name = "nanodet-plus-m_416.onnx"
        self.model_path = os.getenv("NANODET_MODEL_PATH", os.path.join(self.models_dir, target_model_name))
        
        self.input_shape = (416, 416) 
        self.prob_threshold = 0.40
        self.iou_threshold = 0.50

        # LISTA DE MODELOS A DESCARGAR desde xlite-dev
        # Base URL raw:
        self.base_url = "https://raw.githubusercontent.com/xlite-dev/nanodet-toolkit/main/examples/hub/onnx/cv/"
        
        self.files_to_download = [
            "nanodet-plus-m_320.onnx",
            "nanodet-plus-m_416.onnx",
            "nanodet-plus-m-1.5x_320.onnx",
            "nanodet-plus-m-1.5x_416.onnx",
            "nanodet-plus-shufflenet_v2_320.onnx",
            "nanodet-plus-shufflenet_v2_416.onnx"
        ]
        
        self._net = None
        
        # 1. Descargar todos los modelos disponibles en el repo
        self._download_all_models()
        
        # 2. Cargar el modelo seleccionado
        self._load_model()

    def _download_all_models(self):
        """Descarga la suite completa de modelos desde xlite-dev."""
        print(f"[HitDetect] 📦 Verificando modelos en {self.models_dir}...")
        os.makedirs(self.models_dir, exist_ok=True)
        
        opener = urllib.request.build_opener()
        opener.addheaders = [('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')]
        urllib.request.install_opener(opener)

        for filename in self.files_to_download:
            local_path = os.path.join(self.models_dir, filename)
            remote_url = self.base_url + filename
            
            download_needed = False
            
            # Verificar existencia y tamaño (para evitar archivos corruptos de 0kb o HTML de error)
            if not os.path.exists(local_path):
                download_needed = True
            else:
                size_mb = os.path.getsize(local_path) / (1024 * 1024)
                if size_mb < 0.5: # Si pesa menos de 0.5MB, es sospechoso (suelen pesar 4MB+)
                    print(f"[HitDetect] ⚠️ {filename} parece corrupto ({size_mb:.2f} MB). Re-descargando...")
                    try: os.remove(local_path)
                    except: pass
                    download_needed = True
            
            if download_needed:
                print(f"[HitDetect] ⏳ Descargando: {filename} ...")
                try:
                    urllib.request.urlretrieve(remote_url, local_path)
                    print(f"[HitDetect] ✅ {filename} descargado OK.")
                except Exception as e:
                    print(f"[HitDetect] ❌ Error descargando {filename}: {e}")
                    # No lanzamos error fatal aquí para intentar bajar los siguientes
            else:
                # print(f"[HitDetect] -> {filename} ya existe y es válido.")
                pass

    def _load_model(self):
        if not os.path.exists(self.model_path):
            # Si el modelo target falló al descargar, intentamos fallback a cualquiera que exista
            print(f"[HitDetect] 🛑 El modelo objetivo {self.model_path} no existe. Buscando alternativa...")
            found = False
            for f in self.files_to_download:
                p = os.path.join(self.models_dir, f)
                if os.path.exists(p) and os.path.getsize(p) > 1000000:
                    self.model_path = p
                    if "320" in f: self.input_shape = (320, 320)
                    else: self.input_shape = (416, 416)
                    print(f"[HitDetect] ⚠️ Usando fallback: {self.model_path}")
                    found = True
                    break
            if not found:
                raise RuntimeError("No se pudo descargar ningún modelo válido. Verifica tu conexión.")

        try:
            print(f"[HitDetect] Cargando red neuronal: {os.path.basename(self.model_path)}...")
            self._net = cv2.dnn.readNet(self.model_path)
            self._net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
            self._net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
            print("[HitDetect] 🚀 Modelo cargado exitosamente en GPU (CUDA).")
        except Exception as e:
            print(f"[HitDetect] Error crítico cargando modelo OpenCV: {e}")
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
            
            # Hit logic
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