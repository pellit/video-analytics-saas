"""
RT-DETR (Real-Time Detection Transformer) detector implementation.
Uses transformers library from HuggingFace.
This is an alternative model with transformer-based architecture.
"""

import cv2
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
import torch

from .base import BaseDetector, DetectionResult


class RTDETRDetector(BaseDetector):
    """
    RT-DETR detector using HuggingFace transformers.
    
    RT-DETR is a real-time end-to-end object detector based on DETR architecture.
    It achieves excellent accuracy with real-time performance.
    
    Available models:
    - rtdetr-l: Large model (recommended)
    - rtdetr-x: Extra large model (best accuracy)
    """
    
    AVAILABLE_MODELS = ['rtdetr-l', 'rtdetr-x', 'PekingU/rtdetr_r50vd', 'PekingU/rtdetr_r101vd']
    DEFAULT_MODEL = 'PekingU/rtdetr_r50vd'
    
    # COCO class names (same as YOLO-NAS for consistency)
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
        Initialize RT-DETR detector.
        
        Args:
            model_name: HuggingFace model name or path
            device: Device to run on ('auto', 'cpu', 'cuda')
        """
        super().__init__(model_path=model_name, device=device)
        self.model_name = model_name or self.DEFAULT_MODEL
        self.class_names = self.COCO_CLASSES.copy()
        self.processor = None
        self.tracker = None
        
    def load_model(self) -> None:
        """Load RT-DETR model from HuggingFace."""
        try:
            from transformers import RTDetrForObjectDetection, RTDetrImageProcessor
            
            # Determine device
            if self.device == 'auto':
                device = 'cuda' if torch.cuda.is_available() else 'cpu'
            else:
                device = self.device
            
            print(f"[RT-DETR] Loading model {self.model_name} on {device}...")
            
            # Load model and processor
            self.processor = RTDetrImageProcessor.from_pretrained(self.model_name)
            self.model = RTDetrForObjectDetection.from_pretrained(self.model_name)
            self.model.to(device)
            self.model.eval()
            
            # Update class names from model config
            if hasattr(self.model.config, 'id2label'):
                self.class_names = {int(k): v for k, v in self.model.config.id2label.items()}
            
            self._device = device
            self._is_loaded = True
            print(f"[RT-DETR] Model loaded successfully!")
            
        except ImportError as e:
            raise ImportError(
                "transformers library is required for RT-DETR. "
                "Install with: pip install transformers"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Failed to load RT-DETR model: {e}") from e
    
    def detect(
        self, 
        frame: np.ndarray, 
        confidence_threshold: float = 0.5,
        classes: Optional[List[int]] = None
    ) -> Tuple[List[DetectionResult], np.ndarray]:
        """Run detection on a frame."""
        if not self._is_loaded:
            self.load_model()
        
        # Convert BGR to RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Process image
        inputs = self.processor(images=rgb_frame, return_tensors="pt")
        inputs = {k: v.to(self._device) for k, v in inputs.items()}
        
        # Run inference
        with torch.no_grad():
            outputs = self.model(**inputs)
        
        # Post-process
        h, w = frame.shape[:2]
        target_sizes = torch.tensor([[h, w]], device=self._device)
        
        results_processed = self.processor.post_process_object_detection(
            outputs,
            target_sizes=target_sizes,
            threshold=confidence_threshold
        )[0]
        
        results = []
        annotated_frame = frame.copy()
        
        boxes = results_processed['boxes'].cpu().numpy()
        scores = results_processed['scores'].cpu().numpy()
        labels = results_processed['labels'].cpu().numpy()
        
        for i in range(len(boxes)):
            class_id = int(labels[i])
            
            # Filter by class if specified
            if classes is not None and class_id not in classes:
                continue
            
            conf = float(scores[i])
            x1, y1, x2, y2 = map(int, boxes[i])
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
        RT-DETR doesn't have built-in tracking, using ByteTrack or simple tracker.
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
        """Initialize tracker."""
        try:
            from supervision import ByteTrack
            self.tracker = ByteTrack()
        except ImportError:
            # Fallback: import simple tracker from yolo_nas module
            from .yolo_nas import SimpleTracker
            self.tracker = SimpleTracker()
    
    def _draw_detection(self, frame: np.ndarray, det: DetectionResult) -> None:
        """Draw modern detection visualization with corner arcs."""
        # Use the base class modern drawing method
        self.draw_modern_detection(frame, det)
    
    def get_class_names(self) -> Dict[int, str]:
        """Return class names mapping."""
        return self.class_names.copy()
