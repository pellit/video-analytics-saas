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
