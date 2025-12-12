"""
Base classes for detection models.
Provides a unified interface for all detection backends.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
import numpy as np


@dataclass
class DetectionResult:
    """Unified detection result across all model backends."""
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    confidence: float
    class_id: int
    class_name: str
    track_id: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'bbox': self.bbox,
            'confidence': self.confidence,
            'class_id': self.class_id,
            'class_name': self.class_name,
            'track_id': self.track_id
        }


class BaseDetector(ABC):
    """
    Abstract base class for all detection models.
    All model implementations must inherit from this class.
    """
    
    def __init__(self, model_path: Optional[str] = None, device: str = 'auto'):
        """
        Initialize the detector.
        
        Args:
            model_path: Path to model weights (optional, uses default if not provided)
            device: Device to run on ('auto', 'cpu', 'cuda', 'cuda:0', etc.)
        """
        self.model_path = model_path
        self.device = device
        self.model = None
        self.class_names: Dict[int, str] = {}
        self._is_loaded = False
    
    @property
    def is_loaded(self) -> bool:
        return self._is_loaded
    
    @abstractmethod
    def load_model(self) -> None:
        """Load the model weights. Must be implemented by subclasses."""
        pass
    
    @abstractmethod
    def detect(
        self, 
        frame: np.ndarray, 
        confidence_threshold: float = 0.5,
        classes: Optional[List[int]] = None
    ) -> Tuple[List[DetectionResult], np.ndarray]:
        """
        Run detection on a frame.
        
        Args:
            frame: Input frame (BGR format from OpenCV)
            confidence_threshold: Minimum confidence for detections
            classes: List of class IDs to detect (None = all classes)
            
        Returns:
            Tuple of (list of DetectionResult, annotated frame)
        """
        pass
    
    @abstractmethod
    def track(
        self, 
        frame: np.ndarray, 
        confidence_threshold: float = 0.5,
        classes: Optional[List[int]] = None
    ) -> Tuple[List[DetectionResult], np.ndarray]:
        """
        Run detection with tracking on a frame.
        
        Args:
            frame: Input frame (BGR format from OpenCV)
            confidence_threshold: Minimum confidence for detections
            classes: List of class IDs to detect (None = all classes)
            
        Returns:
            Tuple of (list of DetectionResult with track_ids, annotated frame)
        """
        pass
    
    @abstractmethod
    def get_class_names(self) -> Dict[int, str]:
        """Return mapping of class IDs to class names."""
        pass
    
    def get_class_name(self, class_id: int) -> str:
        """Get class name for a class ID."""
        return self.class_names.get(class_id, f"class_{class_id}")
    
    def draw_modern_detection(self, frame: np.ndarray, det: 'DetectionResult', color: Tuple[int, int, int] = None) -> None:
        """
        Draw ultra-minimal detection visualization - corners only.
        Optimized for speed: no arcs, thin lines, simple label.
        
        Args:
            frame: Frame to draw on
            det: Detection result
            color: Optional BGR color tuple, defaults to platform cyan
        """
        import cv2
        
        x1, y1, x2, y2 = det.bbox
        
        # Validate coordinates - skip if invalid (nan, inf, or out of bounds)
        import math
        if any(math.isnan(v) or math.isinf(v) for v in [x1, y1, x2, y2]):
            return  # Skip this detection
        
        # Convert to int and clamp to frame bounds
        h_frame, w_frame = frame.shape[:2]
        x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
        x1 = max(0, min(x1, w_frame - 1))
        y1 = max(0, min(y1, h_frame - 1))
        x2 = max(0, min(x2, w_frame - 1))
        y2 = max(0, min(y2, h_frame - 1))
        
        # Skip if box is too small or invalid
        if x2 <= x1 or y2 <= y1:
            return
        
        w = x2 - x1
        h = y2 - y1
        
        # Platform colors (cyan/teal) - BGR format
        if color is None:
            if det.track_id is not None:
                hue_shift = (det.track_id * 37) % 60
                color = (200 + (hue_shift % 55), 180 - (hue_shift % 30), 50 + (hue_shift % 40))
            else:
                color = (220, 180, 60)  # Cyan
        
        # Corner length (small, proportional)
        corner_len = min(w, h) // 5
        corner_len = max(10, min(corner_len, 25))  # 10-25px
        
        thickness = 1  # Thin lines for speed
        
        # Draw only corner lines (no arcs - faster)
        # Top-left
        cv2.line(frame, (x1, y1), (x1 + corner_len, y1), color, thickness)
        cv2.line(frame, (x1, y1), (x1, y1 + corner_len), color, thickness)
        
        # Top-right
        cv2.line(frame, (x2 - corner_len, y1), (x2, y1), color, thickness)
        cv2.line(frame, (x2, y1), (x2, y1 + corner_len), color, thickness)
        
        # Bottom-left
        cv2.line(frame, (x1, y2 - corner_len), (x1, y2), color, thickness)
        cv2.line(frame, (x1, y2), (x1 + corner_len, y2), color, thickness)
        
        # Bottom-right
        cv2.line(frame, (x2, y2 - corner_len), (x2, y2), color, thickness)
        cv2.line(frame, (x2 - corner_len, y2), (x2, y2), color, thickness)
        
        # Label: class name only (no percentage, no ID)
        label = det.class_name[:10]  # Max 10 chars
        
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.35
        (tw, th), _ = cv2.getTextSize(label, font, font_scale, 1)
        
        # Position: top-left, outside box if possible
        lx = x1
        ly = y1 - 4 if y1 > 15 else y1 + th + 8
        
        # Dark background pill (simple, no overlay for speed)
        cv2.rectangle(frame, (lx - 2, ly - th - 2), (lx + tw + 2, ly + 2), (30, 30, 30), -1)
        cv2.putText(frame, label, (lx, ly), font, font_scale, color, 1, cv2.LINE_AA)
    
    def warmup(self, input_shape: Tuple[int, int, int] = (640, 640, 3)) -> None:
        """
        Warmup the model with a dummy input.
        Useful for first-inference latency reduction.
        """
        dummy_frame = np.zeros(input_shape, dtype=np.uint8)
        try:
            self.detect(dummy_frame)
        except Exception:
            pass  # Ignore warmup errors
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(loaded={self._is_loaded}, device={self.device})"
