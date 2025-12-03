"""
ONNX-based YOLO-NAS Detector.
Ultra-optimized for CPU inference without heavy dependencies.
"""

import os
import numpy as np
from typing import List, Dict, Tuple, Optional

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


class ONNXYOLONASDetector(BaseDetector):
    """
    ONNX Runtime based YOLO-NAS detector.
    
    This is the most efficient option for CPU inference:
    - No PyTorch/TensorFlow dependency
    - 2-3x faster than running .pt models directly
    - Much smaller Docker image
    
    The ONNX model should be exported with preprocessing=True and postprocessing=True
    using the export_yolonas.py script.
    """
    
    def __init__(
        self,
        model_path: Optional[str] = None,
        input_size: int = 640,
        device: str = 'cpu'
    ):
        """
        Initialize ONNX YOLO-NAS detector.
        
        Args:
            model_path: Path to .onnx file. If None, searches in default locations.
            input_size: Model input size (must match export size)
            device: Device to run on ('cpu' or 'cuda')
        """
        super().__init__(model_path=model_path, device=device)
        self.input_size = input_size
        self.session = None
        self.input_name = None
        self.class_names = COCO_CLASSES.copy()
        
        # Track IDs for simple tracking
        self._next_track_id = 1
        self._prev_detections = []
        self._iou_threshold = 0.5
    
    def _find_model_path(self) -> str:
        """Find ONNX model file in default locations."""
        search_paths = [
            self.model_path,
            "yolo_nas_s.onnx",
            "models/yolo_nas_s.onnx",
            "/app/models/yolo_nas_s.onnx",
            os.path.join(os.path.dirname(__file__), "..", "models", "yolo_nas_s.onnx"),
            os.path.join(os.path.dirname(__file__), "..", "..", "models", "yolo_nas_s.onnx"),
        ]
        
        for path in search_paths:
            if path and os.path.exists(path):
                return path
        
        raise FileNotFoundError(
            f"ONNX model not found. Searched: {search_paths}\n"
            "Run 'python export_yolonas.py' to generate the model."
        )
    
    def load_model(self) -> None:
        """Load ONNX model using ONNX Runtime."""
        if self._is_loaded:
            return
        
        try:
            import onnxruntime as ort
        except ImportError:
            raise ImportError(
                "onnxruntime not installed. Run: pip install onnxruntime"
            )
        
        model_path = self._find_model_path()
        print(f"[ONNX-YOLO-NAS] Loading model from: {model_path}")
        
        # Configure session options for CPU optimization
        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess_options.intra_op_num_threads = os.cpu_count() or 4
        sess_options.inter_op_num_threads = 2
        
        # Select execution provider
        if self.device == 'cuda' or self.device.startswith('cuda:'):
            providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
        else:
            providers = ['CPUExecutionProvider']
        
        self.session = ort.InferenceSession(
            model_path,
            sess_options=sess_options,
            providers=providers
        )
        
        self.input_name = self.session.get_inputs()[0].name
        
        # Log model info
        print(f"[ONNX-YOLO-NAS] Model loaded successfully")
        print(f"[ONNX-YOLO-NAS] Input: {self.input_name}")
        print(f"[ONNX-YOLO-NAS] Providers: {self.session.get_providers()}")
        
        self._is_loaded = True
    
    def _preprocess(self, frame: np.ndarray) -> Tuple[np.ndarray, float, float]:
        """
        Preprocess frame for inference.
        
        Returns:
            Tuple of (preprocessed_input, scale_x, scale_y)
        """
        import cv2
        
        h_orig, w_orig = frame.shape[:2]
        
        # Resize to model input size
        img_resized = cv2.resize(frame, (self.input_size, self.input_size))
        
        # Convert BGR to RGB
        img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
        
        # Transpose from HWC to CHW format
        img_chw = np.transpose(img_rgb, (2, 0, 1))
        
        # Add batch dimension and convert to float32
        img_input = np.expand_dims(img_chw, axis=0).astype(np.float32)
        
        # Calculate scale factors for box rescaling
        scale_x = w_orig / self.input_size
        scale_y = h_orig / self.input_size
        
        return img_input, scale_x, scale_y
    
    def _parse_outputs(
        self,
        outputs: List[np.ndarray],
        scale_x: float,
        scale_y: float,
        confidence_threshold: float,
        classes: Optional[List[int]] = None
    ) -> List[DetectionResult]:
        """
        Parse ONNX model outputs into DetectionResult objects.
        
        YOLO-NAS ONNX with postprocessing outputs:
        - outputs[0]: Number of detections (or predictions array)
        - outputs[1]: Bounding boxes [x1, y1, x2, y2]
        - outputs[2]: Confidence scores
        - outputs[3]: Class IDs
        """
        detections = []
        
        # Handle different output formats
        if len(outputs) == 4:
            # Standard format with NMS included
            boxes = outputs[1][0] if len(outputs[1].shape) > 1 else outputs[1]
            scores = outputs[2][0] if len(outputs[2].shape) > 1 else outputs[2]
            class_ids = outputs[3][0] if len(outputs[3].shape) > 1 else outputs[3]
        elif len(outputs) == 1:
            # Combined output format - parse it
            raw_output = outputs[0]
            if len(raw_output.shape) == 3:
                raw_output = raw_output[0]
            # Format: [x1, y1, x2, y2, score, class_id] per row
            boxes = raw_output[:, :4]
            scores = raw_output[:, 4]
            class_ids = raw_output[:, 5]
        else:
            # Try to handle gracefully
            print(f"[ONNX] Unexpected output format: {len(outputs)} arrays")
            return detections
        
        for i, (box, score, class_id) in enumerate(zip(boxes, scores, class_ids)):
            if score < confidence_threshold:
                continue
            
            class_id = int(class_id)
            
            # Filter by class if specified
            if classes is not None and class_id not in classes:
                continue
            
            # Scale box coordinates back to original frame size
            x1 = int(box[0] * scale_x)
            y1 = int(box[1] * scale_y)
            x2 = int(box[2] * scale_x)
            y2 = int(box[3] * scale_y)
            
            # Ensure valid coordinates
            x1 = max(0, x1)
            y1 = max(0, y1)
            
            detections.append(DetectionResult(
                bbox=(x1, y1, x2, y2),
                confidence=float(score),
                class_id=class_id,
                class_name=self.class_names.get(class_id, f"class_{class_id}"),
                track_id=None
            ))
        
        return detections
    
    def detect(
        self,
        frame: np.ndarray,
        confidence_threshold: float = 0.5,
        classes: Optional[List[int]] = None
    ) -> Tuple[List[DetectionResult], np.ndarray]:
        """Run detection on a frame."""
        if not self._is_loaded:
            self.load_model()
        
        # Preprocess
        img_input, scale_x, scale_y = self._preprocess(frame)
        
        # Run inference
        outputs = self.session.run(None, {self.input_name: img_input})
        
        # Parse outputs
        detections = self._parse_outputs(
            outputs, scale_x, scale_y, confidence_threshold, classes
        )
        
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
        
        inter_area = max(0, xi2 - xi1) * max(0, yi2 - yi1)
        
        box1_area = (x2_1 - x1_1) * (y2_1 - y1_1)
        box2_area = (x2_2 - x1_2) * (y2_2 - y1_2)
        
        union_area = box1_area + box2_area - inter_area
        
        return inter_area / union_area if union_area > 0 else 0
    
    def _simple_track(self, detections: List[DetectionResult]) -> List[DetectionResult]:
        """Simple IoU-based tracking."""
        tracked = []
        used_prev = set()
        
        for det in detections:
            best_iou = 0
            best_prev = None
            best_idx = -1
            
            for idx, prev in enumerate(self._prev_detections):
                if idx in used_prev:
                    continue
                if prev.class_id != det.class_id:
                    continue
                    
                iou = self._compute_iou(det.bbox, prev.bbox)
                if iou > best_iou and iou > self._iou_threshold:
                    best_iou = iou
                    best_prev = prev
                    best_idx = idx
            
            if best_prev is not None:
                # Continue existing track
                track_id = best_prev.track_id
                used_prev.add(best_idx)
            else:
                # New track
                track_id = self._next_track_id
                self._next_track_id += 1
            
            tracked.append(DetectionResult(
                bbox=det.bbox,
                confidence=det.confidence,
                class_id=det.class_id,
                class_name=det.class_name,
                track_id=track_id
            ))
        
        self._prev_detections = tracked
        return tracked
    
    def track(
        self,
        frame: np.ndarray,
        confidence_threshold: float = 0.5,
        classes: Optional[List[int]] = None
    ) -> Tuple[List[DetectionResult], np.ndarray]:
        """Run detection with tracking."""
        if not self._is_loaded:
            self.load_model()
        
        # Preprocess
        img_input, scale_x, scale_y = self._preprocess(frame)
        
        # Run inference
        outputs = self.session.run(None, {self.input_name: img_input})
        
        # Parse outputs
        detections = self._parse_outputs(
            outputs, scale_x, scale_y, confidence_threshold, classes
        )
        
        # Apply simple tracking
        tracked_detections = self._simple_track(detections)
        
        # Draw detections
        annotated = frame.copy()
        for det in tracked_detections:
            self.draw_modern_detection(annotated, det)
        
        return tracked_detections, annotated
    
    def get_class_names(self) -> Dict[int, str]:
        """Return class names mapping."""
        return self.class_names.copy()


# Alias for backward compatibility
YOLONASOnnxDetector = ONNXYOLONASDetector
