"""
Ultralytics YOLO detector implementation.

⚠️ WARNING: DISABLED BY DEFAULT ⚠️
This model uses ultralytics library which has licensing restrictions.
Only enable for testing/development purposes.
For production, use YOLO-NAS or RT-DETR instead.

To enable: Set environment variable ENABLE_ULTRALYTICS=true
"""

import os
import cv2
import numpy as np
from typing import List, Dict, Any, Optional, Tuple

from .base import BaseDetector, DetectionResult


# Check if ultralytics is enabled
ULTRALYTICS_ENABLED = os.environ.get('ENABLE_ULTRALYTICS', 'false').lower() == 'true'


class UltralyticsDetector(BaseDetector):
    """
    Ultralytics YOLO detector.
    
    ⚠️ LICENSING WARNING ⚠️
    Ultralytics has AGPL-3.0 license which requires:
    - Open source distribution of your code
    - Commercial license for proprietary use
    
    This detector is DISABLED BY DEFAULT.
    Use YOLO-NAS (Apache 2.0) for production.
    
    Available models:
    - yolov8n.pt: Nano (fastest)
    - yolov8s.pt: Small
    - yolov8m.pt: Medium
    - yolov8l.pt: Large
    - yolov8x.pt: XLarge (most accurate)
    """
    
    AVAILABLE_MODELS = ['yolov8n.pt', 'yolov8s.pt', 'yolov8m.pt', 'yolov8l.pt', 'yolov8x.pt']
    DEFAULT_MODEL = 'yolov8n.pt'
    
    def __init__(self, model_path: str = None, device: str = 'auto'):
        """
        Initialize Ultralytics detector.
        
        Args:
            model_path: Path to model weights (.pt file)
            device: Device to run on ('auto', 'cpu', 'cuda', '0', '1', etc.)
        """
        if not ULTRALYTICS_ENABLED:
            raise RuntimeError(
                "Ultralytics is DISABLED for legal reasons. "
                "Set ENABLE_ULTRALYTICS=true to enable for testing only. "
                "For production, use YOLO-NAS or RT-DETR instead."
            )
        
        super().__init__(model_path=model_path, device=device)
        self.model_path = model_path or self.DEFAULT_MODEL
        
    def load_model(self) -> None:
        """Load Ultralytics YOLO model."""
        if not ULTRALYTICS_ENABLED:
            raise RuntimeError("Ultralytics is disabled. Set ENABLE_ULTRALYTICS=true to enable.")
        
        try:
            from ultralytics import YOLO
            
            print(f"[Ultralytics] ⚠️ WARNING: Using ultralytics (AGPL-3.0 license)")
            print(f"[Ultralytics] Loading model {self.model_path}...")
            
            # Load model
            self.model = YOLO(self.model_path)
            
            # Set device
            if self.device != 'auto':
                self.model.to(self.device)
            
            # Get class names
            self.class_names = self.model.names.copy()
            
            self._device = self.device
            self._is_loaded = True
            print(f"[Ultralytics] Model loaded successfully!")
            
        except ImportError as e:
            raise ImportError(
                "ultralytics library is required. "
                "Install with: pip install ultralytics"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Failed to load Ultralytics model: {e}") from e
    
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
        results = self.model(
            frame,
            conf=confidence_threshold,
            classes=classes,
            verbose=False
        )
        
        detections = []
        
        # Process results
        for r in results:
            boxes = r.boxes
            if boxes is not None:
                for box in boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                    conf = float(box.conf[0].cpu().numpy())
                    class_id = int(box.cls[0].cpu().numpy())
                    
                    result = DetectionResult(
                        bbox=(x1, y1, x2, y2),
                        confidence=conf,
                        class_id=class_id,
                        class_name=self.get_class_name(class_id),
                        track_id=None
                    )
                    detections.append(result)
        
        # Get annotated frame
        annotated_frame = results[0].plot() if results else frame.copy()
        
        return detections, annotated_frame
    
    def track(
        self, 
        frame: np.ndarray, 
        confidence_threshold: float = 0.5,
        classes: Optional[List[int]] = None
    ) -> Tuple[List[DetectionResult], np.ndarray]:
        """Run detection with tracking (built-in to ultralytics)."""
        if not self._is_loaded:
            self.load_model()
        
        # Run tracking
        results = self.model.track(
            frame,
            conf=confidence_threshold,
            classes=classes,
            persist=True,
            verbose=False
        )
        
        detections = []
        
        # Process results
        for r in results:
            boxes = r.boxes
            if boxes is not None:
                for box in boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                    conf = float(box.conf[0].cpu().numpy())
                    class_id = int(box.cls[0].cpu().numpy())
                    
                    # Get track ID if available
                    track_id = None
                    if box.id is not None:
                        track_id = int(box.id[0].cpu().numpy())
                    
                    result = DetectionResult(
                        bbox=(x1, y1, x2, y2),
                        confidence=conf,
                        class_id=class_id,
                        class_name=self.get_class_name(class_id),
                        track_id=track_id
                    )
                    detections.append(result)
        
        # Get annotated frame
        annotated_frame = results[0].plot() if results else frame.copy()
        
        return detections, annotated_frame
    
    def get_class_names(self) -> Dict[int, str]:
        """Return class names mapping."""
        return self.class_names.copy()
