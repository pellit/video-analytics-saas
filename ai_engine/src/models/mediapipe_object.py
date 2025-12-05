"""
MediaPipe Object Detection - Lightweight object detection using MediaPipe.
Uses EfficientDet-Lite0 INT8 quantized model.

Performance: ~9 FPS on CPU
Model size: ~4.4 MB
Best for: General object detection with good accuracy
"""

import cv2
import numpy as np
import os
import urllib.request
from typing import List, Tuple, Optional, Dict, Any

from .base import BaseDetector, DetectionResult


class MediaPipeObjectDetector(BaseDetector):
    """
    MediaPipe Object Detector using EfficientDet-Lite0.
    Good balance of speed and accuracy for general object detection.
    """
    
    # COCO class names (subset used by EfficientDet-Lite)
    COCO_CLASSES = [
        "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
        "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat",
        "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack",
        "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball",
        "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
        "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
        "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
        "couch", "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
        "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
        "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush"
    ]
    
    def __init__(self, device: str = 'cpu'):
        """
        Initialize MediaPipe Object Detector.
        
        Args:
            device: Device to run on (only 'cpu' supported)
        """
        self.device = device
        self.detector = None
        
        # Model path
        self.models_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'models')
        self.model_path = os.path.join(self.models_dir, 'efficientdet_lite0.tflite')
        
        # URL for auto-download
        self.model_url = "https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/int8/latest/efficientdet_lite0.tflite"
    
    def _download_file(self, url: str, path: str) -> bool:
        """Download file if it doesn't exist."""
        if os.path.exists(path):
            return True
        
        os.makedirs(os.path.dirname(path), exist_ok=True)
        print(f"[MediaPipe-Object] Downloading model...")
        
        try:
            urllib.request.urlretrieve(url, path)
            size_mb = os.path.getsize(path) / (1024 * 1024)
            print(f"[MediaPipe-Object] Downloaded: {size_mb:.1f} MB")
            return True
        except Exception as e:
            print(f"[MediaPipe-Object] Download failed: {e}")
            return False
    
    def load_model(self) -> None:
        """Load MediaPipe Object Detection model."""
        print(f"[MediaPipe-Object] Loading model...")
        
        # Download model if needed
        if not self._download_file(self.model_url, self.model_path):
            raise FileNotFoundError(f"Could not download model file")
        
        try:
            import mediapipe as mp
            from mediapipe.tasks import python
            from mediapipe.tasks.python import vision
            
            base_options = python.BaseOptions(model_asset_path=self.model_path)
            options = vision.ObjectDetectorOptions(
                base_options=base_options,
                score_threshold=0.3,
                max_results=50
            )
            self.detector = vision.ObjectDetector.create_from_options(options)
            self.mp = mp
            
            print(f"[MediaPipe-Object] Model loaded successfully")
        except ImportError:
            raise ImportError("MediaPipe not installed. Run: pip install mediapipe")
    
    def detect(
        self,
        frame: np.ndarray,
        confidence_threshold: float = 0.5,
        classes: Optional[List[int]] = None
    ) -> Tuple[List[DetectionResult], np.ndarray]:
        """
        Detect objects in frame.
        
        Args:
            frame: BGR image
            confidence_threshold: Minimum confidence threshold
            classes: List of class IDs to detect (None = all)
            
        Returns:
            Tuple of (detections, annotated_frame)
        """
        if self.detector is None:
            self.load_model()
        
        height, width = frame.shape[:2]
        
        # Convert BGR to RGB for MediaPipe
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb_frame)
        
        # Detect
        result = self.detector.detect(mp_image)
        
        # Process detections
        detections = []
        
        for detection in result.detections:
            # Get category
            category = detection.categories[0]
            confidence = category.score
            
            if confidence < confidence_threshold:
                continue
            
            # Try to map category name to class ID
            class_name = category.category_name
            try:
                class_id = self.COCO_CLASSES.index(class_name.lower())
            except ValueError:
                class_id = category.index if category.index is not None else 0
            
            # Filter by class if specified
            if classes is not None and class_id not in classes:
                continue
            
            # Get bounding box
            bbox = detection.bounding_box
            x = bbox.origin_x
            y = bbox.origin_y
            w = bbox.width
            h = bbox.height
            
            detections.append(DetectionResult(
                class_id=class_id,
                class_name=class_name,
                confidence=float(confidence),
                bbox=(x, y, w, h),
                track_id=None
            ))
        
        # Draw detections
        annotated = self.draw_modern_detection(frame.copy(), detections)
        
        return detections, annotated
    
    def track(
        self,
        frame: np.ndarray,
        confidence_threshold: float = 0.5,
        classes: Optional[List[int]] = None
    ) -> Tuple[List[DetectionResult], np.ndarray]:
        """Track objects (same as detect for this model)."""
        return self.detect(frame, confidence_threshold, classes)
    
    def get_class_names(self) -> List[str]:
        """Get list of class names."""
        return self.COCO_CLASSES
