"""
OpenCV DNN YOLOv4-tiny Detector.
Ultra-fast inference on CPU using OpenCV's DNN module.
Best performance for CPU-only environments.
"""

import os
import cv2
import numpy as np
import urllib.request
from typing import List, Tuple, Optional

from .base import BaseDetector, DetectionResult


# COCO class names (80 classes)
COCO_CLASSES = {
    0: 'person', 1: 'bicycle', 2: 'car', 3: 'motorcycle', 4: 'airplane',
    5: 'bus', 6: 'train', 7: 'truck', 8: 'boat', 9: 'traffic light',
    10: 'fire hydrant', 11: 'stop sign', 12: 'parking meter', 13: 'bench',
    14: 'bird', 15: 'cat', 16: 'dog', 17: 'horse', 18: 'sheep', 19: 'cow',
    20: 'elephant', 21: 'bear', 22: 'zebra', 23: 'giraffe', 24: 'backpack',
    25: 'umbrella', 26: 'handbag', 27: 'tie', 28: 'suitcase', 29: 'frisbee',
    30: 'skis', 31: 'snowboard', 32: 'sports ball', 33: 'kite',
    34: 'baseball bat', 35: 'baseball glove', 36: 'skateboard', 37: 'surfboard',
    38: 'tennis racket', 39: 'bottle', 40: 'wine glass', 41: 'cup',
    42: 'fork', 43: 'knife', 44: 'spoon', 45: 'bowl', 46: 'banana',
    47: 'apple', 48: 'sandwich', 49: 'orange', 50: 'broccoli', 51: 'carrot',
    52: 'hot dog', 53: 'pizza', 54: 'donut', 55: 'cake', 56: 'chair',
    57: 'couch', 58: 'potted plant', 59: 'bed', 60: 'dining table',
    61: 'toilet', 62: 'tv', 63: 'laptop', 64: 'mouse', 65: 'remote',
    66: 'keyboard', 67: 'cell phone', 68: 'microwave', 69: 'oven',
    70: 'toaster', 71: 'sink', 72: 'refrigerator', 73: 'book', 74: 'clock',
    75: 'vase', 76: 'scissors', 77: 'teddy bear', 78: 'hair drier',
    79: 'toothbrush'
}


class OpenCVYOLOv4TinyDetector(BaseDetector):
    """
    OpenCV DNN YOLOv4-tiny detector.
    
    This is the FASTEST option for CPU inference:
    - Uses OpenCV's optimized DNN module
    - ~7 FPS on CPU (vs 2.3 FPS for ONNX YOLO-NAS)
    - Small model size (~23 MB)
    - No PyTorch/TensorFlow dependency
    """
    
    WEIGHTS_URL = "https://github.com/AlexeyAB/darknet/releases/download/darknet_yolo_v4_pre/yolov4-tiny.weights"
    CONFIG_URL = "https://raw.githubusercontent.com/AlexeyAB/darknet/master/cfg/yolov4-tiny.cfg"
    
    def __init__(
        self,
        model_path: Optional[str] = None,
        input_size: int = 416,
        device: str = 'cpu'
    ):
        """
        Initialize OpenCV YOLOv4-tiny detector.
        
        Args:
            model_path: Path to weights file. If None, downloads automatically.
            input_size: Model input size (416 or 608)
            device: Device to run on ('cpu' or 'cuda')
        """
        super().__init__(model_path=model_path, device=device)
        self.input_size = input_size
        self.net = None
        self.output_layers = None
        self.class_names = COCO_CLASSES.copy()
        
        # Track IDs for simple tracking
        self._next_track_id = 1
        self._prev_detections = []
        self._iou_threshold = 0.5
    
    def _find_model_files(self) -> Tuple[str, str]:
        """Find or download model files."""
        # Default paths
        models_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'models')
        os.makedirs(models_dir, exist_ok=True)
        
        weights_path = os.path.join(models_dir, 'yolov4-tiny.weights')
        config_path = os.path.join(models_dir, 'yolov4-tiny.cfg')
        
        # Also check /app/models
        alt_weights = '/app/models/yolov4-tiny.weights'
        alt_config = '/app/models/yolov4-tiny.cfg'
        
        if os.path.exists(alt_weights):
            weights_path = alt_weights
        if os.path.exists(alt_config):
            config_path = alt_config
        
        # Download if not exists
        if not os.path.exists(weights_path):
            print(f"[YOLOv4-tiny] Downloading weights to {weights_path}...")
            urllib.request.urlretrieve(self.WEIGHTS_URL, weights_path)
            print(f"[YOLOv4-tiny] Weights downloaded: {os.path.getsize(weights_path) / 1024 / 1024:.1f} MB")
        
        if not os.path.exists(config_path):
            print(f"[YOLOv4-tiny] Downloading config to {config_path}...")
            urllib.request.urlretrieve(self.CONFIG_URL, config_path)
            print(f"[YOLOv4-tiny] Config downloaded")
        
        return weights_path, config_path
    
    def load_model(self) -> None:
        """Load YOLOv4-tiny model using OpenCV DNN."""
        print("[YOLOv4-tiny] Loading model...")
        
        weights_path, config_path = self._find_model_files()
        
        # Load network
        self.net = cv2.dnn.readNetFromDarknet(config_path, weights_path)
        
        # Set backend and target
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        if self.device == 'cuda' and cv2.cuda.getCudaEnabledDeviceCount() > 0:
            self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
            print("[YOLOv4-tiny] Using CUDA backend")
        else:
            self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
            print("[YOLOv4-tiny] Using CPU backend")
        
        # Get output layer names
        layer_names = self.net.getLayerNames()
        self.output_layers = [layer_names[i - 1] for i in self.net.getUnconnectedOutLayers()]
        
        self._is_loaded = True
        print(f"[YOLOv4-tiny] Model loaded successfully (input: {self.input_size}x{self.input_size})")
    
    def detect(
        self,
        frame: np.ndarray,
        confidence_threshold: float = 0.5,
        classes: Optional[List[int]] = None
    ) -> Tuple[List[DetectionResult], np.ndarray]:
        """Run detection on a frame."""
        if not self._is_loaded:
            self.load_model()
        
        h, w = frame.shape[:2]
        
        # Create blob
        blob = cv2.dnn.blobFromImage(
            frame, 1/255.0, (self.input_size, self.input_size),
            swapRB=True, crop=False
        )
        
        # Run inference
        self.net.setInput(blob)
        outputs = self.net.forward(self.output_layers)
        
        # Parse detections
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
                    
                    # Scale box to original frame size
                    center_x = int(detection[0] * w)
                    center_y = int(detection[1] * h)
                    box_w = int(detection[2] * w)
                    box_h = int(detection[3] * h)
                    
                    x1 = int(center_x - box_w / 2)
                    y1 = int(center_y - box_h / 2)
                    
                    boxes.append([x1, y1, box_w, box_h])
                    confidences.append(float(confidence))
                    class_ids.append(class_id)
        
        # Apply NMS
        indices = cv2.dnn.NMSBoxes(boxes, confidences, confidence_threshold, 0.4)
        
        detections = []
        for i in indices:
            idx = i[0] if isinstance(i, (list, np.ndarray)) else i
            box = boxes[idx]
            x1, y1, bw, bh = box
            x2, y2 = x1 + bw, y1 + bh
            
            # Clamp to frame bounds
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(w, x2)
            y2 = min(h, y2)
            
            class_id = class_ids[idx]
            
            detections.append(DetectionResult(
                bbox=(x1, y1, x2, y2),
                confidence=confidences[idx],
                class_id=class_id,
                class_name=self.class_names.get(class_id, f'class_{class_id}'),
                track_id=None
            ))
        
        # Draw detections
        annotated = frame.copy()
        for det in detections:
            self.draw_modern_detection(annotated, det)
        
        return detections, annotated
    
    def _compute_iou(self, box1: Tuple, box2: Tuple) -> float:
        """Compute IoU between two boxes."""
        x1_1, y1_1, x2_1, y2_1 = box1
        x1_2, y1_2, x2_2, y2_2 = box2
        
        xi1 = max(x1_1, x1_2)
        yi1 = max(y1_1, y1_2)
        xi2 = min(x2_1, x2_2)
        yi2 = min(y2_1, y2_2)
        
        inter_width = max(0, xi2 - xi1)
        inter_height = max(0, yi2 - yi1)
        inter_area = inter_width * inter_height
        
        box1_area = (x2_1 - x1_1) * (y2_1 - y1_1)
        box2_area = (x2_2 - x1_2) * (y2_2 - y1_2)
        
        union_area = box1_area + box2_area - inter_area
        
        if union_area == 0:
            return 0.0
        
        return inter_area / union_area
    
    def track(
        self,
        frame: np.ndarray,
        confidence_threshold: float = 0.5,
        classes: Optional[List[int]] = None
    ) -> Tuple[List[DetectionResult], np.ndarray]:
        """Run detection with simple IoU-based tracking."""
        if not self._is_loaded:
            self.load_model()
        
        # Run detection
        detections, annotated = self.detect(frame, confidence_threshold, classes)
        
        # Simple IoU-based tracking
        for det in detections:
            best_iou = 0.0
            best_track_id = None
            
            for prev_det in self._prev_detections:
                if det.class_id == prev_det.class_id:
                    iou = self._compute_iou(det.bbox, prev_det.bbox)
                    if iou > best_iou and iou > self._iou_threshold:
                        best_iou = iou
                        best_track_id = prev_det.track_id
            
            if best_track_id is not None:
                det.track_id = best_track_id
            else:
                det.track_id = self._next_track_id
                self._next_track_id += 1
        
        # Update previous detections
        self._prev_detections = detections.copy()
        
        # Redraw with track IDs
        annotated = frame.copy()
        for det in detections:
            self.draw_modern_detection(annotated, det)
        
        return detections, annotated
    
    def get_class_names(self) -> dict:
        """Get dictionary of class IDs to class names."""
        return self.class_names.copy()
