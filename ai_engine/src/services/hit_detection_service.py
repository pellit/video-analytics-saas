import os
import traceback
from typing import Dict, Any, List

import cv2
from fastapi import HTTPException


class HitDetectionService:
    """Encapsula la ejecución del modelo hit_detect.onnx."""

    def __init__(self, default_model_dirs: List[str]):
        self.default_model_dirs = default_model_dirs
        self._model_override = os.environ.get('HIT_DETECT_MODEL_PATH')
        self._net = None

    def _resolve_model_path(self) -> str:
        candidates = []
        if self._model_override:
            candidates.append(self._model_override)
        candidates.extend(self.default_model_dirs)
        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                return os.path.abspath(candidate)
        raise HTTPException(
            503,
            "hit_detect.onnx no está disponible en el dispositivo. "
            "Configura HIT_DETECT_MODEL_PATH o copia el archivo a ai_engine/models/."
        )

    def _load_model(self):
        if self._net is not None:
            return self._net
        model_path = self._resolve_model_path()
        print(f"[HitDetect] Loading ONNX model from {model_path}")
        try:
            net = cv2.dnn.readNetFromONNX(model_path)
            net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
            net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
            self._net = net
            return self._net
        except Exception as exc_gpu:
            print(f"[HitDetect] CUDA backend failed: {exc_gpu}. Falling back to CPU.")
            traceback.print_exc()
            try:
                net = cv2.dnn.readNetFromONNX(model_path)
                net.setPreferableBackend(cv2.dnn.DNN_BACKEND_DEFAULT)
                net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
                self._net = net
                return self._net
            except Exception as exc_cpu:
                traceback.print_exc()
                raise HTTPException(503, f"No se pudo inicializar hit_detect.onnx: {exc_cpu}")

    def run_on_video(
        self,
        video_path: str,
        frame_stride: int,
        max_frames: int,
        hit_threshold: float
    ) -> Dict[str, Any]:
        net = self._load_model()
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise HTTPException(400, "Unable to open uploaded video")

        frame_idx = 0
        processed = 0
        detections = []
        debug_logs = []

        while processed < max_frames:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % frame_stride != 0:
                frame_idx += 1
                continue

            resized = cv2.resize(frame, (224, 224))
            blob = cv2.dnn.blobFromImage(resized, scalefactor=1 / 255.0, size=(224, 224), swapRB=True, crop=False)
            net.setInput(blob)
            try:
                output = net.forward()
            except Exception as exc:
                error_msg = f"Hit detection forward failed on frame {frame_idx}: {exc}"
                print(f"[HitDetect] {error_msg}")
                traceback.print_exc()
                cap.release()
                raise HTTPException(500, error_msg)

            flat = output.flatten().tolist()
            if not flat:
                probability = 0.0
            elif len(flat) == 1:
                probability = float(flat[0])
            else:
                probability = float(flat[-1])

            detections.append({
                "frame": frame_idx,
                "hit_probability": round(probability, 4),
                "raw_output": flat
            })
            if len(debug_logs) < 10:
                debug_logs.append({
                    "frame": frame_idx,
                    "blob_shape": list(blob.shape),
                    "output_shape": list(output.shape) if hasattr(output, "shape") else None,
                    "hit_probability": round(probability, 4)
                })

            processed += 1
            frame_idx += 1

        cap.release()

        hits = [det for det in detections if det["hit_probability"] >= hit_threshold]

        return {
            "frames_analyzed": processed,
            "detections": detections,
            "hits_detected": len(hits),
            "hit_threshold": hit_threshold,
            "hit_frames": [det["frame"] for det in hits],
            "debug_logs": debug_logs
        }
