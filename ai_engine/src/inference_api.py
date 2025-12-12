"""
Inference-only API for Edge Devices (Jetson Nano)
UPDATED: Uses YOLOv4-Tiny (Reliable & DNN Compatible)
"""

import os
import time
import math
import base64
import tempfile
import numpy as np
import cv2
import requests
from collections import defaultdict
from typing import Optional, List, Dict, Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

try:
    from cv2.dnn_superres import DnnSuperResImpl_create
except ImportError:
    DnnSuperResImpl_create = None

from .services.jetson_env import JETSON_MODELS_MANIFEST
from .services.video_utils import bgr_to_cuda
from .services.depth_pose import run_depthnet_video, analyze_depth_pose_video as depth_pose_service_analyze

try:
    import jetson.inference
    import jetson.utils
    JETSON_INFERENCE_AVAILABLE = True
except ImportError:
    JETSON_INFERENCE_AVAILABLE = False

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
SUPERRES_MODEL_DIR = os.environ.get('SUPERRES_MODEL_DIR', '/usr/local/bin/networks/Super-Resolution-BSD500')

# Global model instance
net = None
output_layers = None
classes = []
model_name = None
actionnet = None
hit_detection_net = None
face_detector = None
face_recognizer = None
face_recognizer_backend = None
superres_engine = None
superres_scale = 2
superres_model_path = None
face_detector_backend = None

HIT_DETECT_MODEL_OVERRIDE = os.environ.get('HIT_DETECT_MODEL_PATH')


def _resolve_hit_model_path():
    base_dir = os.path.dirname(__file__)
    candidates = [
        HIT_DETECT_MODEL_OVERRIDE,
        os.path.join(base_dir, "../models/hit_detect.onnx"),
        os.path.join(base_dir, "../hit_detect.onnx"),
        os.path.join(base_dir, "hit_detect.onnx"),
        os.path.join(MODELS_DIR, "hit_detect.onnx"),
    ]
    for candidate in candidates:
        if candidate:
            resolved = os.path.abspath(candidate)
            if os.path.exists(resolved):
                return resolved
    return os.path.abspath(os.path.join(base_dir, "../models/hit_detect.onnx"))


HIT_DETECTION_MODEL_PATH = _resolve_hit_model_path()

SOCCER_BALL_LABELS = {"sports_ball", "ball", "frisbee"}
GYM_EQUIPMENT_LABELS = {
    "barbell", "dumbbell", "bench", "kettlebell", "backpack", "suitcase",
    "handbag", "bottle", "chair", "cup"
}


def _resolve_superres_model_path():
    """Locate super-resolution weights, preferring TensorFlow (.pb) exports."""

    def _append_unique(seq: List[str], path: Optional[str]):
        if path and path not in seq:
            seq.append(path)

    candidates: List[str] = []
    _append_unique(candidates, SUPERRES_MODEL_PATH)

    preferred = [
        os.path.join(SUPERRES_MODEL_DIR, 'superres.pb'),
        os.path.join(SUPERRES_MODEL_DIR, 'super_resolution_bsd500.pb'),
        os.path.join(SUPERRES_MODEL_DIR, 'super_resolution.pb'),
        os.path.join(MODELS_DIR, 'superres.pb'),
        os.path.join(MODELS_DIR, 'super_resolution_bsd500.pb'),
        os.path.join(MODELS_DIR, 'super_resolution.pb'),
    ]
    fallbacks = [
        os.path.join(SUPERRES_MODEL_DIR, 'super_resolution.onnx'),
        os.path.join(SUPERRES_MODEL_DIR, 'model.onnx'),
        os.path.join(SUPERRES_MODEL_DIR, 'superres.onnx'),
        os.path.join(MODELS_DIR, 'super_resolution.onnx'),
        os.path.join(MODELS_DIR, 'superres.onnx'),
    ]

    for path in preferred + fallbacks:
        _append_unique(candidates, path)

    if SUPERRES_MODEL_DIR and os.path.isdir(SUPERRES_MODEL_DIR):
        dir_files = sorted(os.listdir(SUPERRES_MODEL_DIR))
        for ext in ('.pb', '.onnx'):
            for filename in dir_files:
                if filename.lower().endswith(ext):
                    _append_unique(candidates, os.path.join(SUPERRES_MODEL_DIR, filename))

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None

# --- Reliable Model URLs (AlexeyAB Darknet) ---
MODEL_URLS = {
    "yolov4-tiny.cfg": "https://raw.githubusercontent.com/AlexeyAB/darknet/master/cfg/yolov4-tiny.cfg",
    "yolov4-tiny.weights": "https://github.com/AlexeyAB/darknet/releases/download/darknet_yolo_v4_pre/yolov4-tiny.weights",
    "coco.names": "https://raw.githubusercontent.com/AlexeyAB/darknet/master/data/coco.names"
}

def download_file(url: str, dest: str):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        print(f"✅ Found {os.path.basename(dest)}")
        return
    print(f"⬇️ Downloading {os.path.basename(dest)}...")
    try:
        r = requests.get(url, stream=True, timeout=30)
        r.raise_for_status()
        with open(dest, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"✅ Download complete: {dest}")
    except Exception as e:
        print(f"❌ Download failed: {e}")

def load_yolo_model():
    """Load YOLOv4-Tiny using OpenCV DNN"""
    global net, output_layers, classes, model_name
    
    # 1. Download required files
    cfg_path = os.path.join(MODELS_DIR, "yolov4-tiny.cfg")
    weights_path = os.path.join(MODELS_DIR, "yolov4-tiny.weights")
    names_path = os.path.join(MODELS_DIR, "coco.names")
    
    download_file(MODEL_URLS["yolov4-tiny.cfg"], cfg_path)
    download_file(MODEL_URLS["yolov4-tiny.weights"], weights_path)
    download_file(MODEL_URLS["coco.names"], names_path)
    
    # 2. Load Classes
    if os.path.exists(names_path):
        with open(names_path, "r") as f:
            classes = [line.strip() for line in f.readlines()]
    else:
        classes = ["object"]

    # 3. Load Network
    print(f"⏳ Loading YOLOv4-Tiny...")
    try:
        net = cv2.dnn.readNet(weights_path, cfg_path)
        
        # Enable CUDA if available (Jetson Magic)
        net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
        net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
        print("✅ CUDA Backend Enabled")
        
        layer_names = net.getLayerNames()
        output_layers = [layer_names[i[0] - 1] for i in net.getUnconnectedOutLayers()]
        model_name = "yolov4-tiny"
        return True
    except Exception as e:
        print(f"❌ Failed to load YOLO: {e}")
        # Fallback to CPU if CUDA fails
        try:
            print("⚠️ Retrying on CPU...")
            net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
            model_name = "yolov4-tiny-cpu"
            return True
        except Exception as e2:
             print(f"❌ CPU Fallback failed: {e2}")
             return False

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
    load_yolo_model()

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
    return {"status": "ok", "model": model_name, "cuda": cv2.cuda.getCudaEnabledDeviceCount() > 0}


def _load_actionnet():
    global actionnet
    if actionnet is None:
        if not JETSON_INFERENCE_AVAILABLE:
            raise HTTPException(503, "jetson-inference is not available on this device")
        try:
            if ACTIONNET_LABELS:
                actionnet = jetson.inference.actionNet(ACTIONNET_MODEL, ACTIONNET_LABELS)
            else:
                actionnet = jetson.inference.actionNet(ACTIONNET_MODEL)
        except Exception as exc:
            manifest_hint = JETSON_MODELS_MANIFEST or "networks/models.json"
            raise HTTPException(
                503,
                f"jetson-inference actionNet failed to load '{ACTIONNET_MODEL}'. "
                f"Verifica que exista {manifest_hint} y los pesos requeridos. Detalle: {exc}"
            )
    return actionnet


def _load_face_detector():
    global face_detector, face_detector_backend
    if face_detector is None:
        if JETSON_INFERENCE_AVAILABLE:
            try:
                face_detector = jetson.inference.detectNet(JETSON_FACE_NETWORK, threshold=JETSON_FACE_THRESHOLD)
                face_detector_backend = "jetson_detectnet"
                return face_detector, face_detector_backend
            except Exception:
                face_detector = None

        if hasattr(cv2, "FaceDetectorYN") and hasattr(cv2.FaceDetectorYN, "create"):
            model_path = FACE_DETECT_MODEL_PATH
            if not os.path.exists(model_path):
                raise HTTPException(503, f"No se encontró el modelo de detección facial en {model_path}")
            try:
                face_detector = cv2.FaceDetectorYN.create(model_path, "", (320, 320))
                face_detector_backend = "yunet"
            except Exception as exc:
                raise HTTPException(503, f"cv2.FaceDetectorYN no pudo cargar '{model_path}': {exc}")
        else:
            cascade_path = getattr(cv2.data, "haarcascades", "") + "haarcascade_frontalface_default.xml"
            if not cascade_path or not os.path.exists(cascade_path):
                raise HTTPException(503, "OpenCV no tiene FaceDetectorYN y no se encontró haarcascade_frontalface_default.xml para el fallback.")
            detector = cv2.CascadeClassifier(cascade_path)
            if detector.empty():
                raise HTTPException(503, "No se pudo inicializar el clasificador Haar para detección facial.")
            face_detector = detector
            face_detector_backend = "cascade"
    return face_detector, face_detector_backend


def _load_face_recognizer():
    global face_recognizer, face_recognizer_backend
    if face_recognizer is None:
        model_path = FACE_RECOGNITION_MODEL_PATH
        if not os.path.exists(model_path):
            raise HTTPException(503, f"No se encontró el modelo de reconocimiento facial en {model_path}")
        if hasattr(cv2, "FaceRecognizerSF") and hasattr(cv2.FaceRecognizerSF, "create"):
            try:
                face_recognizer = cv2.FaceRecognizerSF.create(model_path, "")
                face_recognizer_backend = "opencv_sface"
            except Exception:
                face_recognizer = None
        if face_recognizer is None:
            try:
                face_recognizer = _OnnxSFaceRecognizer(model_path)
                face_recognizer_backend = "onnx_sface"
            except Exception as exc:
                raise HTTPException(503, f"No se pudo inicializar el modelo de reconocimiento facial: {exc}")
    return face_recognizer, face_recognizer_backend


def _infer_superres_config(model_path: str):
    fname = os.path.basename(model_path).lower()
    algo = 'edsr'
    for candidate in ('edsr', 'espcn', 'fsrcnn', 'lapsrn'):
        if candidate in fname:
            algo = candidate
            break
    scale = 4
    for candidate in (8, 4, 3, 2):
        token = f"x{candidate}"
        if token in fname or f"{candidate}x" in fname or f"_x{candidate}" in fname:
            scale = candidate
            break
    return algo, scale


def _load_superres_engine():
    global superres_engine, superres_scale, superres_model_path
    if superres_engine is not None:
        return superres_engine, superres_scale
    if DnnSuperResImpl_create is None:
        raise HTTPException(503, "cv2.dnn_superres no está disponible en este entorno (compila OpenCV con contrib).")
    model_path = _resolve_superres_model_path()
    if not model_path or not os.path.exists(model_path):
        raise HTTPException(503, "No se encontró el modelo de super resolución. Configura SUPERRES_MODEL_PATH o verifica data/networks/Super-Resolution-BSD500.")
    _, ext = os.path.splitext(model_path)
    if ext.lower() == '.onnx':
        raise HTTPException(
            503,
            f"El modelo seleccionado ({model_path}) es ONNX y cv2.dnn_superres solo soporta pesos TensorFlow (.pb). "
            "Descarga/convierte la versión .pb o apunta SUPERRES_MODEL_PATH a un archivo .pb válido."
        )
    try:
        sr = DnnSuperResImpl_create()
        sr.readModel(model_path)
        algo, scale = _infer_superres_config(model_path)
        sr.setModel(algo, scale)
        superres_engine = sr
        superres_scale = scale
        superres_model_path = model_path
        print(f"✅ Super Resolution model loaded ({algo}, x{scale}): {model_path}")
        return superres_engine, superres_scale
    except Exception as exc:
        raise HTTPException(503, f"No se pudo cargar el modelo de super resolución en {model_path}: {exc}")


def _decode_base64_image(image_base64: str) -> np.ndarray:
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


def _align_face_crop(image: np.ndarray, bbox: List[int], landmarks: Optional[List[float]]) -> np.ndarray:
    x1, y1, x2, y2 = bbox
    x1 = max(0, int(x1))
    y1 = max(0, int(y1))
    x2 = min(image.shape[1], int(x2))
    y2 = min(image.shape[0], int(y2))
    if x2 <= x1 or y2 <= y1:
        return cv2.resize(image, SFACE_INPUT_SIZE)
    if landmarks and len(landmarks) >= 10:
        src = np.array(landmarks[:10], dtype=np.float32).reshape(5, 2)
        try:
            M, _ = cv2.estimateAffinePartial2D(src, SFACE_TEMPLATE, method=cv2.LMEDS)
        except Exception:
            M = None
        if M is not None:
            return cv2.warpAffine(image, M, SFACE_INPUT_SIZE)
    face = image[y1:y2, x1:x2]
    if face.size == 0:
        return cv2.resize(image, SFACE_INPUT_SIZE)
    return cv2.resize(face, SFACE_INPUT_SIZE)


class _OnnxSFaceRecognizer:
    def __init__(self, model_path: str):
        self.net = cv2.dnn.readNetFromONNX(model_path)

    def extract(self, image: np.ndarray, bbox: List[int], landmarks: Optional[List[float]]) -> List[float]:
        aligned = _align_face_crop(image, bbox, landmarks)
        blob = cv2.dnn.blobFromImage(
            aligned,
            scalefactor=1 / 255.0,
            size=SFACE_INPUT_SIZE,
            mean=(0, 0, 0),
            swapRB=True,
            crop=False
        )
        self.net.setInput(blob)
        embedding = self.net.forward().flatten()
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        return embedding.astype(np.float32).tolist()


def _save_upload_to_temp(file: UploadFile) -> str:
    try:
        file.file.seek(0)
        contents = file.file.read()
    except Exception:
        raise HTTPException(400, "Failed to read uploaded file")

    if not contents:
        raise HTTPException(400, "Uploaded file is empty")

    suffix = os.path.splitext(file.filename or "")[1]
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(contents)
    tmp.close()
    return tmp.name


def _ensure_video_duration(path: str, max_seconds: int = MAX_VIDEO_DURATION_S):
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


def _get_video_metadata(path: str) -> Dict[str, float]:
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


def _run_inference(img: np.ndarray, confidence: float, nms_threshold: float) -> dict:
    """Run YOLO inference on a decoded frame."""
    global net
    if net is None:
        raise HTTPException(503, "Model not loaded")

    height, width = img.shape[:2]
    start = time.perf_counter()
    blob = cv2.dnn.blobFromImage(img, 1 / 255.0, (416, 416), (0, 0, 0), swapRB=True, crop=False)
    net.setInput(blob)
    outs = net.forward(output_layers)

    class_ids = []
    confidences = []
    boxes = []

    for out in outs:
        for detection in out:
            scores = detection[5:]
            class_id = np.argmax(scores)
            conf = scores[class_id]
            if conf > confidence:
                cx = int(detection[0] * width)
                cy = int(detection[1] * height)
                w = int(detection[2] * width)
                h = int(detection[3] * height)
                x = int(cx - w / 2)
                y = int(cy - h / 2)
                boxes.append([x, y, w, h])
                confidences.append(float(conf))
                class_ids.append(class_id)

    indices = cv2.dnn.NMSBoxes(boxes, confidences, confidence, nms_threshold)
    detections = []
    if len(indices) > 0:
        for i in indices.flatten():
            x, y, w, h = boxes[i]
            detections.append(
                {
                    "class_name": str(classes[class_ids[i]]),
                    "confidence": round(confidences[i], 2),
                    "bbox": [x, y, x + w, y + h],
                }
            )

    return {
        "success": True,
        "detections": detections,
        "time_ms": round((time.perf_counter() - start) * 1000, 2),
    }


def _select_best_detection(detections: List[Dict[str, Any]], label_set: set) -> Optional[Dict[str, Any]]:
    best = None
    for det in detections:
        if det.get("class_name", "").lower() in label_set:
            if best is None or det.get("confidence", 0) > best.get("confidence", 0):
                best = det
    return best


def _bbox_center(bbox: List[int]) -> tuple:
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def _center_distance(bbox_a: List[int], bbox_b: List[int]) -> float:
    ax, ay = _bbox_center(bbox_a)
    bx, by = _bbox_center(bbox_b)
    return math.hypot(ax - bx, ay - by)


def _analyze_soccer_detections(
    video_path: str,
    frame_stride: int,
    max_frames: int,
    confidence: float,
    possession_distance_px: int,
    nms_threshold: float = 0.4
) -> Dict[str, Any]:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise HTTPException(400, "Unable to open uploaded video")

    frame_idx = 0
    processed = 0
    timeline = []
    player_frames = 0
    ball_frames = 0
    possession_frames = 0

    while processed < max_frames:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % frame_stride != 0:
            frame_idx += 1
            continue

        inference = _run_inference(frame, confidence, nms_threshold)
        detections = inference.get("detections", [])
        player_det = _select_best_detection(detections, {"person"})
        ball_det = _select_best_detection(detections, SOCCER_BALL_LABELS)

        entry: Dict[str, Any] = {"frame": frame_idx}
        if player_det:
            entry["player"] = player_det
            player_frames += 1
        if ball_det:
            entry["ball"] = ball_det
            ball_frames += 1

        if player_det and ball_det:
            distance = _center_distance(player_det["bbox"], ball_det["bbox"])
            entry["player_ball_distance"] = round(distance, 2)
            if distance <= possession_distance_px:
                possession_frames += 1

        timeline.append(entry)
        processed += 1
        frame_idx += 1

    cap.release()
    total = len(timeline)

    def _ratio(count: int) -> float:
        return round((count / total) if total else 0.0, 4)

    return {
        "frames_analyzed": processed,
        "timeline": timeline,
        "player_presence_ratio": _ratio(player_frames),
        "ball_presence_ratio": _ratio(ball_frames),
        "possession_ratio": _ratio(possession_frames)
    }


def _analyze_gym_detections(
    video_path: str,
    frame_stride: int,
    max_frames: int,
    confidence: float,
    interaction_distance_px: int,
    nms_threshold: float = 0.4
) -> Dict[str, Any]:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise HTTPException(400, "Unable to open uploaded video")

    frame_idx = 0
    processed = 0
    timeline = []
    player_frames = 0
    equipment_frames = 0
    interaction_frames = 0
    prev_player_bbox = None
    vertical_variation_acc = 0.0
    vertical_variation_count = 0
    equipment_counts = defaultdict(int)

    while processed < max_frames:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % frame_stride != 0:
            frame_idx += 1
            continue

        inference = _run_inference(frame, confidence, nms_threshold)
        detections = inference.get("detections", [])
        player_det = _select_best_detection(detections, {"person"})
        equipment_det = _select_best_detection(detections, GYM_EQUIPMENT_LABELS)

        entry: Dict[str, Any] = {"frame": frame_idx}
        if player_det:
            entry["athlete"] = player_det
            player_frames += 1
            if prev_player_bbox:
                prev_height = prev_player_bbox[3] - prev_player_bbox[1]
                curr_height = player_det["bbox"][3] - player_det["bbox"][1]
                delta = abs(curr_height - prev_height)
                vertical_variation_acc += delta
                vertical_variation_count += 1
            prev_player_bbox = player_det["bbox"]
        else:
            prev_player_bbox = None

        if equipment_det:
            entry["equipment"] = equipment_det
            equipment_frames += 1
            label = equipment_det.get("class_name")
            if label:
                equipment_counts[label] += 1

        if player_det and equipment_det:
            distance = _center_distance(player_det["bbox"], equipment_det["bbox"])
            entry["athlete_equipment_distance"] = round(distance, 2)
            if distance <= interaction_distance_px:
                entry["interaction"] = True
                interaction_frames += 1
            else:
                entry["interaction"] = False

        timeline.append(entry)
        processed += 1
        frame_idx += 1

    cap.release()
    total = len(timeline)

    def _ratio(count: int) -> float:
        return round((count / total) if total else 0.0, 4)

    avg_variation = (
        round(vertical_variation_acc / vertical_variation_count, 2)
        if vertical_variation_count > 0 else 0.0
    )

    equipment_summary = [
        {"label": label, "ratio": _ratio(count)}
        for label, count in sorted(equipment_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    return {
        "frames_analyzed": processed,
        "timeline": timeline,
        "player_presence_ratio": _ratio(player_frames),
        "equipment_presence_ratio": _ratio(equipment_frames),
        "interaction_ratio": _ratio(interaction_frames),
        "avg_vertical_variation": avg_variation,
        "equipment_summary": equipment_summary
    }


def _read_frame_at(path: str, frame_index: int) -> Optional[np.ndarray]:
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return None
    frame_index = max(0, frame_index)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ret, frame = cap.read()
    cap.release()
    return frame if ret else None


def _match_face_embeddings(embedding_a: List[float], embedding_b: List[float]) -> float:
    recognizer, backend = _load_face_recognizer()
    vec_a = np.array(embedding_a, dtype=np.float32).reshape(1, -1)
    vec_b = np.array(embedding_b, dtype=np.float32).reshape(1, -1)
    if backend == "opencv_sface":
        return float(recognizer.match(vec_a, vec_b, cv2.FaceRecognizerSF_FR_COSINE))
    similarity = float(np.dot(vec_a.flatten(), vec_b.flatten()))
    return similarity


def _evaluate_face_consistency(
    video_path: str,
    frame_count: int,
    score_threshold: float,
    match_threshold: float
) -> Dict[str, Any]:
    if frame_count <= 0:
        return {
            "threshold": match_threshold,
            "samples": [],
            "pairwise": [],
            "consistent": False,
            "note": "El video no contiene frames válidos"
        }

    targets = [
        ("start", 0),
        ("middle", max(frame_count // 2, 0)),
        ("end", max(frame_count - 1, 0)),
    ]

    samples = []
    embeddings: Dict[str, List[float]] = {}

    for label, idx in targets:
        frame = _read_frame_at(video_path, idx)
        sample = {
            "position": label,
            "frame": int(idx),
            "success": False
        }
        if frame is None:
            sample["error"] = "frame_unavailable"
        else:
            face = _get_primary_face_embedding(frame, score_threshold)
            if face:
                sample["success"] = True
                sample["score"] = float(face["score"])
                sample["face_id"] = face["face_id"]
                embeddings[label] = face["embedding"]
            else:
                sample["error"] = "face_not_detected"
        samples.append(sample)

    pairwise = []
    positions_to_compare = [("start", "middle"), ("middle", "end"), ("start", "end")]
    for ref, other in positions_to_compare:
        if ref in embeddings and other in embeddings:
            similarity = _match_face_embeddings(embeddings[ref], embeddings[other])
            pairwise.append({
                "pair": f"{ref}-{other}",
                "similarity": similarity,
                "match": similarity >= match_threshold
            })

    consistent = bool(pairwise) and all(item["match"] for item in pairwise)
    return {
        "threshold": match_threshold,
        "samples": samples,
        "pairwise": pairwise,
        "consistent": consistent,
        "successful_samples": sum(1 for sample in samples if sample["success"])
    }


def _derive_action_sequences(
    predictions: List[Dict[str, Any]],
    frame_stride: int,
    fps: float
) -> Dict[str, Any]:
    if not predictions or fps <= 0:
        return {
            "segments": [],
            "label_totals": []
        }

    time_per_sample = frame_stride / fps
    segments = []
    label_totals = defaultdict(int)
    current_label = None
    current_start = None
    current_count = 0

    for pred in predictions:
        label = pred.get("label")
        frame = pred.get("frame", 0)
        if label is None:
            continue
        label_totals[label] += 1
        if label != current_label:
            if current_label is not None:
                segments.append({
                    "label": current_label,
                    "start_frame": current_start,
                    "end_frame": frame,
                    "estimated_seconds": round(current_count * time_per_sample, 2)
                })
            current_label = label
            current_start = frame
            current_count = 0
        current_count += 1

    if current_label is not None:
        end_frame = predictions[-1].get("frame", current_start)
        segments.append({
            "label": current_label,
            "start_frame": current_start,
            "end_frame": end_frame,
            "estimated_seconds": round(current_count * time_per_sample, 2)
        })

    totals_payload = [
        {
            "label": label,
            "samples": count,
            "estimated_seconds": round(count * time_per_sample, 2)
        }
        for label, count in sorted(label_totals.items(), key=lambda x: x[1], reverse=True)
    ]

    return {
        "segments": segments,
        "label_totals": totals_payload
    }


def _run_actionnet_on_image(image: np.ndarray, top_k: int):
    net = _load_actionnet()
    cuda_img = bgr_to_cuda(image)
    class_id, confidence = net.Classify(cuda_img)

    top_predictions = []
    classifications = net.GetClassifications()
    for cls in classifications:
        top_predictions.append({
            "class_id": int(cls.classID),
            "label": net.GetClassDesc(int(cls.classID)),
            "confidence": float(cls.confidence)
        })
        if len(top_predictions) >= top_k:
            break

    return {
        "predicted_class": {
            "class_id": int(class_id),
            "label": net.GetClassDesc(int(class_id)),
            "confidence": float(confidence)
        },
        "top_predictions": top_predictions
    }


def _run_actionnet_on_video(video_path: str, frame_stride: int, top_k: int):
    net = _load_actionnet()
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise HTTPException(400, "Unable to open uploaded video")

    frame_idx = 0
    processed = 0
    predictions = []

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_stride != 0:
            frame_idx += 1
            continue

        cuda_img = bgr_to_cuda(frame)
        class_id, confidence = net.Classify(cuda_img)
        predictions.append({
            "frame": frame_idx,
            "class_id": int(class_id),
            "label": net.GetClassDesc(int(class_id)),
            "confidence": float(confidence)
        })
        processed += 1
        frame_idx += 1

    cap.release()

    aggregates = defaultdict(lambda: {"count": 0, "max_confidence": 0.0})
    for pred in predictions:
        label = pred["label"]
        aggregates[label]["count"] += 1
        aggregates[label]["max_confidence"] = max(
            aggregates[label]["max_confidence"],
            pred["confidence"]
        )

    top_labels = sorted(
        [{"label": label, **stats} for label, stats in aggregates.items()],
        key=lambda x: (x["count"], x["max_confidence"]),
        reverse=True
    )[:top_k]

    return {
        "frames_analyzed": processed,
        "predictions": predictions,
        "top_labels": top_labels
    }


def _load_hit_detection_model():
    global hit_detection_net
    if hit_detection_net is None:
        model_path = HIT_DETECTION_MODEL_PATH
        if not os.path.exists(model_path):
            model_path = _resolve_hit_model_path()
        if not os.path.exists(model_path):
            raise HTTPException(
                503,
                "hit_detect.onnx no está disponible en el dispositivo. "
                "Configura HIT_DETECT_MODEL_PATH o copia el archivo a ai_engine/models/."
            )
        try:
            hit_detection_net = cv2.dnn.readNetFromONNX(model_path)
            hit_detection_net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
            hit_detection_net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
        except Exception:
            # Fallback a CPU silencioso
            hit_detection_net = cv2.dnn.readNetFromONNX(model_path)
            hit_detection_net.setPreferableBackend(cv2.dnn.DNN_BACKEND_DEFAULT)
            hit_detection_net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
    return hit_detection_net


def _run_hit_detection_on_video(
    video_path: str,
    frame_stride: int,
    max_frames: int,
    hit_threshold: float
):
    net = _load_hit_detection_model()
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise HTTPException(400, "Unable to open uploaded video")

    frame_idx = 0
    processed = 0
    detections = []

    while processed < max_frames:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_stride != 0:
            frame_idx += 1
            continue

        resized = cv2.resize(frame, (224, 224))
        blob = cv2.dnn.blobFromImage(resized, scalefactor=1 / 255.0, size=(224, 224), swapRB=True, crop=False)
        net.setInput(blob)
        output = net.forward()
        flat = output.flatten().tolist()
        if not flat:
            probability = 0.0
        elif len(flat) == 1:
            probability = float(flat[0])
        else:
            # Suponemos que la segunda salida corresponde a "hit"
            probability = float(flat[-1])

        detections.append({
            "frame": frame_idx,
            "hit_probability": round(probability, 4),
            "raw_output": flat
        })

        processed += 1
        frame_idx += 1

    cap.release()

    hits = [det for det in detections if det["hit_probability"] >= hit_threshold]

    return {
        "frames_analyzed": processed,
        "detections": detections,
        "hits_detected": len(hits),
        "hit_threshold": hit_threshold,
        "hit_frames": [det["frame"] for det in hits]
    }


def _detect_faces_with_embeddings(image: np.ndarray, score_threshold: float = 0.6) -> List[Dict[str, Any]]:
    detector, backend = _load_face_detector()
    recognizer, recognizer_backend = _load_face_recognizer()
    h, w = image.shape[:2]
    detections: List[Dict[str, Any]] = []
    multiscale_factors = [1.0, 0.85, 0.7, 0.55]

    def _scale_image(src: np.ndarray, scale: float) -> np.ndarray:
        if scale == 1.0:
            return src
        new_w = max(1, int(src.shape[1] * scale))
        new_h = max(1, int(src.shape[0] * scale))
        return cv2.resize(src, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    if backend == "jetson_detectnet":
        for scale in multiscale_factors:
            scaled_img = _scale_image(image, scale)
            cuda_img = bgr_to_cuda(scaled_img)
            raw = detector.Detect(cuda_img, overlay="none")
            if raw:
                inv_scale = 1.0 / scale
                for det in raw:
                    x1 = max(0, int(det.Left * inv_scale))
                    y1 = max(0, int(det.Top * inv_scale))
                    x2 = min(w, int(det.Right * inv_scale))
                    y2 = min(h, int(det.Bottom * inv_scale))
                    detections.append({
                        "bbox": [x1, y1, x2, y2],
                        "score": float(det.Confidence),
                        "landmarks": None,
                        "raw": None
                    })
                if detections:
                    break
    elif backend == "yunet":
        for scale in multiscale_factors:
            scaled_img = _scale_image(image, scale)
            scaled_h, scaled_w = scaled_img.shape[:2]
            detector.setInputSize((scaled_w, scaled_h))
            _, raw = detector.detect(scaled_img)
            if raw is None or len(raw) == 0:
                continue
            inv_scale = 1.0 / scale
            for face in raw:
                x, y, box_w, box_h = face[:4]
                x1 = max(0, int(x * inv_scale))
                y1 = max(0, int(y * inv_scale))
                x2 = min(w, int((x + box_w) * inv_scale))
                y2 = min(h, int((y + box_h) * inv_scale))
                landmarks = None
                raw_face = None
                if len(face) >= 14:
                    lm = (face[4:14] * inv_scale).tolist()
                    landmarks = lm
                    raw_face = face.copy()
                    raw_face = raw_face.astype(np.float32)
                    raw_face[0] = x1
                    raw_face[1] = y1
                    raw_face[2] = max(0, x2 - x1)
                    raw_face[3] = max(0, y2 - y1)
                    raw_face[4:14] = face[4:14] * inv_scale
                else:
                    raw_face = None
                detections.append({
                    "bbox": [x1, y1, x2, y2],
                    "score": float(face[4]) if len(face) > 4 else 0.0,
                    "landmarks": landmarks,
                    "raw": raw_face
                })
            if detections:
                break
    else:
        gray_original = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        for scale in multiscale_factors:
            scaled_gray = _scale_image(gray_original, scale)
            raw = detector.detectMultiScale(
                scaled_gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(48, 48)
            )
            if len(raw) == 0:
                continue
            inv_scale = 1.0 / scale
            for (x, y, box_w, box_h) in raw:
                x1 = max(0, int(x * inv_scale))
                y1 = max(0, int(y * inv_scale))
                x2 = min(w, int((x + box_w) * inv_scale))
                y2 = min(h, int((y + box_h) * inv_scale))
                detections.append({
                    "bbox": [x1, y1, x2, y2],
                    "score": 1.0,
                    "landmarks": None,
                    "raw": None
                })
            if detections:
                break

    results = []
    for det in detections:
        if det["score"] < score_threshold:
            continue

        bbox = det["bbox"]
        landmarks = det.get("landmarks")
        embedding: Optional[List[float]] = None

        if recognizer_backend == "opencv_sface" and det["raw"] is not None:
            try:
                embedding = recognizer.feature(image, det["raw"]).flatten().tolist()
            except Exception:
                embedding = None
        else:
            try:
                embedding = recognizer.extract(image, bbox, landmarks)
            except Exception:
                embedding = None

        if not embedding:
            continue

        bbox_int = [int(max(0, min(w, bbox[0]))), int(max(0, min(h, bbox[1]))), int(max(0, min(w, bbox[2]))), int(max(0, min(h, bbox[3])))]
        results.append({
            "face_id": str(uuid4()),
            "bbox": bbox_int,
            "score": det["score"],
            "embedding": embedding
        })
    return results


def _get_primary_face_embedding(image: np.ndarray, min_score: float = 0.6) -> Optional[Dict[str, Any]]:
    faces = _detect_faces_with_embeddings(image, min_score)
    if not faces:
        return None
    return max(faces, key=lambda f: f["score"])




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

    recognizer, backend = _load_face_recognizer()
    vec_a = np.array(face_a["embedding"], dtype=np.float32).reshape(1, -1)
    vec_b = np.array(face_b["embedding"], dtype=np.float32).reshape(1, -1)
    if backend == "opencv_sface":
        similarity = float(recognizer.match(vec_a, vec_b, cv2.FaceRecognizerSF_FR_COSINE))
    else:
        similarity = float(np.dot(vec_a.flatten(), vec_b.flatten()))
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
            possession_distance_px=possession_distance_px
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
            "dominant_actions": action_analysis.get("top_labels", [])
        }

        analysis = {
            "summary": summary,
            "face_checks": face_checks,
            "detection_frames_analyzed": detection_summary["frames_analyzed"],
            "detection_timeline": detection_summary["timeline"],
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

    sr, scale = _load_superres_engine()
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

    sr, scale = _load_superres_engine()
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
