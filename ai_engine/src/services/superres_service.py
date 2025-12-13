import os
from typing import Optional, Tuple

import cv2
from fastapi import HTTPException


class SuperResolutionService:
    """Maneja cv2.dnn_superres para imágenes/video."""

    def __init__(self, default_model_dir: str, preferred_model_path: Optional[str] = None):
        self.default_model_dir = default_model_dir
        self.preferred_model_path = preferred_model_path
        self._engine = None
        self._scale = 2
        self._model_path = None
        try:
            from cv2.dnn_superres import DnnSuperResImpl_create
            self._factory = DnnSuperResImpl_create
        except ImportError:
            self._factory = None

    def _infer_superres_config(self, model_path: str) -> Tuple[str, int]:
        fname = os.path.basename(model_path).lower()
        algo = 'edsr'
        for candidate in ('edsr', 'espcn', 'fsrcnn', 'lapsrn'):
            if candidate in fname:
                algo = candidate
                break
        scale = 4
        for candidate in (8, 4, 3, 2):
            token = f"x{candidate}"
            if token in fname or f"{candidate}x" in fname or f"_x{candidate}" in fname:
                scale = candidate
                break
        return algo, scale

    def _resolve_model_path(self) -> Optional[str]:
        candidates = []
        if self.preferred_model_path:
            candidates.append(self.preferred_model_path)
        preferred = [
            os.path.join(self.default_model_dir, 'superres.pb'),
            os.path.join(self.default_model_dir, 'super_resolution_bsd500.pb'),
            os.path.join(self.default_model_dir, 'super_resolution.pb'),
        ]
        fallbacks = [
            os.path.join(self.default_model_dir, 'super_resolution.onnx'),
            os.path.join(self.default_model_dir, 'model.onnx'),
            os.path.join(self.default_model_dir, 'superres.onnx'),
        ]
        candidates.extend(preferred + fallbacks)
        if self.default_model_dir and os.path.isdir(self.default_model_dir):
            dir_files = sorted(os.listdir(self.default_model_dir))
            for ext in ('.pb', '.onnx'):
                for filename in dir_files:
                    if filename.lower().endswith(ext):
                        candidates.append(os.path.join(self.default_model_dir, filename))
        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                return candidate
        return None

    def load_engine(self):
        if self._engine is not None:
            return self._engine, self._scale
        if self._factory is None:
            raise HTTPException(503, "cv2.dnn_superres no está disponible en este entorno (compila OpenCV con contrib).")
        model_path = self._resolve_model_path()
        if not model_path or not os.path.exists(model_path):
            raise HTTPException(503, "No se encontró el modelo de super resolución. Configura SUPERRES_MODEL_PATH o verifica data/networks/Super-Resolution-BSD500.")
        _, ext = os.path.splitext(model_path)
        if ext.lower() == '.onnx':
            raise HTTPException(
                503,
                f"El modelo seleccionado ({model_path}) es ONNX y cv2.dnn_superres solo soporta pesos TensorFlow (.pb). "
                "Descarga/convierte la versión .pb o apunta SUPERRES_MODEL_PATH a un archivo .pb válido."
            )
        try:
            sr = self._factory()
            sr.readModel(model_path)
            algo, scale = self._infer_superres_config(model_path)
            sr.setModel(algo, scale)
            self._engine = sr
            self._scale = scale
            self._model_path = model_path
            print(f"✅ Super Resolution model loaded ({algo}, x{scale}): {model_path}")
            return self._engine, self._scale
        except Exception as exc:
            raise HTTPException(503, f"No se pudo cargar el modelo de super resolución en {model_path}: {exc}")
