"""
Inference-only API for Edge Devices (Jetson Nano - Python 3.6 Compatible)
=========================================================================
Refactored for FastAPI 0.83.0 and Python 3.6
"""

import os
import io
import time
import base64
import numpy as np
import cv2
import requests
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# --- Configuration ---
DETECTION_MODEL = os.environ.get('DETECTION_MODEL', 'yolo_fastest')
DETECTION_RESOLUTION = os.environ.get('DETECTION_RESOLUTION', 'medium')
DEVICE_NAME = os.environ.get('DEVICE_NAME', 'jetson-nano')
ENABLE_TENSORRT = os.environ.get('ENABLE_TENSORRT', 'false').lower() == 'true'
ENABLE_CUDA = os.environ.get('ENABLE_CUDA', 'true').lower() == 'true'

# Models directory
MODELS_DIR = os.path.join(os.path.dirname(__file__), "../models")
os.makedirs(MODELS_DIR, exist_ok=True)

# Global model instance
model = None
model_name = None

# --- Model Download URLs ---
MODEL_URLS = {
    "yolo-fastest-xl.cfg": "https://raw.githubusercontent.com/dog-qiuqiu/Yolo-Fastest/master/ModelZoo/yolo-fastest-xl.cfg",
    "yolo-fastest-xl.weights": "https://github.com/dog-qiuqiu/Yolo-Fastest/raw/master/ModelZoo/yolo-fastest-xl.weights",
    "yolov4-tiny.cfg": "https://raw.githubusercontent.com/AlexeyAB/darknet/master/cfg/yolov4-tiny.cfg",
    "yolov4-tiny.weights": "https://github.com/AlexeyAB/darknet/releases/download/darknet_yolo_v4_pre/yolov4-tiny.weights",
    "face_detection_yunet_2023mar.onnx": "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
}


def download_file(url: str, dest: str) -> bool:
    """Download a file from URL to destination."""
    if os.path.exists(dest):
        print(f"✅ Model already exists: {os.path.basename(dest)}")
        return True
    
    print(f"⬇️ Downloading {os.path.basename(dest)}...")
    try:
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
        
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        with open(dest, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    percent = (downloaded / total_size) * 100
                    # print(f"\r  Progress: {percent:.1f}%", end="", flush=True)
        
        print(f"\n✅ Downloaded {os.path.basename(dest)}")
        return True
    except Exception as e:
        print(f"\n❌ Failed to download {dest}: {e}")
        return False


def ensure_models_exist():
    """Ensure required models are downloaded."""
    print("🔍 Checking models...")
    
    # Download YOLO-Fastest (default model)
    yolo_cfg = os.path.join(MODELS_DIR, "yolo-fastest-xl.cfg")
    yolo_weights = os.path.join(MODELS_DIR, "yolo-fastest-xl.weights")
    
    if not os.path.exists(yolo_cfg):
        download_file(MODEL_URLS["yolo-fastest-xl.cfg"], yolo_cfg)
    if not os.path.exists(yolo_weights):
        download_file(MODEL_URLS["yolo-fastest-xl.weights"], yolo_weights)
    
    print("✅ Models check complete")


def load_model(model_type: str = None, resolution: str = None):
    """Load or reload the detection model."""
    global model, model_name
    
    if model_type is None:
        model_type = DETECTION_MODEL
    if resolution is None:
        resolution = DETECTION_RESOLUTION
    
    print(f"⏳ Loading model: {model_type} @ {resolution}...")
    
    try:
        # Import here to avoid circular imports during startup
        from .models import get_detector, ModelType, Resolution
        
        # Convert string to enum
        try:
            model_enum = ModelType(model_type.lower())
        except ValueError:
             # Fallback if enum fails
             model_enum = ModelType.YOLO_FASTEST

        try:
            res_enum = Resolution(resolution.lower())
        except ValueError:
            res_enum = Resolution.MEDIUM
        
        model = get_detector(model_type=model_enum, resolution=res_enum)
        model.load_model()
        model_name = model_type
        
        print(f"✅ Model {model_type} loaded successfully")
        return True
    except Exception as e:
        print(f"❌ Error loading model {model_type}: {e}")
        # Try fallback
        try:
            print("⚠️ Trying fallback model: yolo_fastest")
            # Re-import just in case
            from .models import get_detector, ModelType
            model = get_detector(model_type=ModelType.YOLO_FASTEST)
            model.load_model()
            model_name = "yolo_fastest"
            return True
        except Exception as e2:
            print(f"❌ Fallback also failed: {e2}")
            return False


# --- FastAPI App Setup (Python 3.6 Compatible) ---
app = FastAPI(
    title="Edge Inference API",
    description="Lightweight inference API for edge devices (Jetson Nano)",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Startup/Shutdown Events (Classic Style) ---
@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    print("🚀 Starting Inference API...")
    ensure_models_exist()
    load_model()

@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown."""
    print("👋 Shutting down inference API...")


# --- Request/Response Models ---
class DetectionRequest(BaseModel):
    image_base64: str = Field(..., description="Base64 encoded image")
    confidence_threshold: float = Field(0.5, ge=0.0, le=1.0)
    classes: Optional[List[str]] = Field(None)
    max_detections: int = Field(100, ge=1, le=500)

class Detection(BaseModel):
    class_name: str
    class_id: int
    confidence: float
    bbox: List[float]  # [x1, y1, x2, y2] normalized
    bbox_pixels: List[int] # [x1, y1, x2, y2] pixels

class DetectionResponse(BaseModel):
    success: bool
    detections: List[Detection]
    count: int
    inference_time_ms: float
    model: str
    device: str
    image_size: List[int]

class BatchDetectionRequest(BaseModel):
    images: List[str]
    confidence_threshold: float = Field(0.5)
    classes: Optional[List[str]] = None

class BatchDetectionResponse(BaseModel):
    success: bool
    results: List[DetectionResponse]
    total_inference_time_ms: float
    avg_inference_time_ms: float

class ModelChangeRequest(BaseModel):
    model: str
    resolution: str = "medium"

class HealthResponse(BaseModel):
    status: str
    device: str
    model: str
    cuda_available: bool
    uptime_seconds: float


# Track startup time
startup_time = time.time()


def decode_image(base64_str: str) -> np.ndarray:
    try:
        if ',' in base64_str:
            base64_str = base64_str.split(',')[1]
        
        img_bytes = base64.b64decode(base64_str)
        img_array = np.frombuffer(img_bytes, dtype=np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        
        if img is None:
            raise ValueError("Failed to decode image")
        
        return img
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image: {str(e)}")


def run_inference(image: np.ndarray, confidence_threshold: float = 0.5, 
                  filter_classes: List[str] = None, max_detections: int = 100) -> tuple:
    global model, model_name
    
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    h, w = image.shape[:2]
    start_time = time.perf_counter()
    
    # Run detection
    try:
        results = model.detect(image, confidence=confidence_threshold)
    except Exception as e:
        print(f"Inference error: {e}")
        return [], 0.0, [w, h]
    
    inference_time = (time.perf_counter() - start_time) * 1000
    
    # Process results
    detections = []
    class_names = model.get_class_names()
    
    # Adapt to whatever format the model returns (list of dicts usually)
    for det in results:
        if len(detections) >= max_detections:
            break
        
        # Standardize Dict format
        if isinstance(det, dict):
            class_id = det.get('class_id', 0)
            # Safe class name retrieval
            if 0 <= class_id < len(class_names):
                class_name = class_names[class_id]
            else:
                class_name = det.get('class_name', f"class_{class_id}")
            
            if filter_classes and class_name not in filter_classes:
                continue
            
            bbox = det.get('bbox', det.get('box', [0, 0, 0, 0]))
            x1, y1, x2, y2 = map(int, bbox[:4])
            
            detections.append(Detection(
                class_name=str(class_name),
                class_id=int(class_id),
                confidence=float(det.get('confidence', det.get('score', 0.0))),
                bbox=[x1/w, y1/h, x2/w, y2/h],
                bbox_pixels=[x1, y1, x2, y2]
            ))

    return detections, inference_time, [w, h]


# --- API Endpoints ---

@app.get("/health", response_model=HealthResponse)
async def health_check():
    cuda_available = False
    try:
        import torch
        cuda_available = torch.cuda.is_available()
    except ImportError:
        pass
    
    return HealthResponse(
        status="healthy" if model is not None else "model_not_loaded",
        device=DEVICE_NAME,
        model=model_name or "none",
        cuda_available=cuda_available,
        uptime_seconds=time.time() - startup_time
    )

@app.get("/models")
async def list_models():
    # Simplified mock response to avoid import errors if factory fails
    return {
        "current_model": model_name,
        "available_models": ["yolo_fastest"],
        "device": DEVICE_NAME
    }

@app.post("/models/change")
async def change_model(request: ModelChangeRequest):
    success = load_model(request.model, request.resolution)
    if success:
        return {"success": True, "model": model_name, "message": "Model changed"}
    else:
        raise HTTPException(status_code=500, detail="Failed to load model")

@app.post("/detect", response_model=DetectionResponse)
async def detect(request: DetectionRequest):
    image = decode_image(request.image_base64)
    detections, inference_time, image_size = run_inference(
        image,
        confidence_threshold=request.confidence_threshold,
        filter_classes=request.classes,
        max_detections=request.max_detections
    )
    return DetectionResponse(
        success=True,
        detections=detections,
        count=len(detections),
        inference_time_ms=inference_time,
        model=model_name or "unknown",
        device=DEVICE_NAME,
        image_size=image_size
    )

@app.post("/detect/faces")
async def detect_faces(request: DetectionRequest):
    """
    Specialized face detection endpoint.
    NOTE: Might fail if OpenCV version on Jetson is too old (< 4.5.4).
    """
    image = decode_image(request.image_base64)
    h, w = image.shape[:2]
    
    # Check if this OpenCV version supports YuNet
    if not hasattr(cv2, 'FaceDetectorYN'):
        raise HTTPException(status_code=501, detail="Face detection not supported on this OpenCV version")

    models_dir = MODELS_DIR
    yunet_path = os.path.join(models_dir, "face_detection_yunet_2023mar.onnx")
    
    # Download if missing
    if not os.path.exists(yunet_path):
        download_file(MODEL_URLS["face_detection_yunet_2023mar.onnx"], yunet_path)
    
    try:
        face_detector = cv2.FaceDetectorYN.create(
            yunet_path, "", (w, h),
            score_threshold=request.confidence_threshold,
            nms_threshold=0.3,
            top_k=100
        )
        
        start_time = time.perf_counter()
        _, faces = face_detector.detect(image)
        inference_time = (time.perf_counter() - start_time) * 1000
        
        detections = []
        if faces is not None:
            for face in faces:
                x, y, fw, fh = int(face[0]), int(face[1]), int(face[2]), int(face[3])
                conf = float(face[-1])
                detections.append(Detection(
                    class_name="face",
                    class_id=0,
                    confidence=conf,
                    bbox=[x/w, y/h, (x+fw)/w, (y+fh)/h],
                    bbox_pixels=[x, y, x+fw, y+fh]
                ))
                
        return DetectionResponse(
            success=True,
            detections=detections,
            count=len(detections),
            inference_time_ms=inference_time,
            model="yunet",
            device=DEVICE_NAME,
            image_size=[w, h]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Face detection error: {e}")

# --- Main ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5050)
