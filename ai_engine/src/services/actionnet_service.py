from collections import defaultdict
from typing import Dict, Any, List

import cv2
from fastapi import HTTPException

from .video_utils import bgr_to_cuda
from .jetson_env import JETSON_MODELS_MANIFEST

try:
    import jetson.inference
    import jetson.utils
    JETSON_INFERENCE_AVAILABLE = True
except ImportError:
    JETSON_INFERENCE_AVAILABLE = False


class ActionNetService:
    """Pequeño wrapper alrededor de jetson-inference actionNet."""

    def __init__(self, model_name: str, labels_path: str | None = None):
        self.model_name = model_name
        self.labels_path = labels_path
        self._net = None

    def _ensure_available(self):
        if not JETSON_INFERENCE_AVAILABLE:
            raise HTTPException(503, "jetson-inference is not available on this device")

    def _load(self):
        if self._net is not None:
            return self._net
        self._ensure_available()
        try:
            if self.labels_path:
                self._net = jetson.inference.actionNet(self.model_name, self.labels_path)
            else:
                self._net = jetson.inference.actionNet(self.model_name)
        except Exception as exc:
            manifest_hint = JETSON_MODELS_MANIFEST or "networks/models.json"
            raise HTTPException(
                503,
                f"jetson-inference actionNet failed to load '{self.model_name}'. "
                f"Verifica que exista {manifest_hint} y los pesos requeridos. Detalle: {exc}"
            )
        return self._net

    def classify_image(self, image, top_k: int) -> Dict[str, Any]:
        net = self._load()
        cuda_img = bgr_to_cuda(image)
        class_id, confidence = net.Classify(cuda_img)

        top_predictions = []
        classifications = net.GetClassifications()
        for cls in classifications:
            top_predictions.append({
                "class_id": int(cls.classID),
                "label": net.GetClassDesc(int(cls.classID)),
                "confidence": float(cls.confidence)
            })
            if len(top_predictions) >= top_k:
                break

        return {
            "predicted_class": {
                "class_id": int(class_id),
                "label": net.GetClassDesc(int(class_id)),
                "confidence": float(confidence)
            },
            "top_predictions": top_predictions
        }

    def classify_video(self, video_path: str, frame_stride: int, top_k: int) -> Dict[str, Any]:
        net = self._load()
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise HTTPException(400, "Unable to open uploaded video")

        frame_idx = 0
        processed = 0
        predictions = []

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % frame_stride != 0:
                frame_idx += 1
                continue

            cuda_img = bgr_to_cuda(frame)
            class_id, confidence = net.Classify(cuda_img)
            predictions.append({
                "frame": frame_idx,
                "class_id": int(class_id),
                "label": net.GetClassDesc(int(class_id)),
                "confidence": float(confidence)
            })
            processed += 1
            frame_idx += 1

        cap.release()

        aggregates = defaultdict(lambda: {"count": 0, "max_confidence": 0.0})
        for pred in predictions:
            label = pred["label"]
            aggregates[label]["count"] += 1
            aggregates[label]["max_confidence"] = max(
                aggregates[label]["max_confidence"],
                pred["confidence"]
            )

        top_labels = sorted(
            [{"label": label, **stats} for label, stats in aggregates.items()],
            key=lambda x: (x["count"], x["max_confidence"]),
            reverse=True
        )[:top_k]

        return {
            "frames_analyzed": processed,
            "predictions": predictions,
            "top_labels": top_labels
        }
