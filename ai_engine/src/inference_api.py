"""
Inference-only API for Edge Devices (Jetson Nano)
UPDATED: Uses NanoDet-Plus (NanoDet-Plus-m 416x416 recommended)
"""

import os
import time
import base64
import numpy as np
import cv2
import tempfile
from typing import Optional, List, Dict, Any, Tuple

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .services.video_utils import bgr_to_cuda
from .services.depth_pose import run_depthnet_video, analyze_depth_pose_video as depth_pose_service_analyze
from .services.yolo_service import YoloFallbackService
from .services.video_io import (
    decode_base64_image,
    save_upload_to_temp,
    ensure_video_duration,
    get_video_metadata,
    read_frame_at,
)
from .models.nanodet_plus import NanoDetPlusDetector
from .services.face_service import FaceEmbeddingService
from .services.activity_analysis import ActivityAnalyzer, SOCCER_BALL_LABELS, GYM_EQUIPMENT_LABELS
from .services.actionnet_service import ActionNetService, JETSON_INFERENCE_AVAILABLE as ACTIONNET_AVAILABLE
from .services.hit_detection_service import HitDetectionService
from .services.hit_detection_service_optimized import HitDetectionServiceOptimized
from .services.superres_service import SuperResolutionService
from .services.jetson_env import ensure_jetson_models

JETSON_INFERENCE_AVAILABLE = ACTIONNET_AVAILABLE

# --- Configuration ---
# Default detector: NanoDet-Plus (recommended: NanoDet-Plus-m, 416x416)
# NanoDet es ultra-ligero y muy adecuado para Jetson Nano. Se mantiene
# la compatibilidad con el ModelFactory que mapea 'nanodet' a NanoDet-Plus.
DETECTION_MODEL = os.environ.get('DETECTION_MODEL', 'nanodet')
DETECTION_RESOLUTION = os.environ.get('DETECTION_RESOLUTION', 'medium')
DEVICE_NAME = os.environ.get('DEVICE_NAME', 'jetson-nano')
MAX_VIDEO_DURATION_S = 60

# Optional NVIDIA jetson-inference models
ACTIONNET_MODEL = os.environ.get('ACTIONNET_MODEL', 'resnet18')
ACTIONNET_LABELS = os.environ.get('ACTIONNET_LABELS')
DEPTHNET_MODEL = os.environ.get('DEPTHNET_MODEL', 'resnet18')
POSENET_MODEL = os.environ.get('POSENET_MODEL', 'resnet18-body')

# Models directory
MODELS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../models"))
os.makedirs(MODELS_DIR, exist_ok=True)


def _add_perf_metadata(payload, start_time, frames_processed):
    """Annotate payload with elapsed time (ms) and FPS."""
    elapsed_s = max(time.perf_counter() - start_time, 1e-9)
    payload["elapsed_ms"] = round(elapsed_s * 1000.0, 2)
    frames = frames_processed if frames_processed is not None else 0.0
    fps = (frames / elapsed_s) if frames else 0.0
    payload["analysis_fps"] = round(fps, 2)
    return payload


def _resolve_model_path(preferred_path: str, filename: str) -> str:
    search_dirs = [
        os.path.dirname(preferred_path),
        MODELS_DIR,
        os.path.abspath(os.path.join(os.path.dirname(__file__), "../models")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "../../models")),
        os.path.abspath(os.path.join(os.getcwd(), "models")),
        "/app/ai_engine/models",
        "/app/models",
    ]
    candidates = [preferred_path]
    for directory in search_dirs:
        if directory:
            candidate = os.path.join(directory, filename)
            if candidate not in candidates:
                candidates.append(candidate)
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return os.path.abspath(candidate)
    return preferred_path


FACE_DETECT_MODEL_PATH = _resolve_model_path(
    os.environ.get('FACE_DETECT_MODEL_PATH', os.path.join(MODELS_DIR, 'face_detection_yunet_2023mar.onnx')),
    'face_detection_yunet_2023mar.onnx'
)
FACE_RECOGNITION_MODEL_PATH = _resolve_model_path(
    os.environ.get('FACE_RECOGNITION_MODEL_PATH', os.path.join(MODELS_DIR, 'face_recognition_sface_2021dec.onnx')),
    'face_recognition_sface_2021dec.onnx'
)

JETSON_FACE_NETWORK = os.environ.get('JETSON_FACE_NETWORK', 'facenet-120')
JETSON_FACE_THRESHOLD = float(os.environ.get('JETSON_FACE_THRESHOLD', '0.45'))
SFACE_INPUT_SIZE = (112, 112)
SFACE_TEMPLATE = np.array([
    [38.2946, 51.6963],
    [73.5318, 51.5014],
    [56.0252, 71.7366],
    [41.5493, 92.3655],
    [70.7299, 92.2041]
], dtype=np.float32)
SUPERRES_MODEL_PATH = os.environ.get('SUPERRES_MODEL_PATH')
ESPCN_MODEL_PATH = os.environ.get('ESPCN_MODEL_PATH', os.path.join(MODELS_DIR, 'ESPCN_x4.pb'))
FSRCNN_MODEL_PATH = os.environ.get('FSRCNN_MODEL_PATH', os.path.join(MODELS_DIR, 'FSRCNN_x4.pb'))
SUPERRES_MODELS_DIR_ENV = os.environ.get('SUPERRES_MODELS_DIR', os.path.dirname(ESPCN_MODEL_PATH))
_default_superres_dirs = [
    SUPERRES_MODELS_DIR_ENV,
    os.environ.get('SUPERRES_MODEL_DIR'),
    os.path.abspath(os.path.join(os.getcwd(), "data/networks/Super-Resolution-BSD500")),
    os.path.abspath(os.path.join(os.getcwd(), "data/networks/Super-Resolution--BSD500")),
    "/usr/local/bin/networks/Super-Resolution-BSD500",
    "/usr/local/bin/networks/Super-Resolution--BSD500",
]
SUPERRES_MODEL_DIR = None
for candidate in _default_superres_dirs:
    if candidate and os.path.isdir(candidate):
        SUPERRES_MODEL_DIR = candidate
        break
if SUPERRES_MODEL_DIR is None:
    SUPERRES_MODEL_DIR = _default_superres_dirs[-2]

# Global model instance
BASE_DIR = os.path.dirname(__file__)

yolo_fallback = YoloFallbackService(MODELS_DIR)
face_service = FaceEmbeddingService(
    face_detect_model_path=FACE_DETECT_MODEL_PATH,
    face_recognition_model_path=FACE_RECOGNITION_MODEL_PATH,
    jetson_face_network=JETSON_FACE_NETWORK,
    jetson_face_threshold=JETSON_FACE_THRESHOLD,
    sface_input_size=SFACE_INPUT_SIZE,
    sface_template=SFACE_TEMPLATE,
)


def _decode_face_crop_base64(face_b64: str) -> Optional[np.ndarray]:
    if not face_b64:
        return None
    try:
        data = base64.b64decode(face_b64)
    except Exception:
        return None
    arr = np.frombuffer(data, np.uint8)
    if arr.size == 0:
        return None
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return img


def _compare_faces_for_hit_detection(face_a_b64: str, face_b_b64: str) -> Dict[str, Any]:
    score_threshold = 0.6
    img_a = _decode_face_crop_base64(face_a_b64)
    img_b = _decode_face_crop_base64(face_b_b64)
    if img_a is None or img_b is None:
        raise ValueError("Invalid face crop data for comparison")
    face_a = face_service.get_primary_face_embedding(img_a, score_threshold)
    if not face_a:
        raise ValueError("No face detected in image A")
    face_b = face_service.get_primary_face_embedding(img_b, score_threshold)
    if not face_b:
        raise ValueError("No face detected in image B")
    similarity = face_service.compare_embeddings(face_a["embedding"], face_b["embedding"])
    return {
        "success": True,
        "similarity": similarity,
        "match": similarity >= score_threshold,
        "threshold": score_threshold,
        "face_a": {"face_id": face_a["face_id"], "score": face_a["score"]},
        "face_b": {"face_id": face_b["face_id"], "score": face_b["score"]},
    }

BALL_YOLO_FALLBACK = os.environ.get("BALL_YOLO_FALLBACK", "1").lower() not in ("0", "false", "off")
BALL_YOLO_CONFIDENCE = float(os.environ.get("BALL_YOLO_CONFIDENCE", "0.45"))
BALL_YOLO_NMS = float(os.environ.get("BALL_YOLO_NMS", "0.35"))

activity_analyzer = ActivityAnalyzer(
    yolo_fallback=yolo_fallback,
    enable_ball_fallback=BALL_YOLO_FALLBACK,
    fallback_confidence=BALL_YOLO_CONFIDENCE,
    fallback_nms=BALL_YOLO_NMS,
    soccer_labels=SOCCER_BALL_LABELS,
    gym_labels=GYM_EQUIPMENT_LABELS,
)

actionnet_service = ActionNetService(ACTIONNET_MODEL, ACTIONNET_LABELS)

hit_detection_service = HitDetectionService(
    [
        os.path.join(BASE_DIR, "../models/hit_detect.onnx"),
        os.path.join(BASE_DIR, "../hit_detect.onnx"),
        os.path.join(BASE_DIR, "hit_detect.onnx"),
        os.path.join(MODELS_DIR, "hit_detect.onnx"),
    ],
    face_compare_fn=_compare_faces_for_hit_detection,
)

hit_detection_service_fast = HitDetectionServiceOptimized()

superres_service = SuperResolutionService(SUPERRES_MODEL_DIR, SUPERRES_MODEL_PATH)

# Optional NanoDet-Plus detector and MiDaS ONNX depth model
_nanodet_detector: Optional[NanoDetPlusDetector] = None
_midas_net = None
_midas_input_size = (256, 256)  # default for MiDaS small

# --- FastAPI App ---
app = FastAPI(title="Jetson Inference API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    print("🚀 Starting Inference API...")
    try:
        yolo_fallback.ensure_ready()
    except HTTPException as exc:
        print(f"⚠️ YOLO fallback no disponible: {exc.detail}")
    _log_environment_status()
    ensure_jetson_models()

# --- Request/Response ---
class DetectionRequest(BaseModel):
    image_base64: str
    confidence: float = 0.5
    nms_threshold: float = 0.4

class BatchDetectionRequest(BaseModel):
    images_base64: List[str]
    confidence: float = 0.5
    nms_threshold: float = 0.4
class ActionImageRequest(BaseModel):
    image_base64: str
    top_k: int = 3


class FaceDetectionRequest(BaseModel):
    image_base64: str
    score_threshold: float = 0.6


class FaceCompareRequest(BaseModel):
    image_a_base64: str
    image_b_base64: str
    score_threshold: float = 0.6

class DepthRequest(BaseModel):
    image_base64: str

class SuperResRequest(BaseModel):
    image_base64: str
    model: Optional[str] = None  # path override or keywords 'espcn'/'fsrcnn'

@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": yolo_fallback.model_name,
        "cuda": cv2.cuda.getCudaEnabledDeviceCount() > 0
    }


def _decode_base64_image(image_base64: str) -> np.ndarray:
    return decode_base64_image(image_base64)


def _save_upload_to_temp(file: UploadFile) -> str:
    return save_upload_to_temp(file)


def _ensure_video_duration(path: str, max_seconds: int = MAX_VIDEO_DURATION_S):
    return ensure_video_duration(path, max_seconds)


def _get_video_metadata(path: str) -> Dict[str, float]:
    return get_video_metadata(path)


def _ensure_nanodet_detector() -> NanoDetPlusDetector:
    """Lazy-load NanoDet-Plus for CPU fallback."""
    global _nanodet_detector
    if _nanodet_detector is None:
        try:
            detector = NanoDetPlusDetector(device='cpu')
            detector.load_model()
            _nanodet_detector = detector
            print("✅ NanoDet-Plus cargado como fallback de detección")
        except Exception as exc:
            raise HTTPException(503, f"NanoDet-Plus no disponible: {exc}")
    return _nanodet_detector


def _run_nanodet_fallback(img: np.ndarray, confidence: float) -> Dict[str, Any]:
    """Execute NanoDet-Plus and format detections like detectNet."""
    detector = _ensure_nanodet_detector()
    start = time.perf_counter()
    detections, _ = detector.detect(img, confidence_threshold=confidence)
    formatted = []
    for det in detections:
        bbox = list(map(int, det.bbox))
        formatted.append({
            "class_name": det.class_name,
            "class_id": int(det.class_id),
            "confidence": round(float(det.confidence), 3),
            "bbox": bbox,
            "track_id": det.track_id,
            "area": (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]),
            "status": None,
            "source": "nanodet",
            "engine": "nanodet-plus-m_416"
        })
    return {
        "success": True,
        "detections": formatted,
        "time_ms": round((time.perf_counter() - start) * 1000, 2),
        "engine": "nanodet-plus"
    }


def _build_sample_indices(frame_count: int, sample_interval_pct: int) -> List[int]:
    """Return sorted frame indices sampled every `sample_interval_pct` percent."""
    if frame_count <= 0:
        return []
    interval = max(1, min(sample_interval_pct, 100))
    percents = list(range(0, 101, interval))
    if percents[-1] != 100:
        percents.append(100)
    indices: List[int] = []
    last_idx = None
    for pct in percents:
        idx = int(round((frame_count - 1) * (pct / 100.0)))
        if idx < 0:
            idx = 0
        if idx >= frame_count:
            idx = frame_count - 1
        if last_idx is None or idx != last_idx:
            indices.append(idx)
            last_idx = idx
    return indices


def _log_environment_status():
    """Muestra info útil al iniciar: CUDA y rutas de modelos."""
    try:
        cuda_devices = cv2.cuda.getCudaEnabledDeviceCount()
    except Exception as exc:
        cuda_devices = 0
        print(f"⚠️ No se pudo consultar CUDA: {exc}")
    if cuda_devices > 0:
        print(f"✅ CUDA disponible: {cuda_devices} device(s)")
    else:
        print("⚠️ CUDA no detectado por OpenCV (cpu fallback)")

    model_dirs = {
        "jetson_networks": "/usr/local/bin/networks",
        "jetson_inference_data": "/jetson-inference/data/networks",
        "repo_data_networks": os.path.abspath(os.path.join(os.getcwd(), "data/networks")),
        "superres_dir": SUPERRES_MODEL_DIR,
    }
    for name, path in model_dirs.items():
        if path and os.path.isdir(path):
            print(f"✅ Directorio de modelos '{name}' listo: {path}")
        else:
            print(f"⚠️ Directorio de modelos '{name}' no disponible: {path}")


def _run_inference(img: np.ndarray, confidence: float, nms_threshold: float) -> dict:
    """Wrapper around detectNet inference service with optional YOLO fallback for the ball."""
    try:
        return activity_analyzer.run_inference(img, confidence, nms_threshold)
    except HTTPException as exc:
        detail = str(exc.detail)
        if 'jetson-inference' in detail.lower() or 'detectnet' in detail.lower():
            fallback = _run_nanodet_fallback(img, confidence)
            fallback["warning"] = detail
            return fallback
        raise


def _compute_player_motion_metrics(timeline: List[Dict[str, Any]], fps: float) -> Dict[str, Any]:
    return activity_analyzer.compute_player_motion_metrics(timeline, fps)


def _summarize_orientation(timeline: List[Dict[str, Any]]) -> Dict[str, Any]:
    return activity_analyzer.summarize_orientation(timeline)


def _build_activity_report(
    metadata: Dict[str, Any],
    detection_summary: Dict[str, Any],
    action_analysis: Dict[str, Any],
    action_sequences: Dict[str, Any],
    motion_metrics: Dict[str, Any],
    orientation_summary: Dict[str, Any],
    face_checks: Dict[str, Any]
) -> Dict[str, Any]:
    return activity_analyzer.build_activity_report(
        metadata=metadata,
        detection_summary=detection_summary,
        action_analysis=action_analysis,
        action_sequences=action_sequences,
        motion_metrics=motion_metrics,
        orientation_summary=orientation_summary,
        face_checks=face_checks
    )


def _analyze_soccer_detections(
    video_path: str,
    frame_stride: int,
    max_frames: int,
    confidence: float,
    possession_distance_px: int,
    contact_threshold_px: Optional[int] = None,
    nms_threshold: float = 0.4
) -> Dict[str, Any]:
    return activity_analyzer.analyze_soccer_detections(
        video_path=video_path,
        frame_stride=frame_stride,
        max_frames=max_frames,
        confidence=confidence,
        possession_distance_px=possession_distance_px,
        contact_threshold_px=contact_threshold_px,
        nms_threshold=nms_threshold,
    )


def _analyze_gym_detections(
    video_path: str,
    frame_stride: int,
    max_frames: int,
    confidence: float,
    interaction_distance_px: int,
    nms_threshold: float = 0.4
) -> Dict[str, Any]:
    return activity_analyzer.analyze_gym_detections(
        video_path=video_path,
        frame_stride=frame_stride,
        max_frames=max_frames,
        confidence=confidence,
        interaction_distance_px=interaction_distance_px,
        nms_threshold=nms_threshold,
    )


def _evaluate_face_consistency(
    video_path: str,
    frame_count: int,
    score_threshold: float,
    match_threshold: float
) -> Dict[str, Any]:
    return face_service.evaluate_face_consistency(
        video_path=video_path,
        frame_count=frame_count,
        score_threshold=score_threshold,
        match_threshold=match_threshold
    )


def _derive_action_sequences(
    predictions: List[Dict[str, Any]],
    frame_stride: int,
    fps: float
) -> Dict[str, Any]:
    return activity_analyzer.derive_action_sequences(
        predictions=predictions,
        frame_stride=frame_stride,
        fps=fps
    )


def _run_actionnet_on_image(image: np.ndarray, top_k: int):
    return actionnet_service.classify_image(image, top_k)


def _run_actionnet_on_video(video_path: str, frame_stride: int, top_k: int):
    return actionnet_service.classify_video(video_path, frame_stride, top_k)


def _run_hit_detection_on_video(
    video_path: str,
    frame_stride: int,
    max_frames: int,
    hit_threshold: float,
    return_images: bool = False,
):
    return hit_detection_service.run_on_video(
        video_path=video_path,
        frame_stride=frame_stride,
        max_frames=max_frames,
        hit_threshold=hit_threshold,
        return_images=return_images,
    )


def _detect_faces_with_embeddings(image: np.ndarray, score_threshold: float = 0.6) -> List[Dict[str, Any]]:
    return face_service.detect_with_embeddings(image, score_threshold)


def _get_primary_face_embedding(image: np.ndarray, min_score: float = 0.6) -> Optional[Dict[str, Any]]:
    return face_service.get_primary_face_embedding(image, min_score)


def _encode_image_to_base64(img: np.ndarray) -> str:
    _, buf = cv2.imencode('.jpg', img)
    return 'data:image/jpeg;base64,' + base64.b64encode(buf.tobytes()).decode('ascii')


def _segment_scene(image: np.ndarray, segments: int = 5) -> np.ndarray:
    """
    Simple color-based segmentation using k-means clustering.
    Returns a pseudo-colored mask for visualization purposes.
    """
    h, w = image.shape[:2]
    data = image.reshape((-1, 3)).astype(np.float32)
    K = max(2, min(segments, 12))
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
    attempts = 3
    _, labels, centers = cv2.kmeans(data, K, None, criteria, attempts, cv2.KMEANS_PP_CENTERS)
    centers = np.uint8(centers)
    mask = centers[labels.flatten()].reshape((h, w, 3))
    # Enhance separation by blending with original image
    segmented = cv2.addWeighted(image, 0.4, mask, 0.6, 0)
    return segmented


def _crop_face(frame: np.ndarray, bbox: List[int]) -> np.ndarray:
    x1, y1, x2, y2 = [int(v) for v in bbox]
    h, w = frame.shape[:2]
    x1 = max(0, min(x1, w - 1))
    x2 = max(0, min(x2, w))
    y1 = max(0, min(y1, h - 1))
    y2 = max(0, min(y2, h))
    if x2 <= x1 or y2 <= y1:
        return frame
    crop = frame[y1:y2, x1:x2]
    return crop if crop is not None and crop.size > 0 else frame


def _ensure_midas_net():
    """Load MiDaS ONNX model defined in MIDAS_MODEL_PATH."""
    global _midas_net
    if _midas_net is not None:
        return _midas_net
    model_path = os.environ.get('MIDAS_MODEL_PATH', os.path.join(MODELS_DIR, 'midas_v21_small.onnx'))
    if not os.path.exists(model_path):
        raise HTTPException(503, f"MiDaS no encontrado en {model_path}")
    net = cv2.dnn.readNet(model_path)
    try:
        if cv2.cuda.getCudaEnabledDeviceCount() > 0:
            net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
            net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
        else:
            net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
    except Exception:
        net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
    _midas_net = net
    print("✅ MiDaS ONNX cargado para estimación de profundidad")
    return _midas_net


def _run_midas_depth(frame: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Return MiDaS raw depth map and normalized map (0-1)."""
    net = _ensure_midas_net()
    blob = cv2.dnn.blobFromImage(
        frame,
        scalefactor=1 / 255.0,
        size=_midas_input_size,
        mean=(123.675, 116.28, 103.53),
        swapRB=True,
        crop=False
    )
    net.setInput(blob)
    depth = net.forward()
    depth = np.squeeze(depth)
    depth = cv2.resize(depth, (frame.shape[1], frame.shape[0]))
    depth_min = float(depth.min())
    depth_max = float(depth.max())
    depth_norm = (depth - depth_min) / (depth_max - depth_min + 1e-6)
    depth_norm = np.clip(depth_norm, 0.0, 1.0)
    return depth, depth_norm


def _depth_to_base64(depth_norm: np.ndarray) -> str:
    depth_img = (depth_norm * 255).astype(np.uint8)
    depth_color = cv2.applyColorMap(depth_img, cv2.COLORMAP_INFERNO)
    return _encode_image_to_base64(depth_color)


def _resolve_superres_model_path(model_hint: Optional[str]) -> Optional[str]:
    if not model_hint:
        return None
    hint = model_hint.strip().lower()
    if hint in ("espcn", "espcn_x4", "espcn4"):
        return ESPCN_MODEL_PATH
    if hint in ("fsrcnn", "fsrcnn_x4", "fsrcnn4"):
        return FSRCNN_MODEL_PATH
    if os.path.exists(model_hint):
        return model_hint
    candidate = os.path.join(SUPERRES_MODELS_DIR_ENV, model_hint)
    if os.path.exists(candidate):
        return candidate
    return model_hint


def _run_super_resolution(frame: np.ndarray, model_hint: Optional[str] = None) -> Tuple[np.ndarray, int]:
    """Upscale frame using cv2.dnn_superres via SuperResolutionService."""
    model_path = _resolve_superres_model_path(model_hint)
    engine, scale = superres_service.load_engine(model_path)
    upscaled = engine.upsample(frame)
    return upscaled, scale


def _superres_response_from_base64(image_base64: str, model_hint: Optional[str] = None) -> Dict[str, Any]:
    img = _decode_base64_image(image_base64)
    upscaled, scale = _run_super_resolution(img, model_hint)
    return {
        "success": True,
        "scale": scale,
        "original_size": {"width": int(img.shape[1]), "height": int(img.shape[0])},
        "upscaled_size": {"width": int(upscaled.shape[1]), "height": int(upscaled.shape[0])},
        "image_base64": _encode_image_to_base64(upscaled)
    }


def _superres_endpoint_response(req: SuperResRequest, model_hint: Optional[str]) -> Dict[str, Any]:
    start_time = time.perf_counter()
    payload = _superres_response_from_base64(req.image_base64, model_hint or req.model)
    return _add_perf_metadata(payload, start_time, frames_processed=1)
@app.post("/superres/espcn")
def superres_espcn(req: SuperResRequest):
    return _superres_endpoint_response(req, "espcn")


@app.post("/superres/fsrcnn")
def superres_fsrcnn(req: SuperResRequest):
    return _superres_endpoint_response(req, "fsrcnn")


@app.post("/superres/apply")
def superres_apply(req: SuperResRequest):
    if not req.model:
        raise HTTPException(400, "Debes enviar el campo 'model' (ej: 'espcn' o 'fsrcnn').")
    return _superres_endpoint_response(req, req.model)

@app.post("/detect")
def detect(req: DetectionRequest):
    start_time = time.perf_counter()
    img = _decode_base64_image(req.image_base64)
    result = _run_inference(img, req.confidence, req.nms_threshold)
    return _add_perf_metadata(result, start_time, frames_processed=1)


@app.post("/detect/nanodet")
def detect_nanodet(req: DetectionRequest):
    """Ejecuta NanoDet-Plus directamente sin pasar por detectNet."""
    start_time = time.perf_counter()
    img = _decode_base64_image(req.image_base64)
    result = _run_nanodet_fallback(img, req.confidence)
    return _add_perf_metadata(result, start_time, frames_processed=1)


@app.post("/face/consistency-video")
def face_consistency_video(
    file: UploadFile = File(...),
    confidence: float = Form(0.6),
    match_threshold: float = Form(0.7),
    sample_interval_pct: int = Form(20),
):
    """Analiza un video muestreando frames cada `sample_interval_pct` por ciento
    y determina si la misma persona aparece en todos los samples. Devuelve
    un resumen y una foto por cada cara distinta detectada.
    """
    # Guardar upload
    video_path = _save_upload_to_temp(file)
    # Validar duración y metadatos
    _ensure_video_duration(video_path, MAX_VIDEO_DURATION_S)
    meta = _get_video_metadata(video_path)
    frame_count = int(meta.get("frame_count", 0))
    if frame_count <= 0:
        raise HTTPException(400, "No se pudieron leer frames del video")

    if sample_interval_pct <= 0 or sample_interval_pct > 100:
        raise HTTPException(400, "sample_interval_pct debe estar entre 1 y 100")
    indices = _build_sample_indices(frame_count, sample_interval_pct)

    distinct_faces_embeddings: List[List[float]] = []
    distinct_faces_images: List[str] = []
    distinct_faces_counts: List[int] = []

    samples_report = []

    for idx in indices:
        from .services.video_io import read_frame_at as _read_frame_at
        frame = _read_frame_at(video_path, int(idx))
        sample = {"frame": int(idx), "success": False, "faces": []}
        if frame is None:
            sample["error"] = "frame_unavailable"
            samples_report.append(sample)
            continue

        faces = face_service.detect_with_embeddings(frame, confidence)
        if not faces:
            sample["error"] = "no_faces"
            samples_report.append(sample)
            continue

        sample["success"] = True
        for f in faces:
            emb = f.get("embedding")
            bbox = f.get("bbox")
            score = float(f.get("score", 0.0))
            # Compare to known distinct faces
            matched_idx = None
            for di, de in enumerate(distinct_faces_embeddings):
                try:
                    sim = face_service.compare_embeddings(de, emb)
                except Exception:
                    sim = 0.0
                if sim >= match_threshold:
                    matched_idx = di
                    distinct_faces_counts[di] += 1
                    break
            if matched_idx is None:
                # new distinct face
                distinct_faces_embeddings.append(emb)
                # crop image
                x1, y1, x2, y2 = bbox
                x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                # clamp to frame bounds
                h, w = frame.shape[:2]
                x1, x2 = max(0, min(x1, w - 1)), max(0, min(x2, w - 1))
                y1, y2 = max(0, min(y1, h - 1)), max(0, min(y2, h - 1))
                try:
                    crop = frame[y1:y2, x1:x2]
                    if crop is None or crop.size == 0:
                        crop = frame
                except Exception:
                    crop = frame
                img_b64 = _encode_image_to_base64(crop)
                distinct_faces_images.append(img_b64)
                distinct_faces_counts.append(1)
                matched_idx = len(distinct_faces_embeddings) - 1

            sample["faces"].append({
                "distinct_id": matched_idx,
                "score": score,
                "bbox": bbox,
            })

        samples_report.append(sample)

    consistent = len(distinct_faces_embeddings) <= 1 and len(distinct_faces_embeddings) > 0

    result = {
        "consistent": consistent,
        "match_threshold": match_threshold,
        "sample_interval_pct": sample_interval_pct,
        "frame_count": frame_count,
        "samples": samples_report,
        "distinct_faces_count": len(distinct_faces_embeddings),
        "distinct_faces_images": distinct_faces_images,
        "distinct_faces_occurrences": distinct_faces_counts,
    }

    return result


@app.post("/face/video-summary")
def face_video_summary(
    file: UploadFile = File(...),
    confidence: float = Form(0.6),
    match_threshold: float = Form(0.7),
    sample_interval_pct: int = Form(20),
):
    """
    Extrae capturas aproximadamente cada `sample_interval_pct`% del video y
    reporta si se trata de la misma persona. Devuelve un resumen y un recorte
    (base64) por cada rostro distinto detectado.
    """
    video_path = _save_upload_to_temp(file)
    _ensure_video_duration(video_path, MAX_VIDEO_DURATION_S)
    metadata = _get_video_metadata(video_path)
    frame_count = int(metadata.get("frame_count", 0))
    if frame_count <= 0:
        raise HTTPException(400, "No se pudieron leer frames del video")
    if sample_interval_pct <= 0 or sample_interval_pct > 100:
        raise HTTPException(400, "sample_interval_pct debe estar entre 1 y 100")

    indices = _build_sample_indices(frame_count, sample_interval_pct)
    if not indices:
        raise HTTPException(400, "No hay frames para muestrear en este video")

    distinct_faces: List[Dict[str, Any]] = []
    samples: List[Dict[str, Any]] = []

    for idx in indices:
        frame = read_frame_at(video_path, idx)
        sample_pct = round((idx / max(frame_count - 1, 1)) * 100.0, 2)
        sample_entry = {
            "frame": idx,
            "percent": sample_pct,
            "faces": [],
            "success": False
        }
        if frame is None:
            sample_entry["error"] = "frame_unavailable"
            samples.append(sample_entry)
            continue

        faces = face_service.detect_with_embeddings(frame, confidence)
        if not faces:
            sample_entry["error"] = "no_faces"
            samples.append(sample_entry)
            continue

        sample_entry["success"] = True
        for detected in faces:
            embedding = detected.get("embedding")
            bbox = detected.get("bbox")
            score = float(detected.get("score", 0.0))
            matched_idx = None
            for di, distinct in enumerate(distinct_faces):
                try:
                    similarity = face_service.compare_embeddings(distinct["embedding"], embedding)
                except Exception:
                    similarity = 0.0
                if similarity >= match_threshold:
                    matched_idx = di
                    distinct_faces[di]["occurrences"] += 1
                    break
            if matched_idx is None:
                x1, y1, x2, y2 = [int(v) for v in bbox]
                h, w = frame.shape[:2]
                x1, x2 = max(0, min(x1, w - 1)), max(0, min(x2, w - 1))
                y1, y2 = max(0, min(y1, h - 1)), max(0, min(y2, h - 1))
                crop = frame[y1:y2, x1:x2]
                if crop is None or crop.size == 0:
                    crop = frame
                matched_idx = len(distinct_faces)
                distinct_faces.append({
                    "face_id": matched_idx + 1,
                    "embedding": embedding,
                    "image": _encode_image_to_base64(crop),
                    "first_frame": idx,
                    "occurrences": 1
                })
            sample_entry["faces"].append({
                "face_id": distinct_faces[matched_idx]["face_id"],
                "score": score,
                "bbox": bbox
            })
        samples.append(sample_entry)

    consistent = len(distinct_faces) == 1
    if not distinct_faces:
        summary = "No se detectaron rostros en las capturas del video."
    elif consistent:
        summary = "Se observó a la misma persona en todas las muestras analizadas."
    else:
        summary = f"Se detectaron {len(distinct_faces)} personas distintas en las muestras."

    return {
        "consistent": consistent,
        "summary": summary,
        "sample_interval_pct": sample_interval_pct,
        "frame_count": frame_count,
        "video_duration_s": metadata.get("duration"),
        "distinct_faces": distinct_faces,
        "samples": samples
    }


@app.post("/face/video-total-summary")
def face_video_total_summary(
    file: UploadFile = File(...),
    confidence: float = Form(0.6),
    match_threshold: float = Form(0.7),
    frame_stride: int = Form(5),
    max_frames: int = Form(500),
):
    """
    Analiza todo el video (saltando `frame_stride` frames) para detectar y agrupar
    todas las caras. Devuelve una lista de rostros únicos con su mejor captura,
    embedding y el momento en el que aparecieron por primera vez.
    """
    if frame_stride <= 0:
        raise HTTPException(400, "frame_stride debe ser mayor a 0")
    if max_frames <= 0:
        raise HTTPException(400, "max_frames debe ser mayor a 0")

    video_path = _save_upload_to_temp(file)
    _ensure_video_duration(video_path, MAX_VIDEO_DURATION_S)
    metadata = _get_video_metadata(video_path)
    fps = float(metadata.get("fps") or 0)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise HTTPException(400, "No se pudo abrir el video")

    distinct_faces: List[Dict[str, Any]] = []
    samples: List[Dict[str, Any]] = []

    frame_idx = 0
    processed = 0
    try:
        while processed < max_frames:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % frame_stride != 0:
                frame_idx += 1
                continue

            faces = face_service.detect_with_embeddings(frame, confidence)
            frame_entry = {
                "frame": frame_idx,
                "timestamp_s": round(frame_idx / fps, 2) if fps > 0 else None,
                "faces": []
            }
            for detected in faces:
                embedding = detected.get("embedding")
                bbox = detected.get("bbox")
                score = float(detected.get("score", 0.0))
                face_id = None
                for existing in distinct_faces:
                    try:
                        similarity = face_service.compare_embeddings(existing["embedding"], embedding)
                    except Exception:
                        similarity = 0.0
                    if similarity >= match_threshold:
                        face_id = existing["face_id"]
                        existing["occurrences"] += 1
                        existing["last_frame"] = frame_idx
                        if fps > 0:
                            existing["last_timestamp_s"] = round(frame_idx / fps, 2)
                        if score > existing["best_score"]:
                            existing["best_score"] = score
                            existing["best_image"] = _encode_image_to_base64(_crop_face(frame, bbox))
                        break
                if face_id is None:
                    face_id = len(distinct_faces) + 1
                    first_ts = round(frame_idx / fps, 2) if fps > 0 else None
                    distinct_faces.append({
                        "face_id": face_id,
                        "embedding": embedding,
                        "best_score": score,
                        "best_image": _encode_image_to_base64(_crop_face(frame, bbox)),
                        "occurrences": 1,
                        "first_frame": frame_idx,
                        "first_timestamp_s": first_ts,
                        "last_frame": frame_idx,
                        "last_timestamp_s": first_ts
                    })
                frame_entry["faces"].append({
                    "face_id": face_id,
                    "score": score,
                    "bbox": bbox
                })

            samples.append(frame_entry)
            processed += 1
            frame_idx += 1
    finally:
        cap.release()
        if os.path.exists(video_path):
            os.remove(video_path)

    summary = {
        "distinct_faces_count": len(distinct_faces),
        "distinct_faces": distinct_faces,
        "frames_processed": processed,
        "frame_stride": frame_stride,
        "match_threshold": match_threshold,
        "confidence": confidence,
        "video_duration_s": metadata.get("duration"),
        "samples": samples
    }
    return summary


@app.post("/detect/batch")
def detect_batch(req: BatchDetectionRequest):
    """Analyze multiple images in a single request."""
    if not req.images_base64:
        raise HTTPException(400, "images_base64 list cannot be empty")

    start_time = time.perf_counter()
    batch_results = []
    for idx, image_base64 in enumerate(req.images_base64):
        try:
            img = _decode_base64_image(image_base64)
            result = _run_inference(img, req.confidence, req.nms_threshold)
            batch_results.append({"index": idx, **result})
        except HTTPException as exc:
            batch_results.append({"index": idx, "success": False, "error": exc.detail})

    payload = {"success": True, "frames": len(batch_results), "results": batch_results}
    frames_processed = len(req.images_base64)
    return _add_perf_metadata(payload, start_time, frames_processed=frames_processed)


@app.post("/detect/video")
async def detect_video(
    file: UploadFile = File(...),
    confidence: float = Form(0.5),
    nms_threshold: float = Form(0.4),
    max_frames: int = Form(200),
    frame_stride: int = Form(5),
):
    """Upload a short video and analyze sampled frames."""
    if max_frames <= 0:
        raise HTTPException(400, "max_frames must be > 0")
    if frame_stride <= 0:
        raise HTTPException(400, "frame_stride must be > 0")

    start_time = time.perf_counter()
    tmp_path = _save_upload_to_temp(file)
    try:
        cap = cv2.VideoCapture(tmp_path)
        if not cap.isOpened():
            raise HTTPException(400, "Unable to open uploaded video")

        results = []
        frame_idx = 0
        processed = 0

        while processed < max_frames:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % frame_stride != 0:
                frame_idx += 1
                continue

            result = _run_inference(frame, confidence, nms_threshold)
            result["frame_number"] = frame_idx
            results.append(result)
            processed += 1
            frame_idx += 1

        cap.release()
        payload = {
            "success": True,
            "frames_analyzed": processed,
            "frame_stride": frame_stride,
            "results": results,
        }
        return _add_perf_metadata(payload, start_time, frames_processed=processed)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.post("/detect/nanodet/video")
async def detect_nanodet_video(
    file: UploadFile = File(...),
    confidence: float = Form(0.5),
    frame_stride: int = Form(5),
    max_frames: int = Form(200),
):
    """Analiza un video usando NanoDet-Plus directamente."""
    if frame_stride <= 0:
        raise HTTPException(400, "frame_stride must be > 0")
    if max_frames <= 0:
        raise HTTPException(400, "max_frames must be > 0")

    start_time = time.perf_counter()
    tmp_path = _save_upload_to_temp(file)
    try:
        cap = cv2.VideoCapture(tmp_path)
        if not cap.isOpened():
            raise HTTPException(400, "Unable to open uploaded video")

        frames = []
        frame_idx = 0
        processed = 0
        while processed < max_frames:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % frame_stride != 0:
                frame_idx += 1
                continue
            inference = _run_nanodet_fallback(frame, confidence)
            inference["frame_number"] = frame_idx
            frames.append(inference)
            processed += 1
            frame_idx += 1
        cap.release()
        payload = {
            "success": True,
            "frames_analyzed": processed,
            "frame_stride": frame_stride,
            "results": frames,
        }
        return _add_perf_metadata(payload, start_time, frames_processed=processed)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.post("/face/detect")
def face_detect(req: FaceDetectionRequest):
    start_time = time.perf_counter()
    img = _decode_base64_image(req.image_base64)
    faces = _detect_faces_with_embeddings(img, req.score_threshold)
    payload = {
        "success": True,
        "count": len(faces),
        "faces": faces
    }
    return _add_perf_metadata(payload, start_time, frames_processed=1)


@app.post("/face/compare")
def face_compare(req: FaceCompareRequest):
    img_a = _decode_base64_image(req.image_a_base64)
    img_b = _decode_base64_image(req.image_b_base64)

    face_a = _get_primary_face_embedding(img_a, req.score_threshold)
    if not face_a:
        raise HTTPException(422, "No face detected in image A above the threshold")
    face_b = _get_primary_face_embedding(img_b, req.score_threshold)
    if not face_b:
        raise HTTPException(422, "No face detected in image B above the threshold")

    similarity = face_service.compare_embeddings(face_a["embedding"], face_b["embedding"])
    is_same = similarity >= req.score_threshold

    return {
        "success": True,
        "similarity": similarity,
        "match": is_same,
        "threshold": req.score_threshold,
        "face_a": {"face_id": face_a["face_id"], "score": face_a["score"]},
        "face_b": {"face_id": face_b["face_id"], "score": face_b["score"]}
    }


@app.post("/depth/midas")
def depth_midas(req: DepthRequest):
    """Ejecuta MiDaS v2.1 Small para estimar profundidad en una imagen."""
    start_time = time.perf_counter()
    img = _decode_base64_image(req.image_base64)
    depth_raw, depth_norm = _run_midas_depth(img)
    payload = {
        "success": True,
        "depth_min": float(depth_raw.min()),
        "depth_max": float(depth_raw.max()),
        "depth_map_base64": _depth_to_base64(depth_norm),
    }
    return _add_perf_metadata(payload, start_time, frames_processed=1)


@app.post("/depth/midas/video")
def depth_midas_video(
    file: UploadFile = File(...),
    frame_stride: int = Form(5),
    max_frames: int = Form(100),
):
    """Procesa un video completo con MiDaS (saltando frame_stride)."""
    if frame_stride <= 0:
        raise HTTPException(400, "frame_stride must be > 0")
    if max_frames <= 0:
        raise HTTPException(400, "max_frames must be > 0")

    video_path = _save_upload_to_temp(file)
    _ensure_video_duration(video_path, MAX_VIDEO_DURATION_S)
    meta = _get_video_metadata(video_path)
    fps = float(meta.get("fps") or 0)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise HTTPException(400, "Unable to open uploaded video")

    frames = []
    frame_idx = 0
    processed = 0
    try:
        while processed < max_frames:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % frame_stride != 0:
                frame_idx += 1
                continue
            _, depth_norm = _run_midas_depth(frame)
            frames.append({
                "frame": frame_idx,
                "timestamp_s": round(frame_idx / fps, 2) if fps > 0 else None,
                "depth_map_base64": _depth_to_base64(depth_norm)
            })
            processed += 1
            frame_idx += 1
    finally:
        cap.release()
        if os.path.exists(video_path):
            os.remove(video_path)

    return {
        "success": True,
        "frames_processed": processed,
        "frame_stride": frame_stride,
        "video_duration_s": meta.get("duration"),
        "depth_frames": frames
    }


@app.post("/detect/hit/video")
async def detect_hit_video(
    file: UploadFile = File(...),
    frame_stride: int = Form(1),
    max_frames: int = Form(1800),
    hit_threshold: float = Form(0.1),
    return_images: bool = Form(False),
):
    tmp_path = _save_upload_to_temp(file)
    try:
        # Obtener duración y FPS del video
        cap = cv2.VideoCapture(tmp_path)
        if not cap.isOpened():
            raise HTTPException(400, "Unable to open uploaded video")
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not fps or fps <= 0:
            fps = 30  # Valor por defecto si no se puede leer
        duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps if fps > 0 else 0
        cap.release()

        # Detectar si CUDA está habilitada
        cuda_enabled = False
        try:
            cuda_enabled = cv2.cuda.getCudaEnabledDeviceCount() > 0
        except Exception:
            cuda_enabled = False

        # Asignar valores por defecto si no se especifican
        if frame_stride is None:
            frame_stride = 1 if cuda_enabled else 3
        if hit_threshold is None:
            hit_threshold = 0.4
        if max_frames is None:
            max_frames = int(fps * 60)  # 1 minuto

        if frame_stride <= 0:
            raise HTTPException(400, "frame_stride must be > 0")
        if max_frames <= 0:
            raise HTTPException(400, "max_frames must be > 0")
        if hit_threshold < 0 or hit_threshold > 1:
            raise HTTPException(400, "hit_threshold must be between 0 and 1")

        results = _run_hit_detection_on_video(
            tmp_path,
            frame_stride,
            max_frames,
            hit_threshold,
            return_images=return_images,
        )
        return {
            "success": True,
            "video_duration_s": duration,
            **results
        }
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.post("/detect/hit/fast/video")
async def detect_hit_fast_video(
    file: UploadFile = File(...),
    frame_stride: int = Form(1),
    max_frames: int = Form(1800),
    hit_threshold: float = Form(0.1),
    return_images: bool = Form(False),
):
    tmp_path = _save_upload_to_temp(file)
    try:
        cap = cv2.VideoCapture(tmp_path)
        if not cap.isOpened():
            raise HTTPException(400, "Unable to open uploaded video")
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not fps or fps <= 0:
            fps = 30
        duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps if fps > 0 else 0
        cap.release()

        cuda_enabled = False
        try:
            cuda_enabled = cv2.cuda.getCudaEnabledDeviceCount() > 0
        except Exception:
            cuda_enabled = False

        if frame_stride is None:
            frame_stride = 1 if cuda_enabled else 3
        if hit_threshold is None:
            hit_threshold = 0.4
        if max_frames is None:
            max_frames = int(fps * 60)

        if frame_stride <= 0:
            raise HTTPException(400, "frame_stride must be > 0")
        if max_frames <= 0:
            raise HTTPException(400, "max_frames must be > 0")
        if hit_threshold < 0 or hit_threshold > 1:
            raise HTTPException(400, "hit_threshold must be between 0 and 1")

        results = hit_detection_service_fast.run_on_video(
            tmp_path,
            frame_stride,
            max_frames,
            hit_threshold,
            return_images=return_images,
        )
        return {
            "success": True,
            "video_duration_s": duration,
            **results
        }
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.post("/segment/image")
async def segment_image(
    file: UploadFile = File(...),
    segments: int = Form(5)
):
    """
    Simple scene segmentation helper.
    Returns a pseudo-colored segmentation mask (for quick tests).
    """
    if segments < 2:
        raise HTTPException(400, "segments must be >= 2")
    data = await file.read()
    np_arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "Invalid image")
    segmented = _segment_scene(img, segments)
    return {
        "success": True,
        "segments": segments,
        "segmentation_image_base64": _encode_image_to_base64(segmented)
    }


@app.post("/analyze/depth_pose/video")
async def analyze_depth_pose_video(
    file: UploadFile = File(...),
    frame_stride: int = Form(4),
    max_frames: int = Form(150),
    detection_confidence: float = Form(0.45),
    contact_distance_px: int = Form(45)
):
    if frame_stride <= 0:
        raise HTTPException(400, "frame_stride must be > 0")
    if max_frames <= 0:
        raise HTTPException(400, "max_frames must be > 0")
    if contact_distance_px <= 0:
        raise HTTPException(400, "contact_distance_px must be > 0")

    tmp_path = _save_upload_to_temp(file)
    try:
        duration = _ensure_video_duration(tmp_path)
        results = depth_pose_service_analyze(
            tmp_path,
            frame_stride=frame_stride,
            max_frames=max_frames,
            detection_confidence=detection_confidence,
            contact_distance_px=contact_distance_px,
            detection_fn=_run_inference,
            depth_model_name=DEPTHNET_MODEL,
            pose_model_name=POSENET_MODEL,
            cuda_from_bgr=bgr_to_cuda
        )
        return {
            "success": True,
            "video_duration_s": duration,
            **results
        }
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.post("/analyze/football/video")
async def analyze_football_video(
    file: UploadFile = File(...),
    frame_stride: int = Form(4),
    max_frames: int = Form(180),
    detection_confidence: float = Form(0.45),
    contact_distance_px: int = Form(45),
    possession_distance_px: int = Form(90),
    action_frame_stride: int = Form(8),
    action_top_k: int = Form(3),
    face_score_threshold: float = Form(0.6),
    face_match_threshold: float = Form(0.6)
):
    if frame_stride <= 0 or max_frames <= 0:
        raise HTTPException(400, "frame_stride and max_frames must be > 0")
    if not (0.0 < detection_confidence <= 1.0):
        raise HTTPException(400, "detection_confidence must be between 0 and 1")
    if contact_distance_px <= 0 or possession_distance_px <= 0:
        raise HTTPException(400, "contact_distance_px and possession_distance_px must be > 0")
    if action_frame_stride <= 0 or action_top_k <= 0:
        raise HTTPException(400, "action_frame_stride and action_top_k must be > 0")
    if not (0.0 < face_score_threshold <= 1.0):
        raise HTTPException(400, "face_score_threshold must be between 0 and 1")
    if not (0.0 < face_match_threshold <= 1.0):
        raise HTTPException(400, "face_match_threshold must be between 0 and 1")

    tmp_path = _save_upload_to_temp(file)
    try:
        duration = _ensure_video_duration(tmp_path)
        metadata = _get_video_metadata(tmp_path)
        frame_count = int(metadata["frame_count"])

        detection_summary = _analyze_soccer_detections(
            tmp_path,
            frame_stride=frame_stride,
            max_frames=max_frames,
            confidence=detection_confidence,
            possession_distance_px=possession_distance_px,
            contact_threshold_px=contact_distance_px
        )

        depth_pose = depth_pose_service_analyze(
            tmp_path,
            frame_stride=frame_stride,
            max_frames=max_frames,
            detection_confidence=detection_confidence,
            contact_distance_px=contact_distance_px,
            detection_fn=_run_inference,
            depth_model_name=DEPTHNET_MODEL,
            pose_model_name=POSENET_MODEL,
            cuda_from_bgr=bgr_to_cuda
        )

        if JETSON_INFERENCE_AVAILABLE:
            action_analysis = _run_actionnet_on_video(tmp_path, action_frame_stride, action_top_k)
        else:
            action_analysis = {
                "frames_analyzed": 0,
                "predictions": [],
                "top_labels": [],
                "warning": "jetson-inference no está disponible en este dispositivo"
            }

        face_checks = _evaluate_face_consistency(
            tmp_path,
            frame_count,
            score_threshold=face_score_threshold,
            match_threshold=face_match_threshold
        )

        summary = {
            "player_presence_ratio": detection_summary["player_presence_ratio"],
            "ball_presence_ratio": detection_summary["ball_presence_ratio"],
            "possession_ratio": detection_summary["possession_ratio"],
            "person_depth_trend": depth_pose["person_depth_trend"],
            "ball_depth_trend": depth_pose["ball_depth_trend"],
            "face_consistent": face_checks["consistent"],
            "dominant_actions": action_analysis.get("top_labels", []),
            "juggling_hits": detection_summary.get("juggling_hits", 0),
            "hand_contact_count": len(detection_summary.get("hand_contact_frames", []))
        }

        analysis = {
            "summary": summary,
            "face_checks": face_checks,
            "detection_frames_analyzed": detection_summary["frames_analyzed"],
            "detection_timeline": detection_summary["timeline"],
            "juggling_events": detection_summary.get("juggling_events", []),
            "hand_contact_events": detection_summary.get("hand_contact_events", []),
            "hand_contact_frames": detection_summary.get("hand_contact_frames", []),
            "depth": {
                "frames_analyzed": depth_pose["frames_analyzed"],
                "person_series": depth_pose["person_depth_series"],
                "ball_series": depth_pose["ball_depth_series"],
                "contact_events": depth_pose["contact_events"],
            },
            "action_analysis": action_analysis,
        }

        return {
            "success": True,
            "video_duration_s": duration,
            "frames_total": frame_count,
            "analysis": analysis
        }
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.post("/analyze/football/activity/video")
async def analyze_football_activity_video(
    file: UploadFile = File(...),
    frame_stride: int = Form(1),
    max_frames: int = Form(1600),
    detection_confidence: float = Form(0.35),
    contact_distance_px: int = Form(15),
    possession_distance_px: int = Form(50),
    action_frame_stride: int = Form(8),
    action_top_k: int = Form(1),
    face_score_threshold: float = Form(0.2),
    face_match_threshold: float = Form(0.2)
):
    if frame_stride <= 0 or max_frames <= 0:
        raise HTTPException(400, "frame_stride y max_frames deben ser > 0")
    if not (0.0 < detection_confidence <= 1.0):
        raise HTTPException(400, "detection_confidence debe estar entre 0 y 1")
    if contact_distance_px <= 0 or possession_distance_px <= 0:
        raise HTTPException(400, "contact_distance_px y possession_distance_px deben ser > 0")
    if action_frame_stride <= 0 or action_top_k <= 0:
        raise HTTPException(400, "action_frame_stride y action_top_k deben ser > 0")
    if not (0.0 < face_score_threshold <= 1.0):
        raise HTTPException(400, "face_score_threshold debe estar entre 0 y 1")
    if not (0.0 < face_match_threshold <= 1.0):
        raise HTTPException(400, "face_match_threshold debe estar entre 0 y 1")

    tmp_path = _save_upload_to_temp(file)
    try:
        duration = _ensure_video_duration(tmp_path)
        metadata = _get_video_metadata(tmp_path)
        frame_count = int(metadata["frame_count"])
        fps = max(float(metadata["fps"]), 1e-3)

        detection_summary = _analyze_soccer_detections(
            tmp_path,
            frame_stride=frame_stride,
            max_frames=max_frames,
            confidence=detection_confidence,
            possession_distance_px=possession_distance_px,
            contact_threshold_px=contact_distance_px
        )

        if JETSON_INFERENCE_AVAILABLE:
            action_analysis = _run_actionnet_on_video(tmp_path, action_frame_stride, action_top_k)
        else:
            action_analysis = {
                "frames_analyzed": 0,
                "predictions": [],
                "top_labels": [],
                "warning": "jetson-inference no está disponible en este dispositivo"
            }

        action_sequences = _derive_action_sequences(
            action_analysis.get("predictions", []),
            action_frame_stride,
            fps
        )

        face_checks = _evaluate_face_consistency(
            tmp_path,
            frame_count,
            score_threshold=face_score_threshold,
            match_threshold=face_match_threshold
        )

        motion_metrics = _compute_player_motion_metrics(detection_summary["timeline"], fps)
        orientation_summary = _summarize_orientation(detection_summary["timeline"])

        activity_report = _build_activity_report(
            metadata,
            detection_summary,
            action_analysis,
            action_sequences,
            motion_metrics,
            orientation_summary,
            face_checks
        )

        detection_payload = {
            "frames_analyzed": detection_summary["frames_analyzed"],
            "player_presence_ratio": detection_summary["player_presence_ratio"],
            "ball_presence_ratio": detection_summary["ball_presence_ratio"],
            "possession_ratio": detection_summary["possession_ratio"],
            "juggling_hits": detection_summary["juggling_hits"],
            "ball_detection_sources": detection_summary.get("ball_detection_sources"),
            "ball_detection_counts": detection_summary.get("ball_detection_counts"),
            "timeline": detection_summary["timeline"],
            "juggling_events": detection_summary.get("juggling_events", []),
            "hand_contact_events": detection_summary.get("hand_contact_events", []),
            "hand_contact_frames": detection_summary.get("hand_contact_frames", [])
        }

        return {
            "success": True,
            "video_duration_s": duration,
            "frames_total": frame_count,
            "activity_report": activity_report,
            "detection_summary": detection_payload,
            "action_analysis": action_analysis,
            "action_sequences": action_sequences,
            "motion_metrics": motion_metrics,
            "orientation_summary": orientation_summary,
            "face_checks": face_checks
        }
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.post("/analyze/gym/video")
async def analyze_gym_video(
    file: UploadFile = File(...),
    frame_stride: int = Form(4),
    max_frames: int = Form(180),
    detection_confidence: float = Form(0.45),
    interaction_distance_px: int = Form(110),
    contact_distance_px: int = Form(40),
    action_frame_stride: int = Form(6),
    action_top_k: int = Form(4),
    face_score_threshold: float = Form(0.6),
    face_match_threshold: float = Form(0.6)
):
    if frame_stride <= 0 or max_frames <= 0:
        raise HTTPException(400, "frame_stride and max_frames must be > 0")
    if not (0.0 < detection_confidence <= 1.0):
        raise HTTPException(400, "detection_confidence must be between 0 and 1")
    if interaction_distance_px <= 0 or contact_distance_px <= 0:
        raise HTTPException(400, "interaction_distance_px and contact_distance_px must be > 0")
    if action_frame_stride <= 0 or action_top_k <= 0:
        raise HTTPException(400, "action_frame_stride and action_top_k must be > 0")
    if not (0.0 < face_score_threshold <= 1.0):
        raise HTTPException(400, "face_score_threshold must be between 0 and 1")
    if not (0.0 < face_match_threshold <= 1.0):
        raise HTTPException(400, "face_match_threshold must be between 0 and 1")

    tmp_path = _save_upload_to_temp(file)
    try:
        duration = _ensure_video_duration(tmp_path)
        metadata = _get_video_metadata(tmp_path)
        frame_count = int(metadata["frame_count"])
        fps = max(metadata["fps"], 1e-3)

        detection_summary = _analyze_gym_detections(
            tmp_path,
            frame_stride=frame_stride,
            max_frames=max_frames,
            confidence=detection_confidence,
            interaction_distance_px=interaction_distance_px
        )

        depth_pose = depth_pose_service_analyze(
            tmp_path,
            frame_stride=frame_stride,
            max_frames=max_frames,
            detection_confidence=detection_confidence,
            contact_distance_px=contact_distance_px,
            detection_fn=_run_inference,
            depth_model_name=DEPTHNET_MODEL,
            pose_model_name=POSENET_MODEL,
            cuda_from_bgr=bgr_to_cuda
        )

        if JETSON_INFERENCE_AVAILABLE:
            action_analysis = _run_actionnet_on_video(tmp_path, action_frame_stride, action_top_k)
        else:
            action_analysis = {
                "frames_analyzed": 0,
                "predictions": [],
                "top_labels": [],
                "warning": "jetson-inference no está disponible en este dispositivo"
            }

        action_sequences = _derive_action_sequences(
            action_analysis.get("predictions", []),
            action_frame_stride,
            fps
        )

        face_checks = _evaluate_face_consistency(
            tmp_path,
            frame_count,
            score_threshold=face_score_threshold,
            match_threshold=face_match_threshold
        )

        summary = {
            "player_presence_ratio": detection_summary["player_presence_ratio"],
            "equipment_presence_ratio": detection_summary["equipment_presence_ratio"],
            "interaction_ratio": detection_summary["interaction_ratio"],
            "avg_vertical_variation": detection_summary["avg_vertical_variation"],
            "person_depth_trend": depth_pose["person_depth_trend"],
            "face_consistent": face_checks["consistent"],
            "dominant_actions": action_sequences["label_totals"][:action_top_k]
        }

        analysis = {
            "summary": summary,
            "face_checks": face_checks,
            "detection": {
                "frames_analyzed": detection_summary["frames_analyzed"],
                "timeline": detection_summary["timeline"],
                "equipment_summary": detection_summary["equipment_summary"]
            },
            "depth": {
                "frames_analyzed": depth_pose["frames_analyzed"],
                "person_series": depth_pose["person_depth_series"],
                "ball_series": depth_pose["ball_depth_series"],
                "contact_events": depth_pose["contact_events"],
            },
            "action_analysis": action_analysis,
            "action_sequences": action_sequences
        }

        return {
            "success": True,
            "video_duration_s": duration,
            "frames_total": frame_count,
            "analysis": analysis
        }
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.post("/actionnet/video")
async def actionnet_video(
    file: UploadFile = File(...),
    frame_stride: int = Form(8),
    top_k: int = Form(3),
):
    if frame_stride <= 0:
        raise HTTPException(400, "frame_stride must be > 0")
    if top_k <= 0:
        raise HTTPException(400, "top_k must be > 0")
    if not JETSON_INFERENCE_AVAILABLE:
        raise HTTPException(503, "jetson-inference is required for ActionNet endpoints")

    tmp_path = _save_upload_to_temp(file)
    try:
        duration = _ensure_video_duration(tmp_path)
        results = _run_actionnet_on_video(tmp_path, frame_stride, top_k)
        return {
            "success": True,
            "video_duration_s": duration,
            **results
        }
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.post("/actionnet/image")
def actionnet_image(req: ActionImageRequest):
    if req.top_k <= 0:
        raise HTTPException(400, "top_k must be > 0")
    if not JETSON_INFERENCE_AVAILABLE:
        raise HTTPException(503, "jetson-inference is required for ActionNet endpoints")

    img = _decode_base64_image(req.image_base64)
    result = _run_actionnet_on_image(img, req.top_k)
    return {
        "success": True,
        **result
    }


@app.post("/depthnet/video")
async def depthnet_video(
    file: UploadFile = File(...),
    frame_stride: int = Form(2),
    max_frames: int = Form(1800),
):
    if frame_stride <= 0:
        raise HTTPException(400, "frame_stride must be > 0")
    if max_frames <= 0:
        raise HTTPException(400, "max_frames must be > 0")
    if not JETSON_INFERENCE_AVAILABLE:
        raise HTTPException(503, "jetson-inference is required for DepthNet endpoints")

    tmp_path = _save_upload_to_temp(file)
    try:
        duration = _ensure_video_duration(tmp_path)
        results = run_depthnet_video(
            tmp_path,
            frame_stride=frame_stride,
            max_frames=max_frames,
            preview_frames=3,
            depth_model_name=DEPTHNET_MODEL,
            cuda_from_bgr=bgr_to_cuda
        )
        return {
            "success": True,
            "video_duration_s": duration,
            **results
        }
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.post("/superres/image")
async def superres_image(
    file: UploadFile = File(...),
    model: Optional[str] = Form(None)
):
    content = await file.read()
    data = np.frombuffer(content, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "No se pudo decodificar la imagen subida")

    sr, scale = superres_service.load_engine(_resolve_superres_model_path(model))
    try:
        upscaled = sr.upsample(img)
    except Exception as exc:
        raise HTTPException(500, f"Error aplicando super resolución: {exc}")

    _, buffer = cv2.imencode('.jpg', upscaled, [cv2.IMWRITE_JPEG_QUALITY, 90])
    base64_img = base64.b64encode(buffer).decode()
    return {
        "success": True,
        "scale": scale,
        "original_size": {"width": int(img.shape[1]), "height": int(img.shape[0])},
        "upscaled_size": {"width": int(upscaled.shape[1]), "height": int(upscaled.shape[0])},
        "image_base64": "data:image/jpeg;base64," + base64_img
    }


@app.post("/superres/video")
async def superres_video(
    file: UploadFile = File(...),
    frame_stride: int = Form(1),
    model: Optional[str] = Form(None)
):
    if frame_stride <= 0:
        raise HTTPException(400, "frame_stride debe ser > 0")

    tmp_path = _save_upload_to_temp(file)
    output_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    output_tmp.close()

    sr, scale = superres_service.load_engine(_resolve_superres_model_path(model))
    cap = cv2.VideoCapture(tmp_path)
    if not cap.isOpened():
        os.remove(tmp_path)
        raise HTTPException(400, "No se pudo abrir el video subido")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    if width <= 0 or height <= 0:
        cap.release()
        os.remove(tmp_path)
        raise HTTPException(400, "Dimensiones de video inválidas")

    out_size = (int(width * scale), int(height * scale))
    writer = cv2.VideoWriter(
        output_tmp.name,
        cv2.VideoWriter_fourcc(*'mp4v'),
        fps / frame_stride if frame_stride > 1 else fps,
        out_size
    )

    frame_idx = 0
    processed = 0
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % frame_stride != 0:
                frame_idx += 1
                continue

            upscaled = sr.upsample(frame)
            writer.write(upscaled)
            processed += 1
            frame_idx += 1
    finally:
        cap.release()
        writer.release()
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    with open(output_tmp.name, "rb") as f:
        video_b64 = base64.b64encode(f.read()).decode()
    os.remove(output_tmp.name)

    return {
        "success": True,
        "scale": scale,
        "frames_written": processed,
        "upscaled_resolution": {"width": out_size[0], "height": out_size[1]},
        "video_base64": "data:video/mp4;base64," + video_b64
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5050)
