"""
NanoDet-Plus ONNX Detector.
Ultra-lightweight object detection model optimized for CPU.
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


class NanoDetPlusDetector(BaseDetector):
    """
    NanoDet-Plus ONNX detector.
    
    Ultra-lightweight model for CPU:
    - Very small model (~4.5 MB)
    - ~5.6 FPS on CPU
    - Good balance of speed and accuracy
    - ONNX Runtime for efficient inference
    """
    
    MODEL_URL = "https://github.com/RangiLyu/nanodet/releases/download/v1.0.0-alpha-1/nanodet-plus-m_416.onnx"
    
    def __init__(
        self,
        model_path: Optional[str] = None,
        input_size: int = 416,
        device: str = 'cpu'
    ):
        """
        Initialize NanoDet-Plus detector.
        
        Args:
            model_path: Path to ONNX model. If None, downloads automatically.
            input_size: Model input size (416)
            device: Device to run on ('cpu')
        """
        super().__init__(model_path=model_path, device=device)
        self.input_size = input_size
        self.session = None
        self.input_name = None
        self.class_names = COCO_CLASSES.copy()
        
        # NanoDet-Plus specific parameters
        self.reg_max = 7
        self.strides = [8, 16, 32]
        self.num_classes = 80
        
        # Track IDs for simple tracking
        self._next_track_id = 1
        self._prev_detections = []
        self._iou_threshold = 0.5
        
        # Mean and std for normalization
        self.mean = np.array([103.53, 116.28, 123.675], dtype=np.float32)
        self.std = np.array([57.375, 57.12, 58.395], dtype=np.float32)
    
    def _find_model_file(self) -> str:
        """Find or download model file."""
        # Default paths
        models_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'models')
        os.makedirs(models_dir, exist_ok=True)
        
        model_path = os.path.join(models_dir, 'nanodet-plus-m_416.onnx')
        
        # Also check /app/models
        alt_path = '/app/models/nanodet-plus-m_416.onnx'
        if os.path.exists(alt_path):
            model_path = alt_path
        
        # Download if not exists
        if not os.path.exists(model_path):
            print(f"[NanoDet-Plus] Downloading model to {model_path}...")
            urllib.request.urlretrieve(self.MODEL_URL, model_path)
            print(f"[NanoDet-Plus] Model downloaded: {os.path.getsize(model_path) / 1024 / 1024:.1f} MB")
        
        return model_path
    
    def load_model(self) -> None:
        """Load NanoDet-Plus ONNX model."""
        try:
            import onnxruntime as ort
        except ImportError:
            raise ImportError("onnxruntime is required for NanoDet-Plus. Install with: pip install onnxruntime")
        
        print("[NanoDet-Plus] Loading model...")
        
        model_path = self._find_model_file()
        
        # Create session
        providers = ['CPUExecutionProvider']
        if self.device == 'cuda':
            providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
        
        self.session = ort.InferenceSession(model_path, providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        
        self._is_loaded = True
        print(f"[NanoDet-Plus] Model loaded successfully (input: {self.input_size}x{self.input_size})")
    
    def _preprocess(self, frame: np.ndarray) -> Tuple[np.ndarray, float, Tuple[int, int]]:
        """Preprocess frame for inference."""
        h, w = frame.shape[:2]
        
        # Resize with letterbox
        scale = min(self.input_size / w, self.input_size / h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        
        resized = cv2.resize(frame, (new_w, new_h))
        
        # Create padded image
        padded = np.full((self.input_size, self.input_size, 3), 114, dtype=np.uint8)
        pad_w = (self.input_size - new_w) // 2
        pad_h = (self.input_size - new_h) // 2
        padded[pad_h:pad_h + new_h, pad_w:pad_w + new_w] = resized
        
        # Convert to float and normalize
        img = padded.astype(np.float32)
        img = (img - self.mean) / self.std
        
        # HWC to CHW
        img = np.transpose(img, (2, 0, 1))
        img = np.expand_dims(img, axis=0)
        
        return img, scale, (pad_w, pad_h)
    
    def _softmax(self, x: np.ndarray, axis: int = -1) -> np.ndarray:
        """Compute softmax values."""
        e_x = np.exp(x - np.max(x, axis=axis, keepdims=True))
        return e_x / np.sum(e_x, axis=axis, keepdims=True)
    
    def _decode_boxes(self, cls_preds: List[np.ndarray], reg_preds: List[np.ndarray], 
                      img_size: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Decode NanoDet outputs to boxes, scores, and classes."""
        all_boxes = []
        all_scores = []
        all_classes = []
        
        for stride_idx, stride in enumerate(self.strides):
            feat_h = img_size // stride
            feat_w = img_size // stride
            
            cls_pred = cls_preds[stride_idx]  # [1, num_classes, h, w]
            reg_pred = reg_preds[stride_idx]  # [1, 4*(reg_max+1), h, w]
            
            # Reshape
            cls_pred = cls_pred[0].transpose(1, 2, 0).reshape(-1, self.num_classes)
            reg_pred = reg_pred[0].transpose(1, 2, 0).reshape(-1, 4, self.reg_max + 1)
            
            # Generate anchors
            shift_x = np.arange(0, feat_w) * stride
            shift_y = np.arange(0, feat_h) * stride
            shift_x, shift_y = np.meshgrid(shift_x, shift_y)
            anchors = np.stack([shift_x.flatten(), shift_y.flatten()], axis=-1)
            
            # Decode boxes
            dis = self._softmax(reg_pred, axis=-1)
            dis = np.sum(dis * np.arange(self.reg_max + 1), axis=-1) * stride
            
            x1 = anchors[:, 0] - dis[:, 0]
            y1 = anchors[:, 1] - dis[:, 1]
            x2 = anchors[:, 0] + dis[:, 2]
            y2 = anchors[:, 1] + dis[:, 3]
            
            boxes = np.stack([x1, y1, x2, y2], axis=-1)
            
            # Get scores and classes
            scores = 1 / (1 + np.exp(-cls_pred))  # Sigmoid
            max_scores = np.max(scores, axis=-1)
            max_classes = np.argmax(scores, axis=-1)
            
            all_boxes.append(boxes)
            all_scores.append(max_scores)
            all_classes.append(max_classes)
        
        all_boxes = np.concatenate(all_boxes, axis=0)
        all_scores = np.concatenate(all_scores, axis=0)
        all_classes = np.concatenate(all_classes, axis=0)
        
        return all_boxes, all_scores, all_classes
    
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
        
        # Preprocess
        img, scale, (pad_w, pad_h) = self._preprocess(frame)
        
        # Run inference
        outputs = self.session.run(None, {self.input_name: img})
        
        # Parse outputs - NanoDet-Plus has different output format
        # Simplified parsing for the model we're using
        detections = []
        
        # The output structure varies by model version
        # For nanodet-plus-m_416, we use a simpler approach
        if len(outputs) == 1:
            # Single output tensor - need to parse differently
            output = outputs[0]
            
            # Try to extract detections based on shape
            if len(output.shape) == 3:
                # Shape: [1, N, 85] or similar (x, y, w, h, obj_conf, class_scores...)
                preds = output[0]
                
                for pred in preds:
                    if len(pred) >= 6:
                        # Assuming format: x, y, w, h, obj_conf, class_scores...
                        obj_conf = pred[4] if len(pred) > 4 else 1.0
                        
                        if len(pred) > 5:
                            class_scores = pred[5:]
                            class_id = int(np.argmax(class_scores))
                            score = float(obj_conf * class_scores[class_id])
                        else:
                            class_id = 0
                            score = float(obj_conf)
                        
                        if score > confidence_threshold:
                            if classes is not None and class_id not in classes:
                                continue
                            
                            # Scale coordinates back to original frame
                            cx, cy, bw, bh = pred[:4]
                            x1 = int((cx - bw/2 - pad_w) / scale)
                            y1 = int((cy - bh/2 - pad_h) / scale)
                            x2 = int((cx + bw/2 - pad_w) / scale)
                            y2 = int((cy + bh/2 - pad_h) / scale)
                            
                            # Clamp
                            x1 = max(0, min(w, x1))
                            y1 = max(0, min(h, y1))
                            x2 = max(0, min(w, x2))
                            y2 = max(0, min(h, y2))
                            
                            if x2 > x1 and y2 > y1:
                                detections.append(DetectionResult(
                                    bbox=(x1, y1, x2, y2),
                                    confidence=score,
                                    class_id=class_id,
                                    class_name=self.class_names.get(class_id, f'class_{class_id}'),
                                    track_id=None
                                ))
        
        # Apply simple NMS
        if len(detections) > 1:
            detections = self._simple_nms(detections, iou_threshold=0.4)
        
        # Draw detections
        annotated = frame.copy()
        for det in detections:
            self.draw_modern_detection(annotated, det)
        
        return detections, annotated
    
    def _simple_nms(self, detections: List[DetectionResult], iou_threshold: float = 0.4) -> List[DetectionResult]:
        """Simple NMS implementation."""
        if len(detections) == 0:
            return []
        
        # Sort by confidence
        sorted_dets = sorted(detections, key=lambda x: x.confidence, reverse=True)
        
        keep = []
        while sorted_dets:
            best = sorted_dets.pop(0)
            keep.append(best)
            
            sorted_dets = [
                det for det in sorted_dets
                if self._compute_iou(best.bbox, det.bbox) < iou_threshold
            ]
        
        return keep
    
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
