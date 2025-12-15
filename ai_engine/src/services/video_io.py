import base64
import os
import shutil
import tempfile
from typing import Dict, Optional

import cv2
import numpy as np
from fastapi import HTTPException, UploadFile


def decode_base64_image(image_base64: str) -> np.ndarray:
    """Decode a base64 image string into a numpy array."""
    try:
        payload = image_base64.split(",")[1] if "," in image_base64 else image_base64
        img_bytes = base64.b64decode(payload)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    except Exception:
        raise HTTPException(400, "Invalid image payload")
    if img is None:
        raise HTTPException(400, "Unable to decode image")
    return img


def save_upload_to_temp(file: UploadFile, allow_empty: bool = False) -> str:
    """
    Persist an uploaded file to a secure temporary location without loading everything in memory.
    
    Args:
        file: UploadFile received by FastAPI.
        allow_empty: Whether to allow zero-byte files.
    
    Returns:
        Path to the temporary file on disk.
    """
    try:
        file.file.seek(0)
    except Exception:
        raise HTTPException(400, "Failed to read uploaded file")

    suffix = os.path.splitext(file.filename or "")[1]
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    bytes_written = 0
    try:
        shutil.copyfileobj(file.file, tmp)
        bytes_written = tmp.tell()
    finally:
        tmp.close()
        file.file.seek(0)

    if bytes_written == 0 and not allow_empty:
        os.unlink(tmp.name)
        raise HTTPException(400, "Uploaded file is empty")
    return tmp.name


def ensure_video_duration(path: str, max_seconds: int) -> float:
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise HTTPException(400, "Unable to open uploaded video")
    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    cap.release()
    if fps <= 0 or frames <= 0:
        raise HTTPException(400, "Unable to determine video duration")
    duration = frames / fps
    if duration > max_seconds:
        raise HTTPException(400, f"Video duration {duration:.1f}s exceeds limit of {max_seconds}s")
    return duration


def get_video_metadata(path: str) -> Dict[str, float]:
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise HTTPException(400, "Unable to open uploaded video")
    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    width = cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0
    height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0
    cap.release()
    if fps <= 0 or frames <= 0:
        raise HTTPException(400, "Unable to read video metadata")
    return {
        "fps": float(fps),
        "frame_count": int(frames),
        "width": int(width),
        "height": int(height)
    }


def read_frame_at(path: str, frame_index: int) -> Optional[np.ndarray]:
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return None
    frame_index = max(0, frame_index)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ret, frame = cap.read()
    cap.release()
    return frame if ret else None
