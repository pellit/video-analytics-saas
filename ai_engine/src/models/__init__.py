# Model abstraction layer for video analytics
# Supports: YOLO-NAS (default), RT-DETR, ultralytics (disabled by default for legal reasons)

from .base import BaseDetector, DetectionResult
from .factory import ModelFactory, get_detector

__all__ = ['BaseDetector', 'DetectionResult', 'ModelFactory', 'get_detector']
