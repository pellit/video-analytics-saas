import cv2
from typing import Any

try:
    import jetson.utils
except ImportError:
    jetson = None
else:
    jetson = jetson


def bgr_to_cuda(frame) -> Any:
    """Convert BGR frame to CUDA buffer (RGBA)."""
    if jetson is None:
        raise RuntimeError("jetson.utils is required for CUDA conversions on Jetson devices.")
    rgba = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
    return jetson.utils.cudaFromNumpy(rgba)
