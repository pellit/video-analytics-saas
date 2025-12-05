# Model abstraction layer for video analytics
# ===========================================
#
# Available Models (sorted by speed on CPU):
# ------------------------------------------
# ULTRA-FAST (>15 FPS):
#   - MOBILENET_SSD: ~25 FPS, 22MB - Fastest, MobileNet+SSD
#   - YOLO_FASTEST: ~15 FPS, 3.5MB - Fast + good detections (DEFAULT)
#
# FAST (5-15 FPS):
#   - MEDIAPIPE_OBJECT: ~9 FPS, 4.4MB - MediaPipe EfficientDet
#   - YOLOV4_TINY: ~7 FPS @320, 23MB - OpenCV DNN YOLOv4-tiny
#   - NANODET: ~6 FPS, 4.6MB - Ultra-lightweight ONNX
#
# ACCURATE (<5 FPS):
#   - ONNX: ~1 FPS, 23MB - YOLO-NAS high accuracy
#   - RT_DETR: ~0.3 FPS - Transformer, best accuracy
#
# Resolution Options:
#   - LOW: 320x320 - Fastest
#   - MEDIUM: 416x416 - Balanced (default)
#   - HIGH: 640x640 - Best accuracy
#
# Ultralytics disabled by default for legal reasons (AGPL-3.0)

from .base import BaseDetector, DetectionResult
from .factory import ModelFactory, ModelType, Resolution, get_detector, DEFAULT_MODEL, DEFAULT_RESOLUTION

__all__ = [
    'BaseDetector', 
    'DetectionResult', 
    'ModelFactory', 
    'ModelType', 
    'Resolution',
    'get_detector', 
    'DEFAULT_MODEL',
    'DEFAULT_RESOLUTION'
]
