"""
Inference-only API for Edge Devices (Jetson Nano, Raspberry Pi, etc.)
=====================================================================

This is a lightweight FastAPI service that ONLY handles inference.
No streaming, no Redis, no complex dependencies.

Architecture:
- Main Server: Handles video streaming, frontend, backend, Redis
- Edge Device (Jetson): Receives frames via HTTP, returns detections

Usage:
    uvicorn src.inference_api:app --host 0.0.0.0 --port 5050

Endpoints:
    POST /detect - Detect objects in an image (base64 or file upload)
    POST /detect/batch - Batch detection for multiple frames
    GET /health - Health check
    GET /models - List available models
    POST /models/change - Change detection model
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
from contextlib import asynccontextmanager

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
    "yolov8n.onnx": "https://github.com/ultralytics/assets/releases/download/v8.1.0/yolov8n.onnx",
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
                    print(f"\r  Progress: {percent:.1f}%", end="", flush=True)
        
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
    
    # Download YuNet for face detection
    yunet = os.path.join(MODELS_DIR, "face_detection_yunet_2023mar.onnx")
    if not os.path.exists(yunet):
        download_file(MODEL_URLS["face_detection_yunet_2023mar.onnx"], yunet)
    
    print("✅ Models check complete")


def load_model(model_type: str = None, resolution: str = None):
    """Load or reload the detection model."""
    global model, model_name
    
    if model_type is None:
        model_type = DETECTION_MODEL
    if resolution is None:
        resolution = DETECTION_RESOLUTION
    
    print(f"⏳ Loading model: {model_type} @ {resolution}...")
    
    # Import here to avoid circular imports
    from .models import get_detector, ModelType, Resolution
    
    try:
        # Convert string to enum
        model_enum = ModelType(model_type.lower())
        res_enum = Resolution(resolution.lower())
        
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
            model = get_detector(model_type=ModelType.YOLO_FASTEST)
            model.load_model()
            model_name = "yolo_fastest"
            return True
        except Exception as e2:
            print(f"❌ Fallback also failed: {e2}")
            return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup: Ensure models exist and load
    ensure_models_exist()
    load_model()
    yield
    # Shutdown: Cleanup
    print("👋 Shutting down inference API...")


# --- FastAPI App ---
app = FastAPI(
    title="Edge Inference API",
    description="Lightweight inference API for edge devices (Jetson Nano, etc.)",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request/Response Models ---
class DetectionRequest(BaseModel):
    """Request model for detection."""
    image_base64: str = Field(..., description="Base64 encoded image (JPEG/PNG)")
    confidence_threshold: float = Field(0.5, ge=0.0, le=1.0, description="Minimum confidence")
    classes: Optional[List[str]] = Field(None, description="Filter by class names")
    max_detections: int = Field(100, ge=1, le=500, description="Maximum detections to return")


class Detection(BaseModel):
    """Single detection result."""
    class_name: str
    class_id: int
    confidence: float
    bbox: List[float]  # [x1, y1, x2, y2] normalized or pixel coords
    bbox_pixels: List[int]  # [x1, y1, x2, y2] in pixels


class DetectionResponse(BaseModel):
    """Response model for detection."""
    success: bool
    detections: List[Detection]
    count: int
    inference_time_ms: float
    model: str
    device: str
    image_size: List[int]  # [width, height]


class BatchDetectionRequest(BaseModel):
    """Request for batch detection."""
    images: List[str] = Field(..., description="List of base64 encoded images")
    confidence_threshold: float = Field(0.5, ge=0.0, le=1.0)
    classes: Optional[List[str]] = None


class BatchDetectionResponse(BaseModel):
    """Response for batch detection."""
    success: bool
    results: List[DetectionResponse]
    total_inference_time_ms: float
    avg_inference_time_ms: float


class ModelChangeRequest(BaseModel):
    """Request to change model."""
    model: str = Field(..., description="Model type: yolo_fastest, onnx, mobilenet_ssd, etc.")
    resolution: str = Field("medium", description="Resolution: low, medium, high")


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    device: str
    model: str
    cuda_available: bool
    tensorrt_available: bool
    uptime_seconds: float


# Track startup time
startup_time = time.time()


def decode_image(base64_str: str) -> np.ndarray:
    """Decode base64 string to OpenCV image."""
    try:
        # Remove data URL prefix if present
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
    """
    Run inference on an image.
    
    Returns:
        tuple: (detections_list, inference_time_ms, image_size)
    """
    global model, model_name
    
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    h, w = image.shape[:2]
    
    start_time = time.perf_counter()
    
    # Run detection
    results = model.detect(image, confidence=confidence_threshold)
    
    inference_time = (time.perf_counter() - start_time) * 1000  # ms
    
    # Process results
    detections = []
    class_names = model.get_class_names()
    
    for det in results:
        if len(detections) >= max_detections:
            break
        
        # Handle different result formats
        if hasattr(det, 'boxes'):
            # Supervision/Ultralytics format
            for i, box in enumerate(det.boxes):
                class_id = int(det.class_id[i]) if hasattr(det, 'class_id') else 0
                conf = float(det.confidence[i]) if hasattr(det, 'confidence') else 1.0
                class_name = class_names[class_id] if class_id < len(class_names) else f"class_{class_id}"
                
                if filter_classes and class_name not in filter_classes:
                    continue
                
                x1, y1, x2, y2 = map(int, box)
                detections.append(Detection(
                    class_name=class_name,
                    class_id=class_id,
                    confidence=conf,
                    bbox=[x1/w, y1/h, x2/w, y2/h],  # Normalized
                    bbox_pixels=[x1, y1, x2, y2]
                ))
        elif isinstance(det, dict):
            # Dict format
            class_id = det.get('class_id', 0)
            class_name = det.get('class_name', class_names[class_id] if class_id < len(class_names) else f"class_{class_id}")
            
            if filter_classes and class_name not in filter_classes:
                continue
            
            bbox = det.get('bbox', det.get('box', [0, 0, 0, 0]))
            x1, y1, x2, y2 = map(int, bbox[:4])
            
            detections.append(Detection(
                class_name=class_name,
                class_id=class_id,
                confidence=det.get('confidence', det.get('score', 1.0)),
                bbox=[x1/w, y1/h, x2/w, y2/h],
                bbox_pixels=[x1, y1, x2, y2]
            ))
        elif hasattr(det, 'xyxy'):
            # Supervision Detections format
            for i in range(len(det.xyxy)):
                class_id = int(det.class_id[i]) if det.class_id is not None else 0
                conf = float(det.confidence[i]) if det.confidence is not None else 1.0
                class_name = class_names[class_id] if class_id < len(class_names) else f"class_{class_id}"
                
                if filter_classes and class_name not in filter_classes:
                    continue
                
                x1, y1, x2, y2 = map(int, det.xyxy[i])
                detections.append(Detection(
                    class_name=class_name,
                    class_id=class_id,
                    confidence=conf,
                    bbox=[x1/w, y1/h, x2/w, y2/h],
                    bbox_pixels=[x1, y1, x2, y2]
                ))
    
    return detections, inference_time, [w, h]


# --- API Endpoints ---

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    cuda_available = False
    tensorrt_available = False
    
    try:
        import torch
        cuda_available = torch.cuda.is_available()
    except ImportError:
        pass
    
    # Check TensorRT
    try:
        import tensorrt
        tensorrt_available = True
    except ImportError:
        pass
    
    return HealthResponse(
        status="healthy" if model is not None else "model_not_loaded",
        device=DEVICE_NAME,
        model=model_name or "none",
        cuda_available=cuda_available,
        tensorrt_available=tensorrt_available,
        uptime_seconds=time.time() - startup_time
    )


@app.get("/models")
async def list_models():
    """List available models."""
    from .models import ModelFactory
    
    available = ModelFactory.list_available_models()
    return {
        "current_model": model_name,
        "available_models": available,
        "device": DEVICE_NAME
    }


@app.post("/models/change")
async def change_model(request: ModelChangeRequest):
    """Change the detection model."""
    success = load_model(request.model, request.resolution)
    
    if success:
        return {
            "success": True,
            "model": model_name,
            "resolution": request.resolution,
            "message": f"Model changed to {model_name}"
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to load model")


@app.post("/detect", response_model=DetectionResponse)
async def detect(request: DetectionRequest):
    """
    Detect objects in a single image.
    
    Send a base64 encoded image and receive detections.
    """
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


@app.post("/detect/upload", response_model=DetectionResponse)
async def detect_upload(
    file: UploadFile = File(...),
    confidence_threshold: float = Form(0.5),
    classes: Optional[str] = Form(None),  # Comma-separated
    max_detections: int = Form(100)
):
    """
    Detect objects in an uploaded image file.
    
    Alternative to base64 for direct file uploads.
    """
    contents = await file.read()
    img_array = np.frombuffer(contents, dtype=np.uint8)
    image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    
    if image is None:
        raise HTTPException(status_code=400, detail="Invalid image file")
    
    filter_classes = classes.split(',') if classes else None
    
    detections, inference_time, image_size = run_inference(
        image,
        confidence_threshold=confidence_threshold,
        filter_classes=filter_classes,
        max_detections=max_detections
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


@app.post("/detect/batch", response_model=BatchDetectionResponse)
async def detect_batch(request: BatchDetectionRequest):
    """
    Batch detection for multiple images.
    
    More efficient than calling /detect multiple times.
    """
    results = []
    total_time = 0
    
    for img_b64 in request.images:
        image = decode_image(img_b64)
        
        detections, inference_time, image_size = run_inference(
            image,
            confidence_threshold=request.confidence_threshold,
            filter_classes=request.classes
        )
        
        total_time += inference_time
        
        results.append(DetectionResponse(
            success=True,
            detections=detections,
            count=len(detections),
            inference_time_ms=inference_time,
            model=model_name or "unknown",
            device=DEVICE_NAME,
            image_size=image_size
        ))
    
    return BatchDetectionResponse(
        success=True,
        results=results,
        total_inference_time_ms=total_time,
        avg_inference_time_ms=total_time / len(results) if results else 0
    )


@app.post("/detect/faces")
async def detect_faces(request: DetectionRequest):
    """
    Specialized face detection endpoint.
    
    Uses YuNet for fast face detection.
    """
    image = decode_image(request.image_base64)
    h, w = image.shape[:2]
    
    # Load YuNet face detector
    models_dir = os.path.join(os.path.dirname(__file__), "../models")
    yunet_path = os.path.join(models_dir, "face_detection_yunet_2023mar.onnx")
    
    if not os.path.exists(yunet_path):
        raise HTTPException(status_code=503, detail="Face detection model not available")
    
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
            
            if len(detections) >= request.max_detections:
                break
            
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


# --- Main ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5050)
