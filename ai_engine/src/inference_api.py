"""
Inference-only API for Edge Devices (Jetson Nano)
UPDATED: Uses YOLOv4-Tiny (Reliable & DNN Compatible)
"""

import os
import time
import base64
import numpy as np
import cv2
import requests
from typing import Optional, List
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# --- Configuration ---
# CAMBIO: Usamos yolov4-tiny por defecto porque es 100% compatible con OpenCV DNN
DETECTION_MODEL = os.environ.get('DETECTION_MODEL', 'yolov4-tiny')
DETECTION_RESOLUTION = os.environ.get('DETECTION_RESOLUTION', 'medium')
DEVICE_NAME = os.environ.get('DEVICE_NAME', 'jetson-nano')

# Models directory
MODELS_DIR = os.path.join(os.path.dirname(__file__), "../models")
os.makedirs(MODELS_DIR, exist_ok=True)

# Global model instance
net = None
output_layers = None
classes = []
model_name = None

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

@app.get("/health")
def health():
    return {"status": "ok", "model": model_name, "cuda": cv2.cuda.getCudaEnabledDeviceCount() > 0}

@app.post("/detect")
def detect(req: DetectionRequest):
    global net
    if net is None:
        raise HTTPException(503, "Model not loaded")

    # Decode Image
    try:
        if ',' in req.image_base64:
            b64 = req.image_base64.split(',')[1]
        else:
            b64 = req.image_base64
        img_bytes = base64.b64decode(b64)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    except:
        raise HTTPException(400, "Invalid image")

    height, width = img.shape[:2]
    
    # Inference
    start = time.perf_counter()
    blob = cv2.dnn.blobFromImage(img, 1/255.0, (416, 416), (0,0,0), swapRB=True, crop=False)
    net.setInput(blob)
    outs = net.forward(output_layers)
    
    # Process outputs
    class_ids = []
    confidences = []
    boxes = []
    
    for out in outs:
        for detection in out:
            scores = detection[5:]
            class_id = np.argmax(scores)
            confidence = scores[class_id]
            if confidence > req.confidence:
                # YOLO returns center_x, center_y, w, h
                cx = int(detection[0] * width)
                cy = int(detection[1] * height)
                w = int(detection[2] * width)
                h = int(detection[3] * height)
                x = int(cx - w / 2)
                y = int(cy - h / 2)
                
                boxes.append([x, y, w, h])
                confidences.append(float(confidence))
                class_ids.append(class_id)
    
    # NMS (Non-Maximum Suppression)
    indices = cv2.dnn.NMSBoxes(boxes, confidences, req.confidence, req.nms_threshold)
    
    results = []
    if len(indices) > 0:
        for i in indices.flatten():
            x, y, w, h = boxes[i]
            label = str(classes[class_ids[i]])
            results.append({
                "class_name": label,
                "confidence": round(confidences[i], 2),
                "bbox": [x, y, x+w, y+h] # x1, y1, x2, y2
            })
            
    return {
        "success": True,
        "detections": results,
        "time_ms": round((time.perf_counter() - start) * 1000, 2)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5050)
