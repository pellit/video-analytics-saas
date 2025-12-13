import os
from typing import List, Dict, Any, Optional, Iterable

import cv2
import numpy as np
import requests
from fastapi import HTTPException


MODEL_URLS = {
    "yolov4-tiny.cfg": "https://raw.githubusercontent.com/AlexeyAB/darknet/master/cfg/yolov4-tiny.cfg",
    "yolov4-tiny.weights": "https://github.com/AlexeyAB/darknet/releases/download/darknet_yolo_v4_pre/yolov4-tiny.weights",
    "coco.names": "https://raw.githubusercontent.com/AlexeyAB/darknet/master/data/coco.names",
}


class YoloFallbackService:
    """
    Encapsula la lógica de descarga/carga de YOLOv4-tiny para usarlo como fallback
    cuando detectNet no encuentra ciertos objetos (pelota, etc).
    """

    def __init__(self, models_dir: str):
        self.models_dir = models_dir
        self._net = None
        self._output_layers = None
        self._classes: List[str] = []
        self._model_name: Optional[str] = None

    # --------------------------------------------------------------------- #
    # Public helpers
    # --------------------------------------------------------------------- #
    @property
    def model_name(self) -> Optional[str]:
        return self._model_name

    def ensure_ready(self) -> None:
        """Carga el modelo si todavía no está disponible."""
        if self._net is None or self._output_layers is None:
            if not self._load_model():
                raise HTTPException(503, "YOLOv4-Tiny no está disponible para el fallback de pelota")

    def detect(
        self,
        image: np.ndarray,
        confidence: float,
        nms_threshold: float,
        labels_filter: Optional[Iterable[str]] = None,
    ) -> List[Dict[str, Any]]:
        try:
            self.ensure_ready()
        except HTTPException:
            return []

        h, w = image.shape[:2]
        blob = cv2.dnn.blobFromImage(image, scalefactor=1 / 255.0, size=(416, 416), swapRB=True, crop=False)
        self._net.setInput(blob)
        try:
            layer_outputs = self._net.forward(self._output_layers)
        except Exception as exc:
            print(f"[YOLO fallback] forward failed: {exc}")
            return []

        boxes = []
        confidences = []
        class_ids = []
        for output in layer_outputs:
            for detection in output:
                scores = detection[5:]
                class_id = int(np.argmax(scores))
                conf = float(scores[class_id])
                if conf < confidence:
                    continue
                center_x = int(detection[0] * w)
                center_y = int(detection[1] * h)
                width = int(detection[2] * w)
                height = int(detection[3] * h)
                x = max(0, int(center_x - width / 2))
                y = max(0, int(center_y - height / 2))
                boxes.append([x, y, width, height])
                confidences.append(conf)
                class_ids.append(class_id)

        if not boxes:
            return []

        try:
            idxs = cv2.dnn.NMSBoxes(boxes, confidences, confidence, nms_threshold)
        except Exception:
            idxs = list(range(len(boxes)))

        label_filter_set = {lbl.lower() for lbl in labels_filter} if labels_filter else None
        if isinstance(idxs, (list, tuple)):
            idx_iter = [int(i) for i in idxs]
        elif hasattr(idxs, "__iter__"):
            idx_iter = [int(i[0]) for i in idxs]
        else:
            idx_iter = range(len(boxes))

        results: List[Dict[str, Any]] = []
        for i in idx_iter:
            class_name = self._classes[class_ids[i]] if self._classes else f"class_{class_ids[i]}"
            if label_filter_set and class_name.lower() not in label_filter_set:
                continue
            x, y, width, height = boxes[i]
            bbox = [x, y, x + width, y + height]
            results.append({
                "class_name": class_name.lower(),
                "class_id": int(class_ids[i]),
                "confidence": round(float(confidences[i]), 2),
                "bbox": bbox,
                "track_id": None,
                "area": int(width * height),
                "status": None,
                "source": "yolo",
                "engine": self._model_name or "yolov4-tiny"
            })
        return results

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #
    def _download_file(self, url: str, dest: str) -> None:
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            return
        try:
            r = requests.get(url, stream=True, timeout=30)
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        except Exception as exc:
            print(f"❌ No se pudo descargar {dest}: {exc}")

    def _load_model(self) -> bool:
        cfg_path = os.path.join(self.models_dir, "yolov4-tiny.cfg")
        weights_path = os.path.join(self.models_dir, "yolov4-tiny.weights")
        names_path = os.path.join(self.models_dir, "coco.names")

        self._download_file(MODEL_URLS["yolov4-tiny.cfg"], cfg_path)
        self._download_file(MODEL_URLS["yolov4-tiny.weights"], weights_path)
        self._download_file(MODEL_URLS["coco.names"], names_path)

        if os.path.exists(names_path):
            with open(names_path, "r") as f:
                self._classes = [line.strip() for line in f.readlines()]
        else:
            self._classes = ["object"]

        try:
            print("⏳ Loading YOLOv4-Tiny...")
            self._net = cv2.dnn.readNet(weights_path, cfg_path)
            # Prefer CUDA si está disponible
            self._net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
            self._net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
            layer_names = self._net.getLayerNames()
            self._output_layers = [layer_names[i[0] - 1] for i in self._net.getUnconnectedOutLayers()]
            self._model_name = "yolov4-tiny"
            return True
        except Exception as exc:
            print(f"❌ Error cargando YOLO con CUDA: {exc}")
            try:
                print("⚠️ Retrying on CPU...")
                self._net = cv2.dnn.readNet(weights_path, cfg_path)
                self._net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
                self._net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
                layer_names = self._net.getLayerNames()
                self._output_layers = [layer_names[i[0] - 1] for i in self._net.getUnconnectedOutLayers()]
                self._model_name = "yolov4-tiny-cpu"
                return True
            except Exception as fallback_exc:
                print(f"❌ CPU fallback failed: {fallback_exc}")
                self._net = None
                self._output_layers = None
                self._model_name = None
                return False
