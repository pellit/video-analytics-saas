"""
Inference-only API for Edge Devices (Jetson Nano)
UPDATED: Uses YOLOv4-Tiny (Reliable & DNN Compatible)
"""

import os
import time
import base64
import tempfile
import numpy as np
import cv2
import requests
from collections import defaultdict
from typing import Optional, List


# --- Jetson data directory configuration ------------------------------------
DEFAULT_JETSON_DATA_DIR = '/home/jetson/video-analytics-saas/data'
CUSTOM_JETSON_DATA_DIR = os.environ.get('JETSON_DATA_DIR_OVERRIDE')


def _configure_jetson_data_dir():
    candidate = None
    if CUSTOM_JETSON_DATA_DIR:
        candidate = CUSTOM_JETSON_DATA_DIR
    elif os.path.isdir(DEFAULT_JETSON_DATA_DIR):
        candidate = DEFAULT_JETSON_DATA_DIR

    if candidate and os.path.isdir(candidate):
        if not os.environ.get('JETSON_DATA_DIR'):
            os.environ['JETSON_DATA_DIR'] = candidate
        root_guess = os.path.dirname(candidate)
        os.environ.setdefault('JETSON_INFERENCE_ROOT', root_guess)
        print(f"📁 Jetson data dir: {os.environ['JETSON_DATA_DIR']}")


_configure_jetson_data_dir()

JETSON_DATA_DIR_ACTIVE = os.environ.get('JETSON_DATA_DIR')
JETSON_NETWORKS_DIR = (
    os.path.join(JETSON_DATA_DIR_ACTIVE, 'networks')
    if JETSON_DATA_DIR_ACTIVE else None
)
JETSON_MODELS_MANIFEST = (
    os.path.join(JETSON_NETWORKS_DIR, 'models.json')
    if JETSON_NETWORKS_DIR else None
)
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

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

# Models directory
MODELS_DIR = os.path.join(os.path.dirname(__file__), "../models")
os.makedirs(MODELS_DIR, exist_ok=True)

# Global model instance
net = None
output_layers = None
classes = []
model_name = None
actionnet = None
depthnet = None
hit_detection_net = None

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


def _load_depthnet():
    global depthnet
    if depthnet is None:
        if not JETSON_INFERENCE_AVAILABLE:
            raise HTTPException(503, "jetson-inference is not available on this device")
        try:
            depthnet = jetson.inference.depthNet(DEPTHNET_MODEL)
        except Exception as exc:
            manifest_hint = JETSON_MODELS_MANIFEST or "networks/models.json"
            raise HTTPException(
                503,
                f"jetson-inference depthNet failed to load '{DEPTHNET_MODEL}'. "
                f"Verifica que exista {manifest_hint} y los pesos requeridos. Detalle: {exc}"
            )
    return depthnet

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


def _cuda_from_bgr(frame: np.ndarray):
    rgba = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
    return jetson.utils.cudaFromNumpy(rgba)


def _run_actionnet_on_image(image: np.ndarray, top_k: int):
    net = _load_actionnet()
    cuda_img = _cuda_from_bgr(image)
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

        cuda_img = _cuda_from_bgr(frame)
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


def _run_depthnet_on_video(video_path: str, frame_stride: int, max_frames: int, preview_frames: int = 3):
    net = _load_depthnet()
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise HTTPException(400, "Unable to open uploaded video")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    if width <= 0 or height <= 0:
        cap.release()
        raise HTTPException(400, "Invalid video dimensions")

    frame_idx = 0
    processed = 0
    summaries = []
    previews = []

    while processed < max_frames:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_stride != 0:
            frame_idx += 1
            continue

        cuda_img = _cuda_from_bgr(frame)
        # --- CORRECCIÓN DEPTHNET ---
        # 1. Crear buffer de salida visual si no existe
        if not hasattr(net, 'overlay'):
            net.overlay = jetson.utils.cudaAllocMapped(width=cuda_img.width, height=cuda_img.height, format=cuda_img.format)
        # 2. Procesar (Calcular profundidad)
        net.Process(cuda_img)
        # 3. Visualizar (Pintar el mapa de profundidad en el buffer)
        net.Visualize(net.overlay)
        depth_img = net.overlay
        # ---------------------------
        depth_np = jetson.utils.cudaToNumpy(depth_img, width, height, 1).squeeze()

        summaries.append({
            "frame": frame_idx,
            "mean_depth": float(np.mean(depth_np)),
            "min_depth": float(np.min(depth_np)),
            "max_depth": float(np.max(depth_np)),
        })

        if len(previews) < preview_frames:
            normalized = cv2.normalize(depth_np, None, 0, 255, cv2.NORM_MINMAX)
            normalized = normalized.astype(np.uint8)
            heatmap = cv2.applyColorMap(normalized, cv2.COLORMAP_PLASMA)
            _, buffer = cv2.imencode('.jpg', heatmap, [cv2.IMWRITE_JPEG_QUALITY, 85])
            previews.append({
                "frame": frame_idx,
                "preview_base64": "data:image/jpeg;base64," + base64.b64encode(buffer).decode()
            })

        processed += 1
        frame_idx += 1

    cap.release()

    return {
        "frames_analyzed": processed,
        "summaries": summaries,
        "previews": previews
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
    frame_stride: int = Form(5),
    max_frames: int = Form(120),
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
        results = _run_depthnet_on_video(tmp_path, frame_stride, max_frames)
        return {
            "success": True,
            "video_duration_s": duration,
            **results
        }
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5050)
