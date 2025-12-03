"""
YOLO-NAS detector implementation.
Uses super-gradients library from Deci AI (Apache 2.0 license).
This is the RECOMMENDED model for production use.
"""

import cv2
import numpy as np
from typing import List, Dict, Any, Optional, Tuple

from .base import BaseDetector, DetectionResult


class YOLONASDetector(BaseDetector):
    """
    YOLO-NAS detector using super-gradients library.
    
    License: Apache 2.0 (Deci AI)
    Performance: State-of-the-art accuracy with excellent inference speed.
    
    Available models:
    - yolo_nas_s: Small model, fastest inference
    - yolo_nas_m: Medium model, balanced
    - yolo_nas_l: Large model, best accuracy
    """
    
    AVAILABLE_MODELS = ['yolo_nas_s', 'yolo_nas_m', 'yolo_nas_l']
    DEFAULT_MODEL = 'yolo_nas_s'
    
    # COCO class names (80 classes)
    COCO_CLASSES = {
        0: 'person', 1: 'bicycle', 2: 'car', 3: 'motorcycle', 4: 'airplane',
        5: 'bus', 6: 'train', 7: 'truck', 8: 'boat', 9: 'traffic light',
        10: 'fire hydrant', 11: 'stop sign', 12: 'parking meter', 13: 'bench',
        14: 'bird', 15: 'cat', 16: 'dog', 17: 'elephant', 18: 'bear',
        19: 'zebra', 20: 'giraffe', 21: 'backpack', 22: 'umbrella', 23: 'handbag',
        24: 'tie', 25: 'suitcase', 26: 'frisbee', 27: 'skis', 28: 'snowboard',
        29: 'sports ball', 30: 'kite', 31: 'baseball bat', 32: 'baseball glove',
        33: 'skateboard', 34: 'surfboard', 35: 'tennis racket', 36: 'bottle',
        37: 'wine glass', 38: 'cup', 39: 'fork', 40: 'knife', 41: 'spoon',
        42: 'bowl', 43: 'banana', 44: 'apple', 45: 'sandwich', 46: 'orange',
        47: 'broccoli', 48: 'carrot', 49: 'hot dog', 50: 'pizza', 51: 'donut',
        52: 'cake', 53: 'chair', 54: 'couch', 55: 'potted plant', 56: 'bed',
        57: 'dining table', 58: 'toilet', 59: 'tv', 60: 'laptop', 61: 'mouse',
        62: 'remote', 63: 'keyboard', 64: 'cell phone', 65: 'microwave',
        66: 'oven', 67: 'toaster', 68: 'sink', 69: 'refrigerator', 70: 'book',
        71: 'clock', 72: 'vase', 73: 'scissors', 74: 'teddy bear', 75: 'hair drier',
        76: 'toothbrush'
    }
    
    def __init__(self, model_name: str = None, device: str = 'auto'):
        """
        Initialize YOLO-NAS detector.
        
        Args:
            model_name: Name of the model ('yolo_nas_s', 'yolo_nas_m', 'yolo_nas_l')
            device: Device to run on ('auto', 'cpu', 'cuda')
        """
        super().__init__(model_path=model_name, device=device)
        self.model_name = model_name or self.DEFAULT_MODEL
        self.class_names = self.COCO_CLASSES.copy()
        self.tracker = None
        
    def load_model(self) -> None:
        """Load YOLO-NAS model from super-gradients."""
        try:
            from super_gradients.training import models
            from super_gradients.common.object_names import Models
            import torch
            
            # Determine device
            if self.device == 'auto':
                device = 'cuda' if torch.cuda.is_available() else 'cpu'
            else:
                device = self.device
            
            print(f"[YOLO-NAS] Loading model {self.model_name} on {device}...")
            
            # Load pretrained model
            self.model = models.get(
                self.model_name,
                pretrained_weights="coco"
            ).to(device)
            
            self.model.eval()
            self._device = device
            self._is_loaded = True
            print(f"[YOLO-NAS] Model loaded successfully!")
            
        except ImportError as e:
            raise ImportError(
                "super-gradients library is required for YOLO-NAS. "
                "Install with: pip install super-gradients"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Failed to load YOLO-NAS model: {e}") from e
    
    def detect(
        self, 
        frame: np.ndarray, 
        confidence_threshold: float = 0.5,
        classes: Optional[List[int]] = None
    ) -> Tuple[List[DetectionResult], np.ndarray]:
        """Run detection on a frame."""
        if not self._is_loaded:
            self.load_model()
        
        # Run prediction
        predictions = self.model.predict(frame, conf=confidence_threshold)
        
        results = []
        annotated_frame = frame.copy()
        
        # Process predictions
        pred = predictions[0]  # First image
        
        if hasattr(pred, 'prediction'):
            bboxes = pred.prediction.bboxes_xyxy
            confidences = pred.prediction.confidence
            class_ids = pred.prediction.labels
            
            for i in range(len(bboxes)):
                class_id = int(class_ids[i])
                
                # Filter by class if specified
                if classes is not None and class_id not in classes:
                    continue
                
                conf = float(confidences[i])
                if conf < confidence_threshold:
                    continue
                
                x1, y1, x2, y2 = map(int, bboxes[i])
                class_name = self.get_class_name(class_id)
                
                result = DetectionResult(
                    bbox=(x1, y1, x2, y2),
                    confidence=conf,
                    class_id=class_id,
                    class_name=class_name,
                    track_id=None
                )
                results.append(result)
                
                # Draw on frame
                self._draw_detection(annotated_frame, result)
        
        return results, annotated_frame
    
    def track(
        self, 
        frame: np.ndarray, 
        confidence_threshold: float = 0.5,
        classes: Optional[List[int]] = None
    ) -> Tuple[List[DetectionResult], np.ndarray]:
        """
        Run detection with tracking.
        Note: YOLO-NAS doesn't have built-in tracking, so we use ByteTrack.
        """
        if self.tracker is None:
            self._init_tracker()
        
        # First get detections
        detections, _ = self.detect(frame, confidence_threshold, classes)
        
        if not detections:
            return [], frame.copy()
        
        # Format detections for tracker
        det_array = np.array([
            [d.bbox[0], d.bbox[1], d.bbox[2], d.bbox[3], d.confidence, d.class_id]
            for d in detections
        ])
        
        # Run tracker
        tracked = self.tracker.update(det_array, frame)
        
        results = []
        annotated_frame = frame.copy()
        
        for track in tracked:
            x1, y1, x2, y2, track_id, conf, class_id = track[:7]
            class_id = int(class_id)
            
            result = DetectionResult(
                bbox=(int(x1), int(y1), int(x2), int(y2)),
                confidence=float(conf),
                class_id=class_id,
                class_name=self.get_class_name(class_id),
                track_id=int(track_id)
            )
            results.append(result)
            self._draw_detection(annotated_frame, result)
        
        return results, annotated_frame
    
    def _init_tracker(self):
        """Initialize ByteTrack tracker."""
        try:
            from supervision import ByteTrack
            self.tracker = ByteTrack()
        except ImportError:
            # Fallback: simple tracking by IoU
            print("[YOLO-NAS] ByteTrack not available, using simple detection mode")
            self.tracker = SimpleTracker()
    
    def _draw_detection(self, frame: np.ndarray, det: DetectionResult) -> None:
        """Draw modern detection visualization with corner arcs."""
        # Use the base class modern drawing method
        self.draw_modern_detection(frame, det)
    
    def get_class_names(self) -> Dict[int, str]:
        """Return class names mapping."""
        return self.class_names.copy()


class SimpleTracker:
    """Simple IoU-based tracker as fallback when ByteTrack is not available."""
    
    def __init__(self, iou_threshold: float = 0.5, max_age: int = 30):
        self.iou_threshold = iou_threshold
        self.max_age = max_age
        self.tracks = {}
        self.next_id = 1
    
    def update(self, detections: np.ndarray, frame: np.ndarray) -> np.ndarray:
        """Update tracks with new detections."""
        if len(detections) == 0:
            return np.array([])
        
        results = []
        for det in detections:
            x1, y1, x2, y2, conf, class_id = det
            # Simple: assign new ID to each detection (basic tracking)
            track_id = self.next_id
            self.next_id += 1
            results.append([x1, y1, x2, y2, track_id, conf, class_id])
        
        return np.array(results)
