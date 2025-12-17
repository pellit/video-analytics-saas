import cv2
import numpy as np
import os
import traceback
from typing import Any, Dict, List
from fastapi import HTTPException

class HitDetectionService:
    """
    Servicio de detección usando NanoDet-Plus.
    Reemplaza al modelo antiguo hit_detect.onnx que tenía errores de TopK.
    """

    def __init__(self, default_model_dirs: List[str] = None):
        # Buscamos el modelo NanoDet que descargamos en el Dockerfile
        self.model_path = os.getenv("NANODET_MODEL_PATH", "/app/ai_engine/models/nanodet-plus-m_416.onnx")
        self.input_shape = (416, 416) # Tamaño nativo de NanoDet-Plus-m
        
        # Umbrales
        self.prob_threshold = 0.40  # Confianza mínima para considerar detección
        self.iou_threshold = 0.50   # Para eliminar cajas duplicadas

        self._net = None
        self._load_model()

    def _load_model(self):
        print(f"[HitDetect] Cargando NanoDet-Plus desde: {self.model_path}")
        if not os.path.exists(self.model_path):
            raise RuntimeError(f"No se encuentra el modelo en {self.model_path}")

        try:
            self._net = cv2.dnn.readNet(self.model_path)
            # ACTIVAR CUDA (GPU)
            self._net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
            self._net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
            print("[HitDetect] Modelo cargado exitosamente en GPU (CUDA).")
        except Exception as e:
            print(f"[HitDetect] Error cargando NanoDet: {e}")
            traceback.print_exc()
            raise e

    def _preprocess(self, image):
        # NanoDet requiere normalización específica
        # Mean: [103.53, 116.28, 123.675]
        blob = cv2.dnn.blobFromImage(
            image, 
            scalefactor=1.0, 
            size=self.input_shape,
            mean=(103.53, 116.28, 123.675),
            swapRB=False, # El modelo espera BGR si usamos cv2.imread
            crop=False
        )
        return blob

    def _postprocess(self, outputs, img_w, img_h):
        # Decodificar las salidas de NanoDet
        # La salida suele ser [1, 8400, 80+5] o similar
        preds = outputs[0]
        if len(preds.shape) == 3:
            preds = preds[0]
        
        scale_w = img_w / self.input_shape[0]
        scale_h = img_h / self.input_shape[1]

        class_ids = []
        confidences = []
        boxes = []

        # Estructura típica: [cx, cy, w, h, score_cls1, score_cls2...]
        # O a veces: [cx, cy, w, h, obj_score, cls_scores...]
        # Asumimos estructura directa de onnx simplificado:
        
        for det in preds:
            # Los primeros 4 son bbox, el resto son scores
            scores = det[4:]
            class_id = np.argmax(scores)
            confidence = scores[class_id]

            if confidence > self.prob_threshold:
                cx, cy, w, h = det[0], det[1], det[2], det[3]
                
                # Restaurar coordenadas
                x = int((cx - w/2) * scale_w)
                y = int((cy - h/2) * scale_h)
                width = int(w * scale_w)
                height = int(h * scale_h)

                boxes.append([x, y, width, height])
                confidences.append(float(confidence))
                class_ids.append(class_id)

        # NMS (Non-Maximum Suppression) usando OpenCV (Muy rápido en CPU)
        indices = cv2.dnn.NMSBoxes(boxes, confidences, self.prob_threshold, self.iou_threshold)
        
        results = []
        if len(indices) > 0:
            for i in indices.flatten():
                # Si solo te interesa detectar "personas" (clase 0 en COCO)
                # puedes filtrar aquí: if class_ids[i] == 0:
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
            
            # 1. Inferencia
            blob = self._preprocess(frame)
            self._net.setInput(blob)
            outputs = self._net.forward(self._net.getUnconnectedOutLayersNames())
            
            # 2. Interpretar resultados
            detections = self._postprocess(outputs, img_w, img_h)
            
            # Lógica de "HIT":
            # Si NanoDet encuentra algo con confianza > umbral, es un hit.
            # Tomamos la confianza más alta encontrada en el frame
            max_conf = 0.0
            if detections:
                max_conf = max([d['confidence'] for d in detections])

            is_hit = max_conf >= hit_threshold
            
            if is_hit:
                hits_detected += 1
                hit_frames.append(frame_idx)

            # Logs limitados para no saturar
            if len(debug_logs) < 10:
                debug_logs.append({
                    "frame": frame_idx,
                    "hit_probability": round(max_conf, 4),
                    "is_hit": is_hit,
                    "detections_count": len(detections)
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