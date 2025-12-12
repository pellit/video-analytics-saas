import os
import time
from typing import List, Dict, Any, Optional

import numpy as np
from fastapi import HTTPException

from .video_utils import bgr_to_cuda
from .jetson_env import JETSON_MODELS_MANIFEST

try:
    import jetson.inference
    import jetson.utils
    JETSON_AVAILABLE = True
except ImportError:
    JETSON_AVAILABLE = False


DETECTNET_MODEL = os.environ.get('DETECTNET_MODEL', 'ssd-mobilenet-v2')
DETECTNET_THRESHOLD = float(os.environ.get('DETECTNET_THRESHOLD', '0.35'))
DETECTNET_TRACKING_ENABLED = os.environ.get('DETECTNET_TRACKING', '1') not in ('0', 'false', 'False')
DETECTNET_TRACKER_MIN_FRAMES = int(os.environ.get('DETECTNET_TRACKER_MIN_FRAMES', '3'))
DETECTNET_TRACKER_DROP_FRAMES = int(os.environ.get('DETECTNET_TRACKER_DROP_FRAMES', '15'))
DETECTNET_TRACKER_OVERLAP = float(os.environ.get('DETECTNET_TRACKER_OVERLAP', '0.5'))
IMAGENET_MODEL = os.environ.get('IMAGENET_MODEL', 'googlenet')
DEPTHNET_MODEL = os.environ.get('DEPTHNET_MODEL', 'resnet18')

_detectnet = None
_imagenet = None
_depthnet_runtime = None
_depthnet_numpy = None
_depthnet_dims = (0, 0)
_detectnet_tracker_configured = False


def _ensure_detectnet():
    global _detectnet, _detectnet_tracker_configured
    if _detectnet is None:
        if not JETSON_AVAILABLE:
            raise HTTPException(503, "jetson-inference no está disponible para detectNet")
        try:
            _detectnet = jetson.inference.detectNet(DETECTNET_MODEL, threshold=DETECTNET_THRESHOLD)
        except Exception as exc:
            hint = JETSON_MODELS_MANIFEST or "networks/models.json"
            raise HTTPException(503, f"detectNet no pudo cargar '{DETECTNET_MODEL}'. Verifica {hint}. Detalle: {exc}")

    if DETECTNET_TRACKING_ENABLED and not _detectnet_tracker_configured:
        _detectnet.SetTrackingEnabled(True)
        try:
            _detectnet.SetTrackingParams(
                minFrames=DETECTNET_TRACKER_MIN_FRAMES,
                dropFrames=DETECTNET_TRACKER_DROP_FRAMES,
                overlapThreshold=DETECTNET_TRACKER_OVERLAP
            )
        except Exception:
            pass
        _detectnet_tracker_configured = True
    elif not DETECTNET_TRACKING_ENABLED and _detectnet_tracker_configured:
        _detectnet.SetTrackingEnabled(False)
        _detectnet_tracker_configured = False

    return _detectnet


def _ensure_imagenet():
    global _imagenet
    if _imagenet is None:
        if not JETSON_AVAILABLE:
            raise HTTPException(503, "jetson-inference no está disponible para imageNet")
        try:
            _imagenet = jetson.inference.imageNet(IMAGENET_MODEL)
        except Exception as exc:
            raise HTTPException(503, f"imageNet no pudo cargar '{IMAGENET_MODEL}': {exc}")
    return _imagenet


def _ensure_depthnet():
    global _depthnet_runtime, _depthnet_numpy, _depthnet_dims
    if _depthnet_runtime is None:
        if not JETSON_AVAILABLE:
            raise HTTPException(503, "jetson-inference no está disponible para depthNet")
        try:
            _depthnet_runtime = jetson.inference.depthNet(DEPTHNET_MODEL)
            depth_field = _depthnet_runtime.GetDepthField()
            _depthnet_dims = (depth_field.width, depth_field.height)
            _depthnet_numpy = jetson.utils.cudaToNumpy(depth_field, depth_field.width, depth_field.height, 1)
        except Exception as exc:
            raise HTTPException(503, f"depthNet no pudo cargar '{DEPTHNET_MODEL}': {exc}")
    return _depthnet_runtime, _depthnet_numpy, _depthnet_dims


def run_detectnet_inference(img: np.ndarray, confidence: float, nms_threshold: float = 0.4) -> Dict[str, Any]:
    """Run detectNet inference and return detections."""
    detect_net = _ensure_detectnet()
    start = time.perf_counter()
    cuda_img = bgr_to_cuda(img)
    detections_raw = detect_net.Detect(cuda_img, overlay="none")
    detections = []
    for det in detections_raw:
        if det.Confidence < confidence:
            continue
        detections.append({
            "class_name": detect_net.GetClassDesc(int(det.ClassID)).lower(),
            "class_id": int(det.ClassID),
            "confidence": round(float(det.Confidence), 2),
            "bbox": [int(det.Left), int(det.Top), int(det.Right), int(det.Bottom)],
            "track_id": int(det.TrackID) if det.TrackID >= 0 else None,
            "area": int(det.Area),
            "status": int(det.TrackStatus) if hasattr(det, "TrackStatus") else None
        })
    return {
        "success": True,
        "detections": detections,
        "time_ms": round((time.perf_counter() - start) * 1000, 2),
    }


def classify_frame_with_imagenet(image: np.ndarray) -> Optional[Dict[str, Any]]:
    if not JETSON_AVAILABLE:
        return None
    try:
        net = _ensure_imagenet()
    except HTTPException:
        return None
    cuda_img = bgr_to_cuda(image)
    class_id, confidence = net.Classify(cuda_img)
    return {
        "class_id": int(class_id),
        "label": net.GetClassDesc(int(class_id)),
        "confidence": float(confidence)
    }


def annotate_depth_for_detections(frame: np.ndarray, detections: List[Dict[str, Any]]):
    if not detections or not JETSON_AVAILABLE:
        return None
    try:
        net, depth_np, dims = _ensure_depthnet()
    except HTTPException:
        return None

    cuda_img = bgr_to_cuda(frame)
    net.Process(cuda_img)
    jetson.utils.cudaDeviceSynchronize()
    depth_map = np.array(depth_np).reshape(dims[1], dims[0])
    scale_x = dims[0] / frame.shape[1]
    scale_y = dims[1] / frame.shape[0]

    for det in detections:
        bbox = det["bbox"]
        x1 = max(0, int(bbox[0] * scale_x))
        y1 = max(0, int(bbox[1] * scale_y))
        x2 = min(depth_map.shape[1], int(bbox[2] * scale_x))
        y2 = min(depth_map.shape[0], int(bbox[3] * scale_y))
        if x2 <= x1 or y2 <= y1:
            continue
        region = depth_map[y1:y2, x1:x2]
        if region.size == 0:
            continue
        det["depth_mean"] = float(np.mean(region))
        det["depth_min"] = float(np.min(region))
        det["depth_max"] = float(np.max(region))

    return {
        "map": depth_map,
        "scale_x": scale_x,
        "scale_y": scale_y
    }


def infer_player_orientation(depth_context: Optional[Dict[str, Any]], bbox: List[int]) -> str:
    if not depth_context:
        return "unknown"
    depth_map = depth_context["map"]
    sx = depth_context["scale_x"]
    sy = depth_context["scale_y"]
    x1 = max(0, int(bbox[0] * sx))
    y1 = max(0, int(bbox[1] * sy))
    x2 = min(depth_map.shape[1], int(bbox[2] * sx))
    y2 = min(depth_map.shape[0], int(bbox[3] * sy))
    if x2 <= x1 or y2 <= y1:
        return "unknown"
    height = y2 - y1
    if height < 4:
        return "unknown"
    upper = depth_map[y1:y1 + height // 3, x1:x2]
    lower = depth_map[y1 + 2 * height // 3:y2, x1:x2]
    if upper.size == 0 or lower.size == 0:
        return "unknown"
    upper_mean = float(np.mean(upper))
    lower_mean = float(np.mean(lower))
    delta = upper_mean - lower_mean
    if delta > 0.1:
        return "facing_camera"
    if delta < -0.1:
        return "facing_away"
    return "sideways"


def infer_contact_side(player_bbox: List[int], ball_bbox: List[int]) -> str:
    px = (player_bbox[0] + player_bbox[2]) / 2.0
    bx = (ball_bbox[0] + ball_bbox[2]) / 2.0
    if bx < px - 5:
        return "left_side"
    if bx > px + 5:
        return "right_side"
    return "center"


def describe_depth_relation(player_depth: Optional[float], ball_depth: Optional[float]) -> str:
    if player_depth is None or ball_depth is None:
        return "unknown"
    delta = ball_depth - player_depth
    if abs(delta) < 0.1:
        return "aligned"
    if delta < 0:
        return "ball_closer_to_camera"
    return "ball_farther_from_camera"
