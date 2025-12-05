"""
YOLO-Fastest Detector - Ultra-lightweight and fast object detection.
Uses OpenCV DNN backend for CPU inference.

Performance: ~12-15 FPS on CPU at 416x416
Model size: ~3.5 MB (weights)
"""

import cv2
import numpy as np
import os
import urllib.request
from typing import List, Tuple, Optional, Dict, Any

from .base import BaseDetector, DetectionResult


class YOLOFastestDetector(BaseDetector):
    """
    YOLO-Fastest detector using OpenCV DNN.
    Ultra-lightweight model optimized for real-time CPU inference.
    """
    
    # COCO class names (80 classes)
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
    
    # Resolution presets
    RESOLUTIONS = {
        'low': (320, 320),
        'medium': (416, 416),
        'high': (640, 640)
    }
    
    def __init__(self, resolution: str = 'medium', device: str = 'cpu', input_size: int = None):
        """
        Initialize YOLO-Fastest detector.
        
        Args:
            resolution: 'low' (320), 'medium' (416), or 'high' (640)
            device: Device to run on (only 'cpu' supported)
            input_size: Override input size (320, 416, or 640)
        """
        # Handle input_size override
        if input_size is not None:
            if input_size <= 320:
                self.resolution = 'low'
            elif input_size <= 416:
                self.resolution = 'medium'
            else:
                self.resolution = 'high'
        else:
            self.resolution = resolution.lower()
        
        if self.resolution not in self.RESOLUTIONS:
            self.resolution = 'medium'
        
        self.input_size = self.RESOLUTIONS[self.resolution]
        self.device = device
        self.net = None
        self.layer_names = None
        
        # Model paths
        self.models_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'models')
        self.cfg_path = os.path.join(self.models_dir, 'yolo-fastest-xl.cfg')
        self.weights_path = os.path.join(self.models_dir, 'yolo-fastest-xl.weights')
        
        # URLs for auto-download
        self.cfg_url = "https://raw.githubusercontent.com/dog-qiuqiu/Yolo-Fastest/master/ModelZoo/yolo-fastest-1.1_coco/yolo-fastest-1.1-xl.cfg"
        self.weights_url = "https://github.com/dog-qiuqiu/Yolo-Fastest/raw/master/ModelZoo/yolo-fastest-1.1_coco/yolo-fastest-1.1-xl.weights"
    
    def _download_file(self, url: str, path: str) -> bool:
        """Download file if it doesn't exist."""
        if os.path.exists(path):
            return True
        
        os.makedirs(os.path.dirname(path), exist_ok=True)
        print(f"[YOLO-Fastest] Downloading {os.path.basename(path)}...")
        
        try:
            urllib.request.urlretrieve(url, path)
            size_mb = os.path.getsize(path) / (1024 * 1024)
            print(f"[YOLO-Fastest] Downloaded: {size_mb:.1f} MB")
            return True
        except Exception as e:
            print(f"[YOLO-Fastest] Download failed: {e}")
            return False
    
    def load_model(self) -> None:
        """Load YOLO-Fastest model."""
        print(f"[YOLO-Fastest] Loading model (resolution: {self.resolution})...")
        
        # Download model files if needed
        if not self._download_file(self.cfg_url, self.cfg_path):
            raise FileNotFoundError(f"Could not download config file")
        if not self._download_file(self.weights_url, self.weights_path):
            raise FileNotFoundError(f"Could not download weights file")
        
        # Load network
        self.net = cv2.dnn.readNetFromDarknet(self.cfg_path, self.weights_path)
        
        # Set backend
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        
        # Get output layer names
        self.layer_names = self.net.getUnconnectedOutLayersNames()
        
        print(f"[YOLO-Fastest] Model loaded successfully (input: {self.input_size[0]}x{self.input_size[1]})")
    
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
            frame, 1/255.0, self.input_size,
            swapRB=True, crop=False
        )
        
        # Forward pass
        self.net.setInput(blob)
        outputs = self.net.forward(self.layer_names)
        
        # Process detections
        boxes = []
        confidences = []
        class_ids = []
        
        for output in outputs:
            for detection in output:
                scores = detection[5:]
                class_id = np.argmax(scores)
                confidence = scores[class_id]
                
                if confidence > confidence_threshold:
                    # Filter by class if specified
                    if classes is not None and class_id not in classes:
                        continue
                    
                    # Scale box to original image size
                    center_x = int(detection[0] * width)
                    center_y = int(detection[1] * height)
                    w = int(detection[2] * width)
                    h = int(detection[3] * height)
                    
                    x = int(center_x - w / 2)
                    y = int(center_y - h / 2)
                    
                    boxes.append([x, y, w, h])
                    confidences.append(float(confidence))
                    class_ids.append(class_id)
        
        # Apply NMS
        detections = []
        if boxes:
            indices = cv2.dnn.NMSBoxes(boxes, confidences, confidence_threshold, 0.4)
            
            for i in indices.flatten() if len(indices) > 0 else []:
                x, y, w, h = boxes[i]
                detections.append(DetectionResult(
                    class_id=class_ids[i],
                    class_name=self.COCO_CLASSES[class_ids[i]] if class_ids[i] < len(self.COCO_CLASSES) else f"class_{class_ids[i]}",
                    confidence=confidences[i],
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
    
    def set_resolution(self, resolution: str) -> None:
        """
        Change input resolution.
        
        Args:
            resolution: 'low', 'medium', or 'high'
        """
        if resolution.lower() in self.RESOLUTIONS:
            self.resolution = resolution.lower()
            self.input_size = self.RESOLUTIONS[self.resolution]
            print(f"[YOLO-Fastest] Resolution changed to {self.resolution} ({self.input_size[0]}x{self.input_size[1]})")
