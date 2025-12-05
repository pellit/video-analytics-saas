"""
Model Factory for creating detection model instances.
Provides a unified interface to select and instantiate detection models.

Available Models (sorted by speed on CPU):
==========================================
ULTRA-FAST (>15 FPS):
- MOBILENET_SSD: ~25 FPS, 22MB - Fastest, limited classes (VOC)
- YOLO_FASTEST: ~12-15 FPS, 3.5MB - Fast + many detections

FAST (5-15 FPS):
- MEDIAPIPE_OBJECT: ~9 FPS, 4.4MB - Good balance
- YOLOV4_TINY: ~7 FPS @320, 23MB - OpenCV DNN
- NANODET: ~6 FPS, 4.6MB - Ultra-lightweight ONNX

ACCURATE (1-5 FPS):
- ONNX_YOLONAS: ~0.9 FPS, 23MB - High accuracy
- RT_DETR: ~0.3 FPS - Transformer-based, best accuracy

Resolution Options (for applicable models):
- LOW: 320x320 - Fastest
- MEDIUM: 416x416 - Balanced (default)
- HIGH: 640x640 - Best accuracy
"""

import os
from typing import Optional, Type, Dict
from enum import Enum

from .base import BaseDetector


class ModelType(str, Enum):
    """Available model types."""
    # Ultra-fast models (>15 FPS)
    MOBILENET_SSD = "mobilenet_ssd"    # ~25 FPS - Fastest
    YOLO_FASTEST = "yolo_fastest"       # ~12-15 FPS - Fast + good detection
    
    # Fast models (5-15 FPS)
    MEDIAPIPE_OBJECT = "mediapipe"      # ~9 FPS - MediaPipe EfficientDet
    YOLOV4_TINY = "yolov4_tiny"         # ~7 FPS @320 - OpenCV DNN
    NANODET = "nanodet"                 # ~6 FPS - Ultra-lightweight ONNX
    
    # Accurate models (<5 FPS)
    ONNX = "onnx"                        # ~0.9 FPS - YOLO-NAS ONNX
    RT_DETR = "rt_detr"                  # ~0.3 FPS - Transformer (best accuracy)
    
    # Restricted
    ULTRALYTICS = "ultralytics"          # DISABLED by default (AGPL-3.0)


class Resolution(str, Enum):
    """Input resolution options."""
    LOW = "low"        # 320x320 - Fastest
    MEDIUM = "medium"  # 416x416 - Balanced
    HIGH = "high"      # 640x640 - Best accuracy


# Default model - YOLO-Fastest for best balance of speed/accuracy
DEFAULT_MODEL = ModelType.YOLO_FASTEST
DEFAULT_RESOLUTION = Resolution.MEDIUM


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
    def _get_resolution_size(cls, resolution: Resolution = None) -> int:
        """Convert resolution enum to pixel size."""
        if resolution is None:
            resolution = DEFAULT_RESOLUTION
        return {
            Resolution.LOW: 320,
            Resolution.MEDIUM: 416,
            Resolution.HIGH: 640,
        }.get(resolution, 416)
    
    @classmethod
    def create(
        cls,
        model_type: ModelType = None,
        model_path: Optional[str] = None,
        device: str = 'auto',
        resolution: Resolution = None
    ) -> BaseDetector:
        """
        Create a detector instance.
        
        Args:
            model_type: Type of model to create (default: YOLO_FASTEST)
            model_path: Path to model weights or model name
            device: Device to run on ('auto', 'cpu', 'cuda')
            resolution: Input resolution (LOW=320, MEDIUM=416, HIGH=640)
            
        Returns:
            Initialized detector instance
        """
        if model_type is None:
            model_type = DEFAULT_MODEL
        
        if resolution is None:
            resolution = DEFAULT_RESOLUTION
        
        input_size = cls._get_resolution_size(resolution)
        
        # Convert string to enum if needed
        if isinstance(model_type, str):
            try:
                model_type = ModelType(model_type.lower())
            except ValueError:
                # Fallback: map old names to new
                model_type_map = {
                    'yolo_nas_s': ModelType.ONNX,
                    'yolo_nas_m': ModelType.ONNX,
                    'yolo_nas_l': ModelType.ONNX,
                    'yolo_nas': ModelType.ONNX,
                    'yolov4': ModelType.YOLOV4_TINY,
                    'yolov4_tiny': ModelType.YOLOV4_TINY,
                    'opencv': ModelType.YOLOV4_TINY,
                    'nanodet': ModelType.NANODET,
                    'nanodet_plus': ModelType.NANODET,
                    'mobilenet': ModelType.MOBILENET_SSD,
                    'mobilenet_ssd': ModelType.MOBILENET_SSD,
                    'yolo_fastest': ModelType.YOLO_FASTEST,
                    'fastest': ModelType.YOLO_FASTEST,
                    'mediapipe': ModelType.MEDIAPIPE_OBJECT,
                    'mediapipe_object': ModelType.MEDIAPIPE_OBJECT,
                }
                model_type = model_type_map.get(model_type.lower(), DEFAULT_MODEL)
        
        print(f"[ModelFactory] Creating {model_type.value} with resolution {resolution.value} ({input_size}px)")
        
        # ===== ULTRA-FAST MODELS (>15 FPS) =====
        
        if model_type == ModelType.MOBILENET_SSD:
            try:
                from .mobilenet_ssd import MobileNetSSDDetector
                return MobileNetSSDDetector(device=device, input_size=input_size)
            except Exception as e:
                print(f"[ModelFactory] MobileNet-SSD not available: {e}")
                print("[ModelFactory] Falling back to YOLO-Fastest...")
                model_type = ModelType.YOLO_FASTEST
        
        if model_type == ModelType.YOLO_FASTEST:
            try:
                from .yolo_fastest import YOLOFastestDetector
                return YOLOFastestDetector(device=device, input_size=input_size)
            except Exception as e:
                print(f"[ModelFactory] YOLO-Fastest not available: {e}")
                print("[ModelFactory] Falling back to MediaPipe Object...")
                model_type = ModelType.MEDIAPIPE_OBJECT
        
        # ===== FAST MODELS (5-15 FPS) =====
        
        if model_type == ModelType.MEDIAPIPE_OBJECT:
            try:
                from .mediapipe_object import MediaPipeObjectDetector
                return MediaPipeObjectDetector(device=device)
            except Exception as e:
                print(f"[ModelFactory] MediaPipe Object not available: {e}")
                print("[ModelFactory] Falling back to YOLOv4-tiny...")
                model_type = ModelType.YOLOV4_TINY
        
        if model_type == ModelType.YOLOV4_TINY:
            try:
                from .opencv_yolov4_tiny import OpenCVYOLOv4TinyDetector
                return OpenCVYOLOv4TinyDetector(device=device, input_size=input_size)
            except Exception as e:
                print(f"[ModelFactory] YOLOv4-tiny not available: {e}")
                print("[ModelFactory] Falling back to NanoDet-Plus...")
                model_type = ModelType.NANODET
        
        if model_type == ModelType.NANODET:
            try:
                from .nanodet_plus import NanoDetPlusDetector
                # NanoDet uses fixed 416x416 input
                return NanoDetPlusDetector(device=device)
            except Exception as e:
                print(f"[ModelFactory] NanoDet-Plus not available: {e}")
                print("[ModelFactory] Falling back to ONNX YOLO-NAS...")
                model_type = ModelType.ONNX
        
        # ===== ACCURATE MODELS (<5 FPS) =====
        
        if model_type == ModelType.ONNX:
            try:
                from .onnx_yolonas import ONNXYOLONASDetector
                return ONNXYOLONASDetector(model_path=model_path, device=device)
            except (FileNotFoundError, ImportError) as e:
                print(f"[ModelFactory] ONNX model not available: {e}")
                print("[ModelFactory] Falling back to RT-DETR...")
                model_type = ModelType.RT_DETR
        
        if model_type == ModelType.RT_DETR:
            from .rt_detr import RTDETRDetector
            return RTDETRDetector(model_name=model_path, device=device)
        
        # ===== RESTRICTED MODELS =====
        
        if model_type == ModelType.ULTRALYTICS:
            # Check if enabled
            if os.environ.get('ENABLE_ULTRALYTICS', 'false').lower() != 'true':
                raise RuntimeError(
                    "Ultralytics is DISABLED for legal reasons (AGPL-3.0 license). "
                    "Set ENABLE_ULTRALYTICS=true to enable for TESTING ONLY. "
                    "For production, use YOLO-NAS (Apache 2.0) or RT-DETR."
                )
            from .ultralytics_yolo import UltralyticsDetector
            return UltralyticsDetector(model_path=model_path, device=device)
        
        raise ValueError(f"Unknown model type: {model_type}")
    
    @classmethod
    def from_env(cls, device: str = 'auto') -> BaseDetector:
        """
        Create detector from environment variables.
        
        Environment variables:
            DETECTION_MODEL: Model type (see ModelType enum)
            DETECTION_RESOLUTION: Resolution ('low', 'medium', 'high')
            DETECTION_MODEL_PATH: Path to model weights (optional)
            ENABLE_ULTRALYTICS: 'true' to enable ultralytics (testing only)
        """
        model_type_str = os.environ.get('DETECTION_MODEL', DEFAULT_MODEL.value)
        resolution_str = os.environ.get('DETECTION_RESOLUTION', DEFAULT_RESOLUTION.value)
        model_path = os.environ.get('DETECTION_MODEL_PATH', '').strip() or None
        
        # Parse resolution
        try:
            resolution = Resolution(resolution_str.lower())
        except ValueError:
            print(f"[ModelFactory] Unknown resolution '{resolution_str}', using default: {DEFAULT_RESOLUTION.value}")
            resolution = DEFAULT_RESOLUTION
        
        # Only use ONNX if explicitly requested
        if model_type_str.lower() in ['onnx', 'yolo_nas', 'yolo_nas_s', 'yolo_nas_m', 'yolo_nas_l']:
            # Check if ONNX model file exists
            onnx_paths = [
                model_path,
                "yolo_nas_s.onnx",
                "models/yolo_nas_s.onnx",
                "/app/models/yolo_nas_s.onnx",
            ]
            onnx_found = any(p and os.path.exists(p) for p in onnx_paths if p)
            if onnx_found:
                print("[ModelFactory] ONNX model requested and found - using ONNX runtime")
                return cls.create(model_type=ModelType.ONNX, model_path=model_path, device=device, resolution=resolution)
        
        try:
            model_type = ModelType(model_type_str.lower())
        except ValueError:
            print(f"[ModelFactory] Unknown model type '{model_type_str}', using default: {DEFAULT_MODEL.value}")
            model_type = DEFAULT_MODEL
        
        return cls.create(model_type=model_type, model_path=model_path, device=device, resolution=resolution)
    
    @classmethod
    def list_available_models(cls) -> Dict[str, Dict]:
        """
        List all available models with their details.
        
        Returns:
            Dict with model info including license and status
        """
        return {
            # ULTRA-FAST (>15 FPS)
            ModelType.MOBILENET_SSD.value: {
                'name': 'MobileNet-SSD',
                'library': 'OpenCV DNN (Caffe)',
                'license': 'Apache 2.0',
                'status': 'ENABLED (🚀 ~25 FPS - FASTEST)',
                'fps': '~25 FPS',
                'size': '22MB',
                'description': 'Fastest detector. Uses MobileNet backbone with SSD. Good for real-time tracking.'
            },
            ModelType.YOLO_FASTEST.value: {
                'name': 'YOLO-Fastest',
                'library': 'OpenCV DNN',
                'license': 'MIT',
                'status': 'ENABLED (⚡ DEFAULT ~15 FPS)',
                'fps': '~15 FPS @416',
                'size': '3.5MB',
                'description': 'Ultra-fast YOLO variant. Best balance of speed and detection quality.'
            },
            # FAST (5-15 FPS)
            ModelType.MEDIAPIPE_OBJECT.value: {
                'name': 'MediaPipe Object Detection',
                'library': 'MediaPipe',
                'license': 'Apache 2.0',
                'status': 'ENABLED (~9 FPS)',
                'fps': '~9 FPS @320',
                'size': '4.4MB',
                'description': 'Google MediaPipe EfficientDet-Lite0. Lightweight and efficient.'
            },
            ModelType.YOLOV4_TINY.value: {
                'name': 'OpenCV YOLOv4-tiny',
                'library': 'OpenCV DNN',
                'license': 'MIT/Apache 2.0',
                'status': 'ENABLED (~7 FPS @320)',
                'fps': '~7 FPS @320',
                'size': '23MB',
                'description': 'Classic YOLOv4-tiny. Good detection quality, moderate speed.'
            },
            ModelType.NANODET.value: {
                'name': 'NanoDet-Plus',
                'library': 'onnxruntime',
                'license': 'Apache 2.0',
                'status': 'ENABLED (~6 FPS, ultra-lightweight)',
                'fps': '~6 FPS (fixed 416px)',
                'size': '4.6MB',
                'description': 'Ultra-lightweight detector. Great for embedded/edge devices.'
            },
            # ACCURATE (<5 FPS)
            ModelType.ONNX.value: {
                'name': 'YOLO-NAS ONNX',
                'library': 'onnxruntime',
                'license': 'Apache 2.0',
                'status': 'ENABLED (~1 FPS - HIGH ACCURACY)',
                'fps': '~1 FPS',
                'size': '23MB',
                'description': 'ONNX optimized YOLO-NAS. High accuracy but slower on CPU.'
            },
            ModelType.RT_DETR.value: {
                'name': 'RT-DETR',
                'library': 'transformers',
                'license': 'Apache 2.0',
                'status': 'ENABLED (~0.3 FPS - BEST ACCURACY)',
                'fps': '~0.3 FPS',
                'size': 'Large',
                'description': 'Real-Time Detection Transformer. Best accuracy but very slow on CPU.'
            },
            # RESTRICTED
            ModelType.ULTRALYTICS.value: {
                'name': 'Ultralytics YOLO',
                'library': 'ultralytics',
                'license': 'AGPL-3.0 (⚠️ RESTRICTED)',
                'status': 'DISABLED by default',
                'fps': 'Varies',
                'size': 'Varies',
                'description': 'Original YOLOv8. AGPL license requires open-sourcing for production.'
            }
        }


def get_detector(
    model_type: str = None,
    model_path: str = None,
    device: str = 'auto',
    resolution: str = None
) -> BaseDetector:
    """
    Convenience function to get a detector instance.
    
    Args:
        model_type: Model type (see ModelType enum values)
        model_path: Path to model weights (optional)
        device: Device to run on (default: auto)
        resolution: Input resolution ('low', 'medium', 'high')
        
    Returns:
        Initialized detector instance
    """
    res = None
    if resolution:
        try:
            res = Resolution(resolution.lower())
        except ValueError:
            res = None
    
    if model_type:
        return ModelFactory.create(
            model_type=ModelType(model_type.lower()),
            model_path=model_path,
            device=device,
            resolution=res
        )
    return ModelFactory.from_env(device=device)
