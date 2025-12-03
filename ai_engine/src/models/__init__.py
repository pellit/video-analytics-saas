# Model abstraction layer for video analytics
# Supports: ONNX (fastest), YOLO-NAS, RT-DETR, ultralytics (disabled by default for legal reasons)

from .base import BaseDetector, DetectionResult
from .factory import ModelFactory, ModelType, get_detector

__all__ = ['BaseDetector', 'DetectionResult', 'ModelFactory', 'ModelType', 'get_detector']
