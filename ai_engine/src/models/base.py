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
        Draw modern detection visualization with corner arcs.
        Uses platform colors (cyan/blue tones) by default.
        Shows only track ID without confidence percentage.
        
        Args:
            frame: Frame to draw on
            det: Detection result
            color: Optional BGR color tuple, defaults to platform cyan
        """
        import cv2
        
        x1, y1, x2, y2 = det.bbox
        w = x2 - x1
        h = y2 - y1
        
        # Platform colors (cyan/teal palette) - BGR format
        if color is None:
            # Vary color slightly based on track_id for visual distinction
            if det.track_id is not None:
                hue_shift = (det.track_id * 37) % 60  # Subtle variation
                color = (
                    200 + (hue_shift % 55),  # B: 200-255 (cyan to blue)
                    200 - (hue_shift % 40),  # G: 160-200 
                    50 + (hue_shift % 50)    # R: 50-100
                )
            else:
                color = (230, 180, 60)  # Default cyan-ish
        
        # Corner arc length (proportional to box size)
        arc_len = min(w, h) // 4
        arc_len = max(15, min(arc_len, 40))  # Clamp between 15-40px
        
        thickness = 2
        
        # Draw corner arcs (incomplete rectangle - modern style)
        # Top-left corner
        cv2.line(frame, (x1, y1), (x1 + arc_len, y1), color, thickness)
        cv2.line(frame, (x1, y1), (x1, y1 + arc_len), color, thickness)
        # Small arc at corner
        cv2.ellipse(frame, (x1 + 8, y1 + 8), (8, 8), 180, 0, 90, color, thickness)
        
        # Top-right corner
        cv2.line(frame, (x2 - arc_len, y1), (x2, y1), color, thickness)
        cv2.line(frame, (x2, y1), (x2, y1 + arc_len), color, thickness)
        cv2.ellipse(frame, (x2 - 8, y1 + 8), (8, 8), 270, 0, 90, color, thickness)
        
        # Bottom-left corner  
        cv2.line(frame, (x1, y2 - arc_len), (x1, y2), color, thickness)
        cv2.line(frame, (x1, y2), (x1 + arc_len, y2), color, thickness)
        cv2.ellipse(frame, (x1 + 8, y2 - 8), (8, 8), 90, 0, 90, color, thickness)
        
        # Bottom-right corner
        cv2.line(frame, (x2, y2 - arc_len), (x2, y2), color, thickness)
        cv2.line(frame, (x2 - arc_len, y2), (x2, y2), color, thickness)
        cv2.ellipse(frame, (x2 - 8, y2 - 8), (8, 8), 0, 0, 90, color, thickness)
        
        # Label - only show ID (no percentage)
        if det.track_id is not None:
            label = f"#{det.track_id}"
        else:
            label = det.class_name[:8]  # Short class name
        
        # Modern label style - small pill shape
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.45
        font_thickness = 1
        (tw, th), baseline = cv2.getTextSize(label, font, font_scale, font_thickness)
        
        # Position label at top-left, slightly inside
        label_x = x1 + 4
        label_y = y1 - 8
        
        # If label would go above frame, put it inside
        if label_y - th - 4 < 0:
            label_y = y1 + th + 12
        
        # Draw semi-transparent background pill
        padding = 4
        bg_x1 = label_x - padding
        bg_y1 = label_y - th - padding
        bg_x2 = label_x + tw + padding
        bg_y2 = label_y + padding
        
        # Create overlay for transparency effect
        overlay = frame.copy()
        cv2.rectangle(overlay, (bg_x1, bg_y1), (bg_x2, bg_y2), (40, 40, 40), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
        
        # Draw rounded corners on pill (subtle)
        cv2.rectangle(frame, (bg_x1, bg_y1), (bg_x2, bg_y2), color, 1)
        
        # Draw label text
        cv2.putText(frame, label, (label_x, label_y), font, font_scale, color, font_thickness, cv2.LINE_AA)
    
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
