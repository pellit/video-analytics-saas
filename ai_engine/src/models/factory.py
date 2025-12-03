"""
Model Factory for creating detection model instances.
Provides a unified interface to select and instantiate detection models.
"""

import os
from typing import Optional, Type, Dict
from enum import Enum

from .base import BaseDetector


class ModelType(str, Enum):
    """Available model types."""
    ONNX = "onnx"              # ONNX Runtime - FASTEST for CPU (recommended)
    YOLO_NAS = "yolo_nas"      # super-gradients, Apache 2.0 license
    RT_DETR = "rt_detr"        # HuggingFace transformers
    ULTRALYTICS = "ultralytics" # DISABLED by default (AGPL-3.0)


# Default model to use - ONNX is fastest for CPU
DEFAULT_MODEL = ModelType.ONNX


class ModelFactory:
    """
    Factory class for creating detection model instances.
    
    Usage:
        # Get default model (YOLO-NAS)
        detector = ModelFactory.create()
        
        # Get specific model
        detector = ModelFactory.create(ModelType.RT_DETR)
        
        # Get model from environment variable
        detector = ModelFactory.from_env()
    """
    
    _registry: Dict[ModelType, Type[BaseDetector]] = {}
    
    @classmethod
    def register(cls, model_type: ModelType, detector_class: Type[BaseDetector]):
        """Register a detector class for a model type."""
        cls._registry[model_type] = detector_class
    
    @classmethod
    def create(
        cls,
        model_type: ModelType = None,
        model_path: Optional[str] = None,
        device: str = 'auto'
    ) -> BaseDetector:
        """
        Create a detector instance.
        
        Args:
            model_type: Type of model to create (default: YOLO_NAS)
            model_path: Path to model weights or model name
            device: Device to run on ('auto', 'cpu', 'cuda')
            
        Returns:
            Initialized detector instance
        """
        if model_type is None:
            model_type = DEFAULT_MODEL
        
        # Convert string to enum if needed
        if isinstance(model_type, str):
            try:
                model_type = ModelType(model_type.lower())
            except ValueError:
                # Fallback: map old names to new
                model_type_map = {
                    'yolo_nas_s': ModelType.ONNX,
                    'yolo_nas_m': ModelType.YOLO_NAS,
                    'yolo_nas_l': ModelType.YOLO_NAS,
                }
                model_type = model_type_map.get(model_type.lower(), DEFAULT_MODEL)
        
        # Lazy import to avoid loading all models
        if model_type == ModelType.ONNX:
            try:
                from .onnx_yolonas import ONNXYOLONASDetector
                return ONNXYOLONASDetector(model_path=model_path, device=device)
            except (FileNotFoundError, ImportError) as e:
                print(f"[ModelFactory] ONNX model not available: {e}")
                print("[ModelFactory] Falling back to RT-DETR...")
                from .rt_detr import RTDETRDetector
                return RTDETRDetector(model_name=model_path, device=device)
        
        elif model_type == ModelType.YOLO_NAS:
            try:
                from .yolo_nas import YOLONASDetector
                return YOLONASDetector(model_name=model_path, device=device)
            except ImportError as e:
                print(f"[ModelFactory] YOLO-NAS not available: {e}")
                print("[ModelFactory] Falling back to RT-DETR...")
                from .rt_detr import RTDETRDetector
                return RTDETRDetector(model_name=model_path, device=device)
        
        elif model_type == ModelType.RT_DETR:
            from .rt_detr import RTDETRDetector
            return RTDETRDetector(model_name=model_path, device=device)
        
        elif model_type == ModelType.ULTRALYTICS:
            # Check if enabled
            if os.environ.get('ENABLE_ULTRALYTICS', 'false').lower() != 'true':
                raise RuntimeError(
                    "Ultralytics is DISABLED for legal reasons (AGPL-3.0 license). "
                    "Set ENABLE_ULTRALYTICS=true to enable for TESTING ONLY. "
                    "For production, use YOLO-NAS (Apache 2.0) or RT-DETR."
                )
            from .ultralytics_yolo import UltralyticsDetector
            return UltralyticsDetector(model_path=model_path, device=device)
        
        else:
            raise ValueError(f"Unknown model type: {model_type}")
    
    @classmethod
    def from_env(cls, device: str = 'auto') -> BaseDetector:
        """
        Create detector from environment variables.
        
        Environment variables:
            DETECTION_MODEL: Model type ('onnx', 'yolo_nas', 'rt_detr', 'ultralytics')
            DETECTION_MODEL_PATH: Path to model weights (optional)
            ENABLE_ULTRALYTICS: 'true' to enable ultralytics (testing only)
        """
        model_type_str = os.environ.get('DETECTION_MODEL', DEFAULT_MODEL.value)
        model_path = os.environ.get('DETECTION_MODEL_PATH', '').strip() or None
        
        # Check for ONNX model file first (highest priority)
        onnx_paths = [
            model_path,
            "yolo_nas_s.onnx",
            "models/yolo_nas_s.onnx",
            "/app/models/yolo_nas_s.onnx",
        ]
        
        onnx_found = any(p and os.path.exists(p) for p in onnx_paths if p)
        
        # If ONNX file exists and no specific model type is set, use ONNX
        if onnx_found and model_type_str in ['onnx', 'yolo_nas', DEFAULT_MODEL.value]:
            print("[ModelFactory] ONNX model found - using optimized ONNX runtime")
            return cls.create(model_type=ModelType.ONNX, model_path=model_path, device=device)
        
        try:
            model_type = ModelType(model_type_str.lower())
        except ValueError:
            print(f"[ModelFactory] Unknown model type '{model_type_str}', using default: {DEFAULT_MODEL.value}")
            model_type = DEFAULT_MODEL
        
        # Default to yolo_nas_s for YOLO-NAS if no path specified
        if model_type == ModelType.YOLO_NAS and model_path is None:
            model_path = 'yolo_nas_s'
            print(f"[ModelFactory] Using default model: yolo_nas_s")
        
        return cls.create(model_type=model_type, model_path=model_path, device=device)
    
    @classmethod
    def list_available_models(cls) -> Dict[str, Dict]:
        """
        List all available models with their details.
        
        Returns:
            Dict with model info including license and status
        """
        return {
            ModelType.ONNX.value: {
                'name': 'YOLO-NAS ONNX',
                'library': 'onnxruntime',
                'license': 'Apache 2.0',
                'status': 'ENABLED (⚡ FASTEST - Recommended for CPU)',
                'variants': ['yolo_nas_s.onnx', 'yolo_nas_m.onnx', 'yolo_nas_l.onnx'],
                'description': 'ONNX optimized YOLO-NAS. 2-3x faster than PyTorch on CPU. Smallest Docker image.'
            },
            ModelType.YOLO_NAS.value: {
                'name': 'YOLO-NAS',
                'library': 'super-gradients',
                'license': 'Apache 2.0',
                'status': 'ENABLED',
                'variants': ['yolo_nas_s', 'yolo_nas_m', 'yolo_nas_l'],
                'description': 'State-of-the-art YOLO model by Deci AI. Requires super-gradients library.'
            },
            ModelType.RT_DETR.value: {
                'name': 'RT-DETR',
                'library': 'transformers',
                'license': 'Apache 2.0',
                'status': 'ENABLED',
                'variants': ['PekingU/rtdetr_r50vd', 'PekingU/rtdetr_r101vd'],
                'description': 'Real-Time Detection Transformer. Transformer-based architecture with excellent accuracy.'
            },
            ModelType.ULTRALYTICS.value: {
                'name': 'Ultralytics YOLO',
                'library': 'ultralytics',
                'license': 'AGPL-3.0 (⚠️ RESTRICTED)',
                'status': 'DISABLED by default',
                'variants': ['yolov8n.pt', 'yolov8s.pt', 'yolov8m.pt', 'yolov8l.pt', 'yolov8x.pt'],
                'description': 'Original YOLOv8. AGPL license requires open-sourcing or commercial license for production use.'
            }
        }


def get_detector(
    model_type: str = None,
    model_path: str = None,
    device: str = 'auto'
) -> BaseDetector:
    """
    Convenience function to get a detector instance.
    
    Args:
        model_type: 'yolo_nas', 'rt_detr', or 'ultralytics' (default: yolo_nas)
        model_path: Path to model weights (optional)
        device: Device to run on (default: auto)
        
    Returns:
        Initialized detector instance
    """
    if model_type:
        return ModelFactory.create(
            model_type=ModelType(model_type.lower()),
            model_path=model_path,
            device=device
        )
    return ModelFactory.from_env(device=device)
