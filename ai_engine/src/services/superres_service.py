import os
from pathlib import Path
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
        search_dirs = []
        if self.default_model_dir:
            search_dirs.append(self.default_model_dir)
        # Additional fallbacks relative to repo
        repo_root = Path(__file__).resolve().parents[2]
        search_dirs.extend([
            repo_root / "data" / "networks" / "Super-Resolution-BSD500",
            repo_root / "data" / "networks" / "Super-Resolution--BSD500",
            Path("/usr/local/bin/networks/Super-Resolution-BSD500"),
            Path("/usr/local/bin/networks/Super-Resolution--BSD500"),
        ])
        unique_dirs = []
        for directory in search_dirs:
            if directory and directory not in unique_dirs:
                unique_dirs.append(directory)
        file_candidates = [
            "superres.pb",
            "super_resolution_bsd500.pb",
            "super_resolution.pb",
            "super_resolution.onnx",
            "superres.onnx",
            "model.onnx",
        ]
        for base in unique_dirs:
            base = Path(base)
            if not base or not base.exists():
                continue
            for fname in file_candidates:
                candidate = base / fname
                if candidate.exists():
                    candidates.append(str(candidate))
            for entry in sorted(base.glob("*")):
                if entry.suffix.lower() in (".pb", ".onnx"):
                    candidates.append(str(entry))
        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                return candidate
        return None

    def load_engine(self, model_override: Optional[str] = None):
        if model_override:
            model_override = os.path.abspath(model_override)
            if not os.path.exists(model_override):
                raise HTTPException(503, f"El modelo de super resolución '{model_override}' no existe en el contenedor.")
            if self._engine is not None and self._model_path == model_override:
                return self._engine, self._scale
            self._engine = None
            self._model_path = None
            model_path = model_override
        else:
            if self._engine is not None:
                return self._engine, self._scale
            model_path = self._resolve_model_path()
        if self._factory is None:
            raise HTTPException(503, "cv2.dnn_superres no está disponible en este entorno (compila OpenCV con contrib).")
        if not model_path or not os.path.exists(model_path):
            raise HTTPException(503, "No se encontró el modelo de super resolución. Configura SUPERRES_MODEL_PATH o verifica data/networks/Super-Resolution-BSD500.")
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
            _, ext = os.path.splitext(model_path)
            if ext.lower() == ".onnx":
                raise HTTPException(
                    503,
                    f"No se pudo cargar el modelo ONNX ({model_path}). cv2.dnn_superres requiere pesos TensorFlow (.pb) "
                    "o una versión de OpenCV compilada con soporte ONNX para dnn_superres. "
                    "Convierte el modelo a .pb o especifica SUPERRES_MODEL_PATH apuntando a un archivo compatible. "
                    f"Detalle original: {exc}"
                )
            raise HTTPException(503, f"No se pudo cargar el modelo de super resolución en {model_path}: {exc}")
