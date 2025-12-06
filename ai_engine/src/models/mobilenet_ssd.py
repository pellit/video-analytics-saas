"""
MobileNet-SSD Detector - Ultra-fast lightweight object detection.
Uses OpenCV DNN backend with Caffe model.

Performance: ~20-25 FPS on CPU
Model size: ~22 MB
Best for: Real-time streaming where speed is critical
"""

import cv2
import numpy as np
import os
import urllib.request
from typing import List, Tuple, Optional, Dict, Any

from .base import BaseDetector, DetectionResult


class MobileNetSSDDetector(BaseDetector):
    """
    MobileNet-SSD detector using OpenCV DNN.
    Fastest model for real-time detection, trades accuracy for speed.
    """
    
    # VOC class names (21 classes including background)
    VOC_CLASSES = [
        "background", "aeroplane", "bicycle", "bird", "boat", "bottle", "bus", "car",
        "cat", "chair", "cow", "diningtable", "dog", "horse", "motorbike", "person",
        "pottedplant", "sheep", "sofa", "train", "tvmonitor"
    ]
    
    # Map VOC to COCO-like IDs for compatibility
    VOC_TO_COCO = {
        1: 4,    # aeroplane -> airplane
        2: 1,    # bicycle
        3: 14,   # bird
        4: 8,    # boat
        5: 39,   # bottle
        6: 5,    # bus
        7: 2,    # car
        8: 15,   # cat
        9: 56,   # chair
        10: 19,  # cow
        11: 60,  # diningtable -> dining table
        12: 16,  # dog
        13: 17,  # horse
        14: 3,   # motorbike -> motorcycle
        15: 0,   # person
        16: 58,  # pottedplant -> potted plant
        17: 18,  # sheep
        18: 57,  # sofa -> couch
        19: 6,   # train
        20: 62,  # tvmonitor -> tv
    }
    
    def __init__(self, device: str = 'cpu', input_size: int = None):
        """
        Initialize MobileNet-SSD detector.
        
        Args:
            device: Device to run on (only 'cpu' supported)
            input_size: Ignored - MobileNet-SSD uses fixed 300x300 input
        """
        self.device = device
        self.net = None
        self.input_size = (300, 300)  # Fixed input size for MobileNet-SSD
        
        # Model paths
        self.models_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'models')
        self.prototxt_path = os.path.join(self.models_dir, 'MobileNetSSD_deploy.prototxt')
        self.model_path = os.path.join(self.models_dir, 'MobileNetSSD_deploy.caffemodel')
        
        # URLs for auto-download
        self.prototxt_url = "https://raw.githubusercontent.com/chuanqi305/MobileNet-SSD/master/deploy.prototxt"
        self.model_url = "https://github.com/chuanqi305/MobileNet-SSD/raw/master/mobilenet_iter_73000.caffemodel"
    
    def _download_file(self, url: str, path: str) -> bool:
        """Download file if it doesn't exist."""
        if os.path.exists(path):
            return True
        
        os.makedirs(os.path.dirname(path), exist_ok=True)
        print(f"[MobileNet-SSD] Downloading {os.path.basename(path)}...")
        
        try:
            urllib.request.urlretrieve(url, path)
            size_mb = os.path.getsize(path) / (1024 * 1024)
            print(f"[MobileNet-SSD] Downloaded: {size_mb:.1f} MB")
            return True
        except Exception as e:
            print(f"[MobileNet-SSD] Download failed: {e}")
            return False
    
    def load_model(self) -> None:
        """Load MobileNet-SSD model."""
        print(f"[MobileNet-SSD] Loading model...")
        
        # Download model files if needed
        if not self._download_file(self.prototxt_url, self.prototxt_path):
            raise FileNotFoundError(f"Could not download prototxt file")
        if not self._download_file(self.model_url, self.model_path):
            raise FileNotFoundError(f"Could not download model file")
        
        # Load network
        self.net = cv2.dnn.readNetFromCaffe(self.prototxt_path, self.model_path)
        
        # Set backend
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        
        print(f"[MobileNet-SSD] Model loaded successfully (input: 300x300)")
    
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
        if self.net is None:
            self.load_model()
        
        height, width = frame.shape[:2]
        
        # Create blob
        blob = cv2.dnn.blobFromImage(
            frame, 0.007843, self.input_size, 127.5
        )
        
        # Forward pass
        self.net.setInput(blob)
        output = self.net.forward()
        
        # Process detections
        detections = []
        
        for i in range(output.shape[2]):
            confidence = output[0, 0, i, 2]
            
            if confidence > confidence_threshold:
                class_id = int(output[0, 0, i, 1])
                
                # Skip background
                if class_id == 0:
                    continue
                
                # Map to COCO-like ID if filtering
                coco_id = self.VOC_TO_COCO.get(class_id, class_id)
                if classes is not None and coco_id not in classes:
                    continue
                
                # Get bounding box
                x1 = int(output[0, 0, i, 3] * width)
                y1 = int(output[0, 0, i, 4] * height)
                x2 = int(output[0, 0, i, 5] * width)
                y2 = int(output[0, 0, i, 6] * height)
                
                # Clamp to frame bounds
                x1 = max(0, x1)
                y1 = max(0, y1)
                x2 = min(width, x2)
                y2 = min(height, y2)
                
                detections.append(DetectionResult(
                    class_id=coco_id,
                    class_name=self.VOC_CLASSES[class_id] if class_id < len(self.VOC_CLASSES) else f"class_{class_id}",
                    confidence=float(confidence),
                    bbox=(x1, y1, x2, y2),  # x1, y1, x2, y2 format
                    track_id=None
                ))
        
        # Draw detections
        annotated = frame.copy()
        for det in detections:
            self.draw_modern_detection(annotated, det)
        
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
        return self.VOC_CLASSES[1:]  # Exclude background
