"""
Inference-only API for Edge Devices (Jetson Nano)
UPDATED: Uses YOLOv4-Tiny (Reliable & DNN Compatible)
"""

import os
import time
import base64
import numpy as np
import cv2
import tempfile
from typing import Optional, List, Dict, Any

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
)
from .services.face_service import FaceEmbeddingService
from .services.activity_analysis import ActivityAnalyzer, SOCCER_BALL_LABELS, GYM_EQUIPMENT_LABELS
from .services.actionnet_service import ActionNetService, JETSON_INFERENCE_AVAILABLE as ACTIONNET_AVAILABLE
from .services.hit_detection_service import HitDetectionService
from .services.superres_service import SuperResolutionService

JETSON_INFERENCE_AVAILABLE = ACTIONNET_AVAILABLE

# --- Configuration ---
# CAMBIO: Usamos yolov4-tiny por defecto porque es 100% compatible con OpenCV DNN
DETECTION_MODEL = os.environ.get('DETECTION_MODEL', 'yolov4-tiny')
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
_default_superres_dirs = [
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

activity_analyzer = ActivityAnalyzer(
    yolo_fallback=yolo_fallback,
    enable_ball_fallback=BALL_YOLO_FALLBACK,
    fallback_confidence=BALL_YOLO_CONFIDENCE,
    fallback_nms=BALL_YOLO_NMS,
    soccer_labels=SOCCER_BALL_LABELS,
    gym_labels=GYM_EQUIPMENT_LABELS,
)

actionnet_service = ActionNetService(ACTIONNET_MODEL, ACTIONNET_LABELS)

hit_detection_service = HitDetectionService([
    os.path.join(BASE_DIR, "../models/hit_detect.onnx"),
    os.path.join(BASE_DIR, "../hit_detect.onnx"),
    os.path.join(BASE_DIR, "hit_detect.onnx"),
    os.path.join(MODELS_DIR, "hit_detect.onnx"),
])

superres_service = SuperResolutionService(SUPERRES_MODEL_DIR, SUPERRES_MODEL_PATH)

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


def _run_inference(img: np.ndarray, confidence: float, nms_threshold: float) -> dict:
    """Wrapper around detectNet inference service with optional YOLO fallback for the ball."""
    return activity_analyzer.run_inference(img, confidence, nms_threshold)


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
    hit_threshold: float
):
    return hit_detection_service.run_on_video(
        video_path=video_path,
        frame_stride=frame_stride,
        max_frames=max_frames,
        hit_threshold=hit_threshold
    )


def _detect_faces_with_embeddings(image: np.ndarray, score_threshold: float = 0.6) -> List[Dict[str, Any]]:
    return face_service.detect_with_embeddings(image, score_threshold)


def _get_primary_face_embedding(image: np.ndarray, min_score: float = 0.6) -> Optional[Dict[str, Any]]:
    return face_service.get_primary_face_embedding(image, min_score)




@app.post("/detect")
def detect(req: DetectionRequest):
    img = _decode_base64_image(req.image_base64)
    return _run_inference(img, req.confidence, req.nms_threshold)


@app.post("/detect/batch")
def detect_batch(req: BatchDetectionRequest):
    """Analyze multiple images in a single request."""
    if not req.images_base64:
        raise HTTPException(400, "images_base64 list cannot be empty")

    batch_results = []
    for idx, image_base64 in enumerate(req.images_base64):
        try:
            img = _decode_base64_image(image_base64)
            result = _run_inference(img, req.confidence, req.nms_threshold)
            batch_results.append({"index": idx, **result})
        except HTTPException as exc:
            batch_results.append({"index": idx, "success": False, "error": exc.detail})

    return {"success": True, "frames": len(batch_results), "results": batch_results}


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
        return {
            "success": True,
            "frames_analyzed": processed,
            "frame_stride": frame_stride,
            "results": results,
        }
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.post("/face/detect")
def face_detect(req: FaceDetectionRequest):
    img = _decode_base64_image(req.image_base64)
    faces = _detect_faces_with_embeddings(img, req.score_threshold)
    return {
        "success": True,
        "count": len(faces),
        "faces": faces
    }


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


@app.post("/detect/hit/video")
async def detect_hit_video(
    file: UploadFile = File(...),
    frame_stride: int = Form(None),
    max_frames: int = Form(None),
    hit_threshold: float = Form(None)
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

        results = _run_hit_detection_on_video(tmp_path, frame_stride, max_frames, hit_threshold)
        return {
            "success": True,
            "video_duration_s": duration,
            **results
        }
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


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
async def superres_image(file: UploadFile = File(...)):
    content = await file.read()
    data = np.frombuffer(content, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "No se pudo decodificar la imagen subida")

    sr, scale = superres_service.load_engine()
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
    frame_stride: int = Form(1)
):
    if frame_stride <= 0:
        raise HTTPException(400, "frame_stride debe ser > 0")

    tmp_path = _save_upload_to_temp(file)
    output_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    output_tmp.close()

    sr, scale = superres_service.load_engine()
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
