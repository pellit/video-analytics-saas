import os
import json
import time
import threading
import base64
import asyncio
import cv2
import redis
import numpy as np
import requests
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from yt_dlp import YoutubeDL
from pydantic import BaseModel
from typing import Optional, List
from .depth_service import DepthService
from .models import get_detector, ModelFactory
from .core.satellite import get_satellite_service, SatelliteService
from .core.vlm import get_vlm_analyzer, init_vlm_analyzer, VLMPrompts
from .core.hybrid import get_hybrid_analyzer, init_hybrid_analyzer, AlertSeverity
from .core.image_comparison import (
    get_comparator, compare_images, compare_images_from_base64,
    ComparisonResult, ChangeSeverity, ChangeType
)

app = FastAPI()

# --- Model Management ---
MODELS_DIR = os.path.join(os.path.dirname(__file__), "../models")
os.makedirs(MODELS_DIR, exist_ok=True)

YUNET_PATH = os.path.join(MODELS_DIR, "face_detection_yunet_2023mar.onnx")
SFACE_PATH = os.path.join(MODELS_DIR, "face_recognition_sface_2021dec.onnx")

# VLM (Moondream) - Lazy loaded to save RAM at startup
vlm_analyzer = None
VLM_ENABLED = os.environ.get('ENABLE_VLM', 'true').lower() == 'true'

# Hybrid Analyzer - Lazy loaded
hybrid_analyzer = None

# Initialize Services
depth_service = DepthService()

def download_file(url, dest):
    if os.path.exists(dest): return True
    print(f"⬇️ Downloading {os.path.basename(dest)}...")
    try:
        r = requests.get(url, stream=True, timeout=30)
        r.raise_for_status()
        # Create parent directory if needed
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"✅ Downloaded {os.path.basename(dest)}")
        return True
    except Exception as e:
        print(f"❌ Failed to download {dest}: {e}")
        return False

# Download models on import/startup (non-blocking)
yunet_ok = download_file("https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx", YUNET_PATH)
sface_ok = download_file("https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx", SFACE_PATH)

# Initialize Face Models (Lazy - will be None if models unavailable)
face_recognizer = None
FACE_RECOGNITION_AVAILABLE = False

def init_face_recognizer():
    """Initialize face recognizer if model is available."""
    global face_recognizer, FACE_RECOGNITION_AVAILABLE
    if face_recognizer is not None:
        return FACE_RECOGNITION_AVAILABLE
    
    if os.path.exists(SFACE_PATH):
        try:
            face_recognizer = cv2.FaceRecognizerSF.create(SFACE_PATH, "")
            FACE_RECOGNITION_AVAILABLE = True
            print("✅ Face recognizer initialized")
        except Exception as e:
            print(f"⚠️ Face recognizer unavailable: {e}")
            FACE_RECOGNITION_AVAILABLE = False
    else:
        print("⚠️ Face recognition model not found - feature disabled")
        FACE_RECOGNITION_AVAILABLE = False
    
    return FACE_RECOGNITION_AVAILABLE


def non_max_suppression_faces(faces, iou_threshold=0.4):
    """
    Apply Non-Maximum Suppression to remove duplicate face detections.
    
    Args:
        faces: List of face arrays [x, y, w, h, landmarks..., score]
        iou_threshold: IoU threshold for suppression
    
    Returns:
        List of filtered face detections
    """
    if not faces or len(faces) == 0:
        return []
    
    # Convert to numpy array
    faces_arr = np.array(faces)
    
    # Extract boxes and scores
    boxes = faces_arr[:, 0:4]  # x, y, w, h
    scores = faces_arr[:, -1]  # confidence score
    
    # Convert to x1, y1, x2, y2 format
    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 0] + boxes[:, 2]
    y2 = boxes[:, 1] + boxes[:, 3]
    
    # Sort by score (descending)
    indices = np.argsort(scores)[::-1]
    
    keep = []
    while len(indices) > 0:
        i = indices[0]
        keep.append(i)
        
        if len(indices) == 1:
            break
        
        # Compute IoU with remaining boxes
        xx1 = np.maximum(x1[i], x1[indices[1:]])
        yy1 = np.maximum(y1[i], y1[indices[1:]])
        xx2 = np.minimum(x2[i], x2[indices[1:]])
        yy2 = np.minimum(y2[i], y2[indices[1:]])
        
        w = np.maximum(0, xx2 - xx1)
        h = np.maximum(0, yy2 - yy1)
        
        intersection = w * h
        area_i = (x2[i] - x1[i]) * (y2[i] - y1[i])
        area_others = (x2[indices[1:]] - x1[indices[1:]]) * (y2[indices[1:]] - y1[indices[1:]])
        union = area_i + area_others - intersection
        
        iou = intersection / (union + 1e-6)
        
        # Keep boxes with IoU below threshold
        remaining = np.where(iou <= iou_threshold)[0]
        indices = indices[remaining + 1]
    
    return [faces[i] for i in keep]


# Try to init on startup (but don't fail if unavailable)
init_face_recognizer()

# Permitir CORS para que el Frontend pueda ver el video
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')

# --- MEJORA: Bucle de conexión robusto ---
r = None
while True:
    try:
        print(f"⏳ Intentando conectar a Redis en: {REDIS_HOST}...")
        r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)
        r.ping() # Ping para verificar conexión real
        print("✅ Conexión exitosa a Redis.")
        break
    except Exception as e:
        print(f"⚠️ Redis no está listo ({e}). Reintentando en 2s...")
        time.sleep(2)
# -----------------------------------------

global_state = {
    "streams": {},  # camera_id => { active, url, current_frame, lock, thread }
    "lock": threading.Lock()
}

# --- Model Loading with Abstraction Layer ---
print("⏳ Cargando modelo de detección...")
print(f"📋 Modelos disponibles: {list(ModelFactory.list_available_models().keys())}")

# Get detector from environment (default: ONNX or RT-DETR fallback)
# Set DETECTION_MODEL env var to change: 'onnx', 'yolo_nas', 'rt_detr', or 'ultralytics'
try:
    model = get_detector()
    model.load_model()
    class_names = model.get_class_names()
    print(f"✅ Modelo {model.__class__.__name__} cargado correctamente.")
except Exception as e:
    print(f"❌ Error cargando modelo: {e}")
    print("⚠️ Intentando cargar modelo de respaldo RT-DETR...")
    from src.models.rt_detr import RTDETRDetector
    model = RTDETRDetector()
    model.load_model()
    class_names = model.get_class_names()
    print("✅ Modelo de respaldo RT-DETR cargado.")

# 1. MEJORA: Forzamos formato compatible con OpenCV
def get_stream_url(youtube_url):
    try:
        # Primero intentamos obtener un stream directo MP4 (más compatible con OpenCV)
        ydl_opts = {
            'format': 'best[ext=mp4][height<=720]/best[ext=mp4]/best[height<=720]/best',
            'quiet': True,
            'no_warnings': True,
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
        }
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            url = info.get('url')
            if url:
                print(f"✅ Stream URL obtenida correctamente")
                return url
            # Si no hay URL directa, buscar en formatos
            formats = info.get('formats', [])
            for f in formats:
                if f.get('ext') == 'mp4' and f.get('url'):
                    return f['url']
            # Fallback: usar la URL del primer formato disponible
            if formats:
                return formats[-1].get('url', youtube_url)
        return youtube_url
    except Exception as e:
        print(f"❌ Error yt-dlp: {e}")
        return youtube_url

def stream_thread(camera_id, url):
    print(f"🚀 Iniciando stream thread para camera {camera_id}")
    cap = None
    last_url = None

    while True:
        with global_state['lock']:
            stream = global_state['streams'].get(str(camera_id))
            if not stream or not stream.get('active'):
                if cap:
                    cap.release(); cap = None
                time.sleep(0.5)
                continue
            current_url = stream.get('url')
            
        # Re-initialize if URL changed or cap is None
        if cap is None or current_url != last_url:
            if cap:
                cap.release()
            
            print(f"🔍 Buscando stream para: {current_url}")
            if "youtube" in current_url or "youtu.be" in current_url:
                real_url = get_stream_url(current_url)
                print(f"▶ Stream URL obtenida (imprimiendo primeros 50 chars): {real_url[:50]}...")
            else:
                real_url = current_url
                # Aumentamos el buffer para evitar cortes
                os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;udp"
            
            cap = cv2.VideoCapture(real_url)
            last_url = current_url
            
            # Verificación extra
            if not cap.isOpened():
                print("❌ ERROR CRÍTICO: OpenCV no pudo abrir la URL.")
                cap = None
                time.sleep(2)
                continue
        
        success, frame = cap.read()
        
        if not success:
            # Si falla la lectura, liberamos cap para forzar reconexión
            # Solo reintenta suavemente
            if cap:
                cap.release()
            cap = None
            time.sleep(0.1)
            continue

        # Get config
        detection_classes = []
        face_enabled = False
        depth_enabled = False
        bev_enabled = False
        tracking_enabled = False
        with global_state['lock']:
            stream = global_state['streams'].get(str(camera_id))
            if stream:
                detection_classes = stream.get('detection_classes', [])
                face_enabled = stream.get('face_enabled', False)
                depth_enabled = stream.get('depth_enabled', False)
                bev_enabled = stream.get('bev_enabled', False)
                tracking_enabled = stream.get('tracking_enabled', False)

        # Inferencia con modelo abstracto
        classes_indices = None
        if detection_classes and class_names:
            # Map class names to indices
            classes_indices = []
            for idx, cls_name in class_names.items():
                if cls_name in detection_classes:
                    classes_indices.append(idx)
            if not classes_indices:
                classes_indices = None  # No valid classes found, detect all
        
        # Get confidence threshold from config (default 0.5)
        confidence_threshold = 0.5
        with global_state['lock']:
            stream = global_state['streams'].get(str(camera_id))
            if stream:
                confidence_threshold = stream.get('confidence_threshold', 0.5)
        
        # Use tracking or regular detection based on config
        try:
            if tracking_enabled:
                detections, annotated_frame = model.track(
                    frame, 
                    confidence_threshold=confidence_threshold,
                    classes=classes_indices
                )
            else:
                detections, annotated_frame = model.detect(
                    frame, 
                    confidence_threshold=confidence_threshold,
                    classes=classes_indices
                )
        except Exception as e:
            print(f"⚠️ Error en inferencia: {e}")
            detections = []
            annotated_frame = frame.copy()

        # Depth / 3D Logic
        if depth_enabled:
            try:
                # Convert detections to format expected by Depth Service
                detections_list = []
                for det in detections:
                    det_item = {
                        'label': det.class_name,
                        'bbox': list(det.bbox),
                        'score': det.confidence
                    }
                    # Add track ID if tracking is enabled
                    if tracking_enabled and det.track_id is not None:
                        det_item['track_id'] = det.track_id
                    detections_list.append(det_item)
                
                annotated_frame, bev_map, bev_data = depth_service.process_3d_view(annotated_frame, detections_list, enable_bev=bev_enabled)
                
                # Send BEV data to frontend via Redis (no concatenation to video)
                if bev_enabled and bev_data and bev_data['objects']:
                    bev_event = {
                        'camera_id': int(camera_id),
                        'event': 'bev_update',
                        'bev_data': bev_data
                    }
                    r.publish('bev_events', json.dumps(bev_event))
                
            except Exception as e:
                print(f"⚠️ Depth error: {e}")

        # Face Recognition Logic (only if models are available)
        # Multi-scale detection for better results with different face sizes
        if face_enabled and os.path.exists(YUNET_PATH):
            try:
                h, w, _ = frame.shape
                all_faces = []
                
                # Multi-scale detection: try different scales for better detection
                # Scales: original, 1.5x upscale for small faces, 0.75x for performance
                scales = [1.0]  # Base scale
                
                # Add upscale for small faces if frame is large enough
                if min(h, w) > 400:
                    scales.append(1.5)  # Upscale to detect small faces
                if min(h, w) > 600:
                    scales.append(0.5)  # Downscale for very large faces
                
                for scale in scales:
                    if scale == 1.0:
                        scaled_frame = frame
                        sh, sw = h, w
                    else:
                        sw, sh = int(w * scale), int(h * scale)
                        scaled_frame = cv2.resize(frame, (sw, sh), interpolation=cv2.INTER_LINEAR)
                    
                    # Create detector for this scale
                    face_detector = cv2.FaceDetectorYN.create(YUNET_PATH, "", (sw, sh))
                    face_detector.setScoreThreshold(0.6)  # Lower threshold for better recall
                    
                    # Detect faces
                    retval, faces = face_detector.detect(scaled_frame)
                    
                    if faces is not None:
                        for face in faces:
                            # Scale back coordinates to original frame size
                            if scale != 1.0:
                                face_scaled = face.copy()
                                face_scaled[0:4] = face_scaled[0:4] / scale  # x, y, w, h
                                face_scaled[4:14] = face_scaled[4:14] / scale  # landmarks
                                all_faces.append(face_scaled)
                            else:
                                all_faces.append(face)
                
                # Remove duplicate detections (NMS-like)
                faces = non_max_suppression_faces(all_faces, iou_threshold=0.4) if all_faces else None
                
                if faces is not None and len(faces) > 0:
                    for face in faces:
                        # Convert to numpy array if needed
                        face = np.array(face) if not isinstance(face, np.ndarray) else face
                        # Face format: x1, y1, w, h, x_re, y_re, x_le, y_le, x_nt, y_nt, x_rcm, y_rcm, x_lcm, y_lcm, score
                        box = face[0:4].astype(np.int32)
                        score = float(face[-1])
                        
                        # Extract face embedding using SFace (if available)
                        embedding_list = None
                        if FACE_RECOGNITION_AVAILABLE and face_recognizer is not None:
                            try:
                                # Crop and align face for embedding
                                face_aligned = face_recognizer.alignCrop(frame, face)
                                embedding = face_recognizer.feature(face_aligned)
                                embedding_list = embedding.flatten().tolist()
                            except Exception as emb_err:
                                print(f"⚠️ Embedding error: {emb_err}")
                        
                        # Crop face image for storage
                        face_crop = None
                        face_image_base64 = None
                        should_save = np.random.rand() < 0.3  # Save 30% of faces
                        try:
                            x, y, fw, fh = box
                            # Add margin
                            margin = int(min(fw, fh) * 0.2)
                            x1 = max(0, x - margin)
                            y1 = max(0, y - margin)
                            x2 = min(w, x + fw + margin)
                            y2 = min(h, y + fh + margin)
                            face_crop = frame[y1:y2, x1:x2]
                            
                            # Encode as base64 for sending to backend
                            if should_save and face_crop is not None and face_crop.size > 0:
                                _, buffer = cv2.imencode('.jpg', face_crop, [cv2.IMWRITE_JPEG_QUALITY, 80])
                                face_image_base64 = base64.b64encode(buffer).decode('utf-8')
                                print(f"📸 Face cropped for saving (size: {face_crop.shape})")
                        except Exception as crop_err:
                            print(f"⚠️ Face crop error: {crop_err}")
                        
                        # Draw minimal face detection (corners only for speed)
                        x, y, fw, fh = box
                        x1, y1, x2, y2 = x, y, x + fw, y + fh
                        
                        # Color for faces (magenta/pink)
                        face_color = (200, 100, 220)  # BGR
                        
                        # Ultra-thin for speed
                        thickness = 1
                        arc_len = min(fw, fh) // 5
                        arc_len = max(8, min(arc_len, 25))
                        
                        # Only corners - no ellipses for maximum speed
                        cv2.line(annotated_frame, (x1, y1), (x1 + arc_len, y1), face_color, thickness)
                        cv2.line(annotated_frame, (x1, y1), (x1, y1 + arc_len), face_color, thickness)
                        
                        cv2.line(annotated_frame, (x2 - arc_len, y1), (x2, y1), face_color, thickness)
                        cv2.line(annotated_frame, (x2, y1), (x2, y1 + arc_len), face_color, thickness)
                        
                        cv2.line(annotated_frame, (x1, y2 - arc_len), (x1, y2), face_color, thickness)
                        cv2.line(annotated_frame, (x1, y2), (x1 + arc_len, y2), face_color, thickness)
                        
                        cv2.line(annotated_frame, (x2, y2 - arc_len), (x2, y2), face_color, thickness)
                        cv2.line(annotated_frame, (x2 - arc_len, y2), (x2, y2), face_color, thickness)
                        
                        # Minimal label - class name only, no overlay background
                        label = "Face"
                        font = cv2.FONT_HERSHEY_SIMPLEX
                        (tw, th), _ = cv2.getTextSize(label, font, 0.4, 1)
                        label_y = y1 - 6 if y1 > 20 else y2 + th + 10
                        cv2.putText(annotated_frame, label, (x1, label_y), font, 0.4, face_color, 1, cv2.LINE_AA)
                        
                        # Publish Face Event
                        event_obj = { 
                            'camera_id': int(camera_id), 
                            'event': 'face_detected', 
                            'payload': { 
                                'label': 'Face', 
                                'score': float(score), 
                                'bbox': box.tolist(),
                                'has_embedding': embedding_list is not None
                            } 
                        }
                        r.publish('detections', json.dumps(event_obj))
                        
                        # Send face detection to backend for storage
                        backend_url = os.environ.get('BACKEND_API_URL', 'http://localhost:8000')
                        worker_key = os.environ.get('WORKER_API_KEY')
                        
                        # Always send if we have embedding OR image
                        if worker_key and (embedding_list or face_image_base64):
                            def send_face_async(url, json_data, headers):
                                try:
                                    resp = requests.post(url, json=json_data, headers=headers, timeout=2)
                                    if resp.status_code == 201:
                                        print(f"✅ Face detection saved to backend")
                                    else:
                                        print(f"⚠️ Backend response: {resp.status_code}")
                                except Exception as e:
                                    print(f"❌ Error sending face to backend: {e}")
                            
                            face_data = {
                                'camera_id': int(camera_id),
                                'confidence': float(score),
                                'bbox': box.tolist(),
                                'embedding': embedding_list,
                                'face_image_base64': face_image_base64
                            }
                            threading.Thread(
                                target=send_face_async,
                                args=(
                                    f"{backend_url}/api/worker/face-detection",
                                    face_data,
                                    {'X-WORKER-KEY': worker_key, 'Content-Type': 'application/json'}
                                )
                            ).start()
                            
            except Exception as e:
                print(f"⚠️ Face detection error: {e}")

        with global_state['lock']:
            stream = global_state['streams'].get(str(camera_id))
            if stream is not None:
                stream['current_frame'] = annotated_frame.copy()

        # Publicar detecciones en Redis y al Backend
        try:
            for det in detections:
                try:
                    payload = { 
                        'label': det.class_name, 
                        'score': det.confidence, 
                        'bbox': list(det.bbox)
                    }
                    if det.track_id is not None:
                        payload['track_id'] = det.track_id
                    
                    event_obj = { 'camera_id': int(camera_id), 'event': det.class_name, 'payload': payload }
                    # Publish on Redis channel
                    r.publish('detections', json.dumps(event_obj))
                    # Send to backend worker endpoint (Throttled)
                    backend_url = os.environ.get('BACKEND_API_URL', 'http://localhost:8000')
                    worker_key = os.environ.get('WORKER_API_KEY')
                    
                    # Simple throttling: only send if random < 0.1 (approx 10% of detections)
                    # Or better: use a timestamp per camera. For now, random is easiest to unblock.
                    if worker_key and np.random.rand() < 0.1:
                        def send_async(url, json_data, headers):
                            try:
                                requests.post(url, json=json_data, headers=headers, timeout=1)
                            except:
                                pass # Fire and forget
                        
                        threading.Thread(target=send_async, args=(f"{backend_url}/api/worker/detections", event_obj, {'X-WORKER-KEY': worker_key, 'Content-Type': 'application/json'})).start()

                except Exception as e:
                    print(f"⚠️ Error procesando detección: {e}")
        except Exception as e:
            print(f"⚠️ Error generando detecciones: {e}")

def redis_listener_loop():
    print("👂 Escuchando Redis 'video_control'...")
    pubsub = r.pubsub()
    pubsub.subscribe('video_control')

    for message in pubsub.listen():
        if message['type'] == 'message':
            try:
                # Laravel a veces manda el mensaje como string JSON puro
                data = json.loads(message['data'])
                print(f"📩 Mensaje recibido: {data}")
                
                action = data.get('action')
                if action == 'START':
                    cam_id = str(data.get('camera_id'))
                    url = data.get('url')
                    detection_classes = data.get('detection_classes', []) # List of class names
                    face_enabled = data.get('face_recognition_enabled', False)
                    depth_enabled = data.get('depth_enabled', False)
                    bev_enabled = data.get('bev_enabled', False)
                    tracking_enabled = data.get('tracking', False)  # Tracking option
                    
                    print(f"🎯 Config - Classes: {len(detection_classes) if detection_classes else 'all'}, Face: {face_enabled}, Depth: {depth_enabled}, BEV: {bev_enabled}, Tracking: {tracking_enabled}")
                    
                    with global_state['lock']:
                        if cam_id not in global_state['streams']:
                            global_state['streams'][cam_id] = { 
                                'active': True, 
                                'url': url, 
                                'current_frame': None, 
                                'lock': threading.Lock(), 
                                'thread': None,
                                'detection_classes': detection_classes,
                                'face_enabled': face_enabled,
                                'depth_enabled': depth_enabled,
                                'bev_enabled': bev_enabled,
                                'tracking_enabled': tracking_enabled
                            }
                        else:
                            global_state['streams'][cam_id]['active'] = True
                            global_state['streams'][cam_id]['url'] = url
                            global_state['streams'][cam_id]['detection_classes'] = detection_classes
                            global_state['streams'][cam_id]['face_enabled'] = face_enabled
                            global_state['streams'][cam_id]['depth_enabled'] = depth_enabled
                            global_state['streams'][cam_id]['bev_enabled'] = bev_enabled
                            global_state['streams'][cam_id]['tracking_enabled'] = tracking_enabled
                        
                        # Launch thread if missing
                        if not global_state['streams'][cam_id].get('thread'):
                            t = threading.Thread(target=stream_thread, args=(cam_id, url), daemon=True)
                            global_state['streams'][cam_id]['thread'] = t
                            t.start()
                    # Allow workers to send a model name (eg. 'yolov8n' or 'yolov8n.pt')
                    model_name = data.get('model')
                    if model_name:
                        try:
                            # Only reload if model name is different from current
                            current_model_name = model.ckpt_path if hasattr(model, 'ckpt_path') else ''
                            # Simple check: if we don't have a way to check name easily, we just reload.
                            # But reloading global model while other threads use it is risky.
                            # For now, we will only load if it's not loaded or we want to force it.
                            # Better approach: Use a lock for model inference or per-thread model.
                            # Given the "last camera works" issue, let's avoid reloading if possible.
                            print(f"⚙️ Loading model requested: {model_name}")
                            # global model
                            # model = YOLO(f"{model_name}.pt") if not model_name.endswith('.pt') else YOLO(model_name)
                        except Exception as e:
                            print(f"⚠️ Error loading {model_name}: {e}")
                    global_state["active"] = True
                elif action == 'STOP':
                    cam_id = str(data.get('camera_id'))
                    with global_state['lock']:
                        if cam_id in global_state['streams']:
                            global_state['streams'][cam_id]['active'] = False
                            global_state['streams'][cam_id]['current_frame'] = None  # Clear frame to stop showing old data
                    print(f"🛑 Stream {cam_id} marked as stopped")
            except Exception as e:
                print(f"Error procesando mensaje Redis: {e}")

def generate_mjpeg():
    while True:
        frame = None
        with global_state["lock"]:
            if global_state["current_frame"] is not None:
                frame = global_state["current_frame"]
        
        if frame is None:
            time.sleep(0.1)
            continue

        (flag, encodedImage) = cv2.imencode(".jpg", frame)
        if not flag: continue
            
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + bytearray(encodedImage) + b'\r\n')
        time.sleep(0.04)

@app.get("/video_feed")
def video_feed(camera_id: str = None):
    # stream a specific camera_id if provided, otherwise default to first active stream
    def generator():
        while True:
            frame = None
            with global_state['lock']:
                if camera_id:
                    stream = global_state['streams'].get(str(camera_id))
                    if stream and stream.get('current_frame') is not None:
                        frame = stream['current_frame']
                else:
                    # pick first active stream
                    for s in global_state['streams'].values():
                        if s.get('current_frame') is not None:
                            frame = s['current_frame']; break
            if frame is None:
                time.sleep(0.1); continue
            (flag, encodedImage) = cv2.imencode('.jpg', frame)
            if not flag: continue
            yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + bytearray(encodedImage) + b'\r\n')
            time.sleep(0.04)
    return StreamingResponse(generator(), media_type='multipart/x-mixed-replace; boundary=frame')


@app.get('/health')
def health_check():
    """Simple health endpoint for the worker process. This returns the list of active streams and a basic OK."""
    with global_state['lock']:
        active_ids = [cam_id for cam_id, stream in global_state['streams'].items() if stream.get('active', False)]
    return { 
        'status': 'ok', 
        'active_streams': active_ids,
        'face_detection_available': os.path.exists(YUNET_PATH),
        'face_recognition_available': FACE_RECOGNITION_AVAILABLE
    }


# Face events SSE endpoint
@app.get('/events/faces')
async def face_events_sse(camera_id: int = None):
    """
    Server-Sent Events endpoint for real-time face detection updates.
    Subscribes to Redis pub/sub for face_detected events.
    """
    async def event_generator():
        pubsub = r.pubsub()
        pubsub.subscribe('detections')
        
        try:
            yield f"data: {json.dumps({'event': 'connected', 'camera_id': camera_id})}\n\n"
            
            while True:
                message = pubsub.get_message(timeout=1.0)
                if message and message['type'] == 'message':
                    try:
                        data = json.loads(message['data'])
                        # Filter for face events only
                        if data.get('event') == 'face_detected':
                            # Filter by camera if specified
                            if camera_id is None or data.get('camera_id') == camera_id:
                                yield f"data: {json.dumps(data)}\n\n"
                    except json.JSONDecodeError:
                        pass
                else:
                    # Send keepalive
                    yield f": keepalive\n\n"
                
                await asyncio.sleep(0.1)
        finally:
            pubsub.unsubscribe('detections')
            pubsub.close()
    
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        event_generator(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )


@app.get('/models')
def list_models():
    """List available detection models and their status."""
    return {
        'current_model': model.__class__.__name__,
        'available_models': ModelFactory.list_available_models(),
        'class_names': class_names
    }


@app.get('/models/info')
def model_info():
    """Get detailed info about the currently loaded model."""
    return {
        'name': model.__class__.__name__,
        'is_loaded': model.is_loaded,
        'device': getattr(model, '_device', 'unknown'),
        'total_classes': len(class_names)
    }


# --- Model Export Service ---
from .export_model import (
    export_yolo_nas, 
    get_export_status, 
    list_models as list_export_models,
    check_onnx_model,
    get_available_models
)

# Export task running in background
_export_task = None
_export_lock = threading.Lock()


@app.get('/models/export/available')
def models_export_available():
    """List available models for export and installed ONNX models."""
    return list_export_models()


@app.get('/models/export/status')
def models_export_status():
    """Get current export status."""
    status = get_export_status()
    with _export_lock:
        status['task_running'] = _export_task is not None and _export_task.is_alive()
    return status


@app.post('/models/export/start')
def models_export_start(data: dict):
    """
    Start exporting a YOLO-NAS model to ONNX format.
    
    Expects:
        {
            "model_type": "yolo_nas_s",  // or yolo_nas_m, yolo_nas_l
            "input_size": 640            // 320, 416, 512, or 640
        }
    """
    global _export_task
    
    model_type = data.get('model_type', 'yolo_nas_s')
    input_size = data.get('input_size', 640)
    
    # Validate params
    if model_type not in ['yolo_nas_s', 'yolo_nas_m', 'yolo_nas_l']:
        return {"error": f"Invalid model_type: {model_type}", "success": False}
    
    if input_size not in [320, 416, 512, 640]:
        return {"error": f"Invalid input_size: {input_size}", "success": False}
    
    with _export_lock:
        if _export_task is not None and _export_task.is_alive():
            return {"error": "Export already in progress", "success": False}
        
        # Check if model already exists
        existing = check_onnx_model(model_type)
        if existing.get('exists'):
            return {
                "warning": f"Model {model_type}.onnx already exists ({existing['size_mb']} MB)",
                "existing": existing,
                "message": "Use force=true to overwrite"
            }
        
        # Start export in background thread
        def run_export():
            try:
                export_yolo_nas(model_type, input_size)
            except Exception as e:
                print(f"❌ Export thread error: {e}")
        
        _export_task = threading.Thread(target=run_export, daemon=True)
        _export_task.start()
        
        return {
            "success": True,
            "message": f"Started export of {model_type} with input size {input_size}",
            "status_url": "/models/export/status"
        }


@app.post('/models/export/force')
def models_export_force(data: dict):
    """
    Force export (overwrite existing model).
    
    Expects:
        {
            "model_type": "yolo_nas_s",
            "input_size": 640
        }
    """
    global _export_task
    
    model_type = data.get('model_type', 'yolo_nas_s')
    input_size = data.get('input_size', 640)
    
    with _export_lock:
        if _export_task is not None and _export_task.is_alive():
            return {"error": "Export already in progress", "success": False}
        
        # Delete existing model if present
        onnx_path = os.path.join(MODELS_DIR, f"{model_type}.onnx")
        if os.path.exists(onnx_path):
            os.remove(onnx_path)
            print(f"🗑️ Removed existing model: {onnx_path}")
        
        def run_export():
            try:
                export_yolo_nas(model_type, input_size)
            except Exception as e:
                print(f"❌ Export thread error: {e}")
        
        _export_task = threading.Thread(target=run_export, daemon=True)
        _export_task.start()
        
        return {
            "success": True,
            "message": f"Started forced export of {model_type}",
            "status_url": "/models/export/status"
        }


@app.post('/models/reload')
def models_reload():
    """
    Reload detection model (useful after exporting new ONNX model).
    """
    global model, class_names
    
    try:
        print("🔄 Reloading detection model...")
        new_model = get_detector()
        
        if new_model and new_model.is_loaded:
            model = new_model
            class_names = getattr(model, 'class_names', [])
            return {
                "success": True,
                "model": model.__class__.__name__,
                "message": "Model reloaded successfully"
            }
        else:
            return {
                "success": False,
                "error": "Failed to load new model"
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# --- Satellite Service ---
satellite_service = get_satellite_service()

@app.get('/satellite/status')
def satellite_status():
    """Check satellite service availability."""
    return {
        'available': satellite_service.is_available(),
        'configured': satellite_service.config.is_configured()
    }


@app.post('/satellite/analyze')
def satellite_analyze(zone_data: dict):
    """
    Analyze a satellite zone by downloading image and running detection.
    
    Expects:
        {
            "zone_id": 1,
            "lat": -32.94,
            "lon": -60.63,
            "km_radius": 1.0,
            "user_id": 1
        }
    """
    if not satellite_service.is_available():
        return {"error": "Satellite service not configured", "status": "error"}
    
    try:
        lat = zone_data.get('lat')
        lon = zone_data.get('lon')
        km_radius = zone_data.get('km_radius', 1.0)
        zone_id = zone_data.get('zone_id')
        user_id = zone_data.get('user_id')
        
        print(f"🛰️ Analyzing satellite zone {zone_id} at ({lat}, {lon})")
        
        # Download satellite image
        image = satellite_service.get_latest_image(lat, lon, km_radius)
        
        if image is None:
            return {"error": "Failed to download satellite image", "status": "error"}
        
        # Run detection on satellite image
        detections = model.detect(image)
        
        # Prepare results
        detection_results = []
        for det in detections:
            detection_results.append({
                'class_name': det.class_name,
                'confidence': det.confidence,
                'bbox': list(det.bbox)
            })
        
        # --- VLM Analysis (if enabled) ---
        vlm_analysis = None
        enable_vlm = zone_data.get('enable_vlm', VLM_ENABLED)
        vlm_prompt = zone_data.get('vlm_prompt', VLMPrompts.SATELLITE_GENERAL)
        
        if enable_vlm and VLM_ENABLED:
            global vlm_analyzer
            try:
                if vlm_analyzer is None:
                    print("🧠 Loading VLM for satellite analysis...")
                    vlm_analyzer = init_vlm_analyzer()
                
                if vlm_analyzer.available:
                    vlm_result = vlm_analyzer.analyze_image(image, vlm_prompt)
                    if vlm_result["success"]:
                        vlm_analysis = vlm_result["answer"]
                        print(f"🤖 VLM: {vlm_analysis[:100]}...")
            except Exception as e:
                print(f"⚠️ VLM analysis skipped: {e}")
        
        # Encode image to base64 for storage
        _, img_encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 85])
        image_base64 = base64.b64encode(img_encoded).decode('utf-8')
        
        # Notify backend via HTTP
        backend_url = os.environ.get('BACKEND_API_URL', 'http://localhost:8000')
        worker_key = os.environ.get('WORKER_API_KEY')
        
        result = {
            'zone_id': zone_id,
            'user_id': user_id,
            'detections': detection_results,
            'image_base64': image_base64,
            'vlm_analysis': vlm_analysis,  # VLM interpretation
            'cloud_cover': 0.0,  # TODO: get from API response
            'captured_at': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        if worker_key:
            try:
                resp = requests.post(
                    f"{backend_url}/api/worker/satellite-result",
                    json=result,
                    headers={'X-WORKER-KEY': worker_key, 'Content-Type': 'application/json'},
                    timeout=10
                )
                print(f"📡 Backend notified: {resp.status_code}")
            except Exception as e:
                print(f"⚠️ Error notifying backend: {e}")
        
        # Publish on Redis
        r.publish('satellite_results', json.dumps({
            'zone_id': zone_id,
            'detections_count': len(detection_results),
            'vlm_analysis': vlm_analysis,
            'status': 'completed'
        }))
        
        return {
            'status': 'success',
            'zone_id': zone_id,
            'detections_count': len(detection_results),
            'detections': detection_results,
            'vlm_analysis': vlm_analysis
        }
        
    except Exception as e:
        print(f"❌ Satellite analysis error: {e}")
        return {"error": str(e), "status": "error"}


# --- VLM (Moondream) Endpoints ---

class VLMAnalyzeRequest(BaseModel):
    """Request body for VLM analysis"""
    image_base64: str
    question: str = "Describe this image in detail."
    questions: Optional[List[str]] = None


@app.get('/vlm/status')
def vlm_status():
    """Check VLM (Moondream) availability and status."""
    global vlm_analyzer
    
    return {
        'enabled': VLM_ENABLED,
        'loaded': vlm_analyzer is not None and vlm_analyzer.available,
        'model': 'vikhyatk/moondream2',
        'prompts': {
            'satellite_general': VLMPrompts.SATELLITE_GENERAL,
            'satellite_flood': VLMPrompts.SATELLITE_FLOOD,
            'security_scene': VLMPrompts.SECURITY_SCENE
        }
    }


@app.post('/vlm/analyze')
def vlm_analyze(request: VLMAnalyzeRequest):
    """
    Analyze an image using Moondream VLM.
    
    Expects:
        {
            "image_base64": "base64_encoded_image",
            "question": "What do you see in this image?",
            "questions": ["Question 1", "Question 2"]  // Optional: for batch
        }
    
    Returns:
        {
            "success": true,
            "answer": "description...",
            "answers": ["answer1", "answer2"]  // If batch
        }
    """
    global vlm_analyzer
    
    if not VLM_ENABLED:
        return {"success": False, "error": "VLM is disabled. Set ENABLE_VLM=true"}
    
    try:
        # Lazy load VLM on first use (saves ~2GB RAM at startup)
        if vlm_analyzer is None:
            print("🧠 Loading VLM (first use)...")
            vlm_analyzer = init_vlm_analyzer()
        
        if not vlm_analyzer.available:
            return {"success": False, "error": "VLM failed to initialize"}
        
        # Decode image from base64
        img_data = base64.b64decode(request.image_base64)
        img_array = np.frombuffer(img_data, dtype=np.uint8)
        image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        
        if image is None:
            return {"success": False, "error": "Invalid image data"}
        
        # Batch or single question
        if request.questions:
            result = vlm_analyzer.batch_analyze(image, request.questions)
            return {
                "success": result["success"],
                "answers": result.get("answers", []),
                "error": result.get("error")
            }
        else:
            result = vlm_analyzer.analyze_image(image, request.question)
            return {
                "success": result["success"],
                "answer": result.get("answer"),
                "error": result.get("error")
            }
            
    except Exception as e:
        print(f"❌ VLM analysis error: {e}")
        return {"success": False, "error": str(e)}


@app.post('/vlm/validate-detection')
def vlm_validate_detection(data: dict):
    """
    Validate YOLO detections using VLM.
    Useful for reducing false positives.
    
    Expects:
        {
            "image_base64": "base64_encoded_image",
            "detected_objects": ["person", "car", "truck"],
            "context_prompt": "Is this a construction site?" // Optional
        }
    """
    global vlm_analyzer
    
    if not VLM_ENABLED:
        return {"success": False, "error": "VLM is disabled"}
    
    try:
        if vlm_analyzer is None:
            vlm_analyzer = init_vlm_analyzer()
        
        if not vlm_analyzer.available:
            return {"success": False, "error": "VLM not available"}
        
        # Decode image
        img_data = base64.b64decode(data.get('image_base64', ''))
        img_array = np.frombuffer(img_data, dtype=np.uint8)
        image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        
        if image is None:
            return {"success": False, "error": "Invalid image"}
        
        detected_objects = data.get('detected_objects', [])
        context_prompt = data.get('context_prompt')
        
        result = vlm_analyzer.validate_detection(image, detected_objects, context_prompt)
        return result
        
    except Exception as e:
        print(f"❌ VLM validation error: {e}")
        return {"success": False, "error": str(e)}


@app.post('/vlm/analyze-camera-snapshot')
def vlm_analyze_camera_snapshot(data: dict):
    """
    Analyze current snapshot from an active camera stream using VLM.
    
    Expects:
        {
            "camera_id": 1,
            "question": "What is happening in this scene?"
        }
    """
    global vlm_analyzer
    
    if not VLM_ENABLED:
        return {"success": False, "error": "VLM is disabled"}
    
    camera_id = str(data.get('camera_id'))
    question = data.get('question', VLMPrompts.SECURITY_SCENE)
    
    with global_state['lock']:
        stream = global_state['streams'].get(camera_id)
        if not stream or not stream.get('active'):
            return {"success": False, "error": f"Camera {camera_id} not active"}
        
        with stream['lock']:
            frame = stream.get('current_frame')
    
    if frame is None:
        return {"success": False, "error": "No frame available"}
    
    try:
        if vlm_analyzer is None:
            vlm_analyzer = init_vlm_analyzer()
        
        result = vlm_analyzer.analyze_image(frame, question)
        return {
            "success": result["success"],
            "camera_id": camera_id,
            "answer": result.get("answer"),
            "error": result.get("error")
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


# --- Hybrid Analysis Endpoints (YOLO + VLM) ---

@app.get('/hybrid/status')
def hybrid_status():
    """Check hybrid analyzer (YOLO + VLM) status."""
    global hybrid_analyzer, vlm_analyzer
    
    return {
        'available': True,
        'detector_loaded': model is not None,
        'vlm_enabled': VLM_ENABLED,
        'vlm_loaded': vlm_analyzer is not None and vlm_analyzer.available,
        'hybrid_initialized': hybrid_analyzer is not None
    }


@app.post('/hybrid/detect-and-validate')
def hybrid_detect_and_validate(data: dict):
    """
    Detect objects with YOLO and validate with VLM.
    Reduces false positives by cross-checking detections.
    
    Expects:
        {
            "image_base64": "...",
            "validate_with_vlm": true,
            "confidence_threshold": 0.5
        }
    """
    global hybrid_analyzer, vlm_analyzer
    
    try:
        # Lazy init hybrid analyzer
        if hybrid_analyzer is None:
            if vlm_analyzer is None and VLM_ENABLED:
                vlm_analyzer = init_vlm_analyzer()
            hybrid_analyzer = init_hybrid_analyzer(detector=model, vlm=vlm_analyzer)
        else:
            # Ensure components are set
            if hybrid_analyzer.detector is None:
                hybrid_analyzer.set_detector(model)
            if hybrid_analyzer.vlm is None and vlm_analyzer:
                hybrid_analyzer.set_vlm(vlm_analyzer)
        
        # Decode image
        img_data = base64.b64decode(data.get('image_base64', ''))
        img_array = np.frombuffer(img_data, dtype=np.uint8)
        image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        
        if image is None:
            return {"success": False, "error": "Invalid image data"}
        
        validate = data.get('validate_with_vlm', VLM_ENABLED)
        threshold = data.get('confidence_threshold', 0.5)
        
        result = hybrid_analyzer.detect_and_validate(
            image,
            validate_with_vlm=validate,
            confidence_threshold=threshold
        )
        
        return {
            "success": True,
            **result
        }
        
    except Exception as e:
        print(f"❌ Hybrid detect error: {e}")
        return {"success": False, "error": str(e)}


@app.post('/hybrid/smart-alert')
def hybrid_smart_alert(data: dict):
    """
    Generate a smart alert with VLM context.
    
    Expects:
        {
            "image_base64": "...",
            "detections": [...],
            "alert_type": "person_in_restricted",
            "camera_id": 1
        }
    """
    global hybrid_analyzer, vlm_analyzer
    
    try:
        if hybrid_analyzer is None:
            if vlm_analyzer is None and VLM_ENABLED:
                vlm_analyzer = init_vlm_analyzer()
            hybrid_analyzer = init_hybrid_analyzer(detector=model, vlm=vlm_analyzer)
        
        # Decode image
        img_data = base64.b64decode(data.get('image_base64', ''))
        img_array = np.frombuffer(img_data, dtype=np.uint8)
        image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        
        if image is None:
            return {"success": False, "error": "Invalid image data"}
        
        detections = data.get('detections', [])
        alert_type = data.get('alert_type', 'general')
        camera_id = data.get('camera_id')
        zone_id = data.get('zone_id')
        
        alert = hybrid_analyzer.generate_smart_alert(
            image,
            detections,
            alert_type=alert_type,
            camera_id=camera_id,
            zone_id=zone_id
        )
        
        if alert:
            return {
                "success": True,
                "alert": alert.to_dict()
            }
        else:
            return {
                "success": True,
                "alert": None,
                "message": "No alert generated (conditions not met)"
            }
        
    except Exception as e:
        print(f"❌ Smart alert error: {e}")
        return {"success": False, "error": str(e)}


@app.post('/hybrid/analyze-satellite-zone')
def hybrid_analyze_satellite_zone(data: dict):
    """
    Comprehensive satellite zone analysis combining detection and VLM.
    
    Expects:
        {
            "image_base64": "...",
            "zone_id": 1,
            "analysis_type": "general"  # general, flood, construction, deforestation, agriculture
        }
    """
    global hybrid_analyzer, vlm_analyzer
    
    try:
        if hybrid_analyzer is None:
            if vlm_analyzer is None and VLM_ENABLED:
                vlm_analyzer = init_vlm_analyzer()
            hybrid_analyzer = init_hybrid_analyzer(detector=model, vlm=vlm_analyzer)
        
        # Decode image
        img_data = base64.b64decode(data.get('image_base64', ''))
        img_array = np.frombuffer(img_data, dtype=np.uint8)
        image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        
        if image is None:
            return {"success": False, "error": "Invalid image data"}
        
        zone_id = data.get('zone_id', 0)
        analysis_type = data.get('analysis_type', 'general')
        
        result = hybrid_analyzer.analyze_satellite_zone(
            image,
            zone_id=zone_id,
            analysis_type=analysis_type
        )
        
        return {
            "success": True,
            **result
        }
        
    except Exception as e:
        print(f"❌ Satellite zone analysis error: {e}")
        return {"success": False, "error": str(e)}


def satellite_listener_loop():
    """Listen for satellite analysis commands on Redis."""
    print("🛰️ Escuchando Redis 'satellite_control'...")
    pubsub = r.pubsub()
    pubsub.subscribe('satellite_control')
    
    for message in pubsub.listen():
        if message['type'] == 'message':
            try:
                data = json.loads(message['data'])
                print(f"🛰️ Satellite message: {data}")
                
                action = data.get('action')
                if action == 'ANALYZE':
                    # Run analysis in a separate thread to not block listener
                    threading.Thread(
                        target=satellite_analyze,
                        args=(data,),
                        daemon=True
                    ).start()
                    
            except Exception as e:
                print(f"Error procesando mensaje satellite: {e}")


@app.on_event("startup")
def startup_event():
    # Start the Redis listener thread on startup
    threading.Thread(target=redis_listener_loop, daemon=True).start()
    # Start the Satellite Redis listener thread
    threading.Thread(target=satellite_listener_loop, daemon=True).start()


# ============================================================================
# IMAGE COMPARISON ENDPOINTS (for satellite monitoring)
# ============================================================================

@app.get('/comparison/status')
def comparison_status():
    """Get status of image comparison service."""
    comparator = get_comparator()
    return {
        "available": comparator is not None,
        "min_contour_area": comparator.min_contour_area if comparator else None,
        "blur_kernel": comparator.blur_kernel if comparator else None
    }


@app.post('/comparison/compare')
def compare_satellite_images(data: dict):
    """
    Compare two satellite images and detect changes.
    
    Expects:
        {
            "image_previous_base64": "...",  # Previous/baseline image
            "image_current_base64": "...",   # Current/new image
            "threshold": 30,                 # Optional: pixel diff threshold
            "generate_visuals": true         # Optional: generate visualization images
        }
    
    Returns:
        {
            "success": true,
            "overall_change_percent": 15.5,
            "ssim_score": 0.85,
            "histogram_correlation": 0.92,
            "pixel_diff_percent": 12.3,
            "severity": "moderate",
            "suggested_change_type": "construction",
            "change_regions": [...],
            "recommendations": [...],
            "diff_image_base64": "...",
            "heatmap_base64": "...",
            "overlay_base64": "..."
        }
    """
    try:
        img_prev_b64 = data.get('image_previous_base64')
        img_curr_b64 = data.get('image_current_base64')
        
        if not img_prev_b64 or not img_curr_b64:
            return {"success": False, "error": "Both images are required"}
        
        threshold = data.get('threshold', 30)
        generate_visuals = data.get('generate_visuals', True)
        
        # Run comparison
        result = compare_images_from_base64(
            img_prev_b64, 
            img_curr_b64,
            threshold=threshold,
            generate_visuals=generate_visuals
        )
        
        # Convert result to dict for JSON serialization
        return {
            "success": True,
            "overall_change_percent": result.overall_change_percent,
            "ssim_score": result.ssim_score,
            "histogram_correlation": result.histogram_correlation,
            "pixel_diff_percent": result.pixel_diff_percent,
            "severity": result.severity.value,
            "suggested_change_type": result.suggested_change_type.value,
            "change_regions": [
                {
                    "x": r.x, "y": r.y, "width": r.width, "height": r.height,
                    "area": r.area, "change_percent": r.change_percent,
                    "centroid": r.centroid
                }
                for r in result.change_regions
            ],
            "recommendations": result.recommendations,
            "diff_image_base64": result.diff_image_base64,
            "heatmap_base64": result.heatmap_base64,
            "overlay_base64": result.overlay_base64,
            "analysis_timestamp": result.analysis_timestamp
        }
        
    except Exception as e:
        print(f"❌ Image comparison error: {e}")
        return {"success": False, "error": str(e)}


@app.post('/comparison/analyze-with-suggestions')
def compare_with_ai_suggestions(data: dict):
    """
    Compare images and get AI-powered suggestions using VLM.
    
    Expects:
        {
            "image_previous_base64": "...",
            "image_current_base64": "...",
            "zone_name": "Zone A",
            "use_vlm": true  # Whether to use VLM for detailed analysis
        }
    
    Returns comparison results + VLM interpretation if requested.
    """
    global vlm_analyzer
    
    try:
        img_prev_b64 = data.get('image_previous_base64')
        img_curr_b64 = data.get('image_current_base64')
        zone_name = data.get('zone_name', 'Unknown Zone')
        use_vlm = data.get('use_vlm', False)
        
        if not img_prev_b64 or not img_curr_b64:
            return {"success": False, "error": "Both images are required"}
        
        # First, run basic comparison
        result = compare_images_from_base64(img_prev_b64, img_curr_b64)
        
        response = {
            "success": True,
            "zone_name": zone_name,
            "comparison": {
                "overall_change_percent": result.overall_change_percent,
                "severity": result.severity.value,
                "suggested_change_type": result.suggested_change_type.value,
                "change_regions_count": len(result.change_regions),
                "recommendations": result.recommendations,
                "heatmap_base64": result.heatmap_base64,
                "overlay_base64": result.overlay_base64
            }
        }
        
        # If significant change and VLM requested, get detailed analysis
        if use_vlm and result.overall_change_percent > 5:
            if vlm_analyzer is None and VLM_ENABLED:
                vlm_analyzer = init_vlm_analyzer()
            
            if vlm_analyzer:
                # Decode current image for VLM
                img_data = base64.b64decode(img_curr_b64)
                img_array = np.frombuffer(img_data, dtype=np.uint8)
                current_image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                
                # Ask VLM about the changes
                change_prompt = f"""This satellite image shows an area that has changed by approximately {result.overall_change_percent:.1f}%.
The automated analysis suggests this might be related to {result.suggested_change_type.value}.
Please describe what you see in detail and confirm or refine this assessment.
What specific changes can you identify? Are there any potential concerns?"""
                
                vlm_analysis = vlm_analyzer.analyze_image(current_image, change_prompt)
                
                response["vlm_analysis"] = {
                    "detailed_interpretation": vlm_analysis,
                    "model": "moondream2",
                    "prompt_used": change_prompt
                }
        
        # Generate notification recommendation
        should_notify = (
            result.severity.value in ['significant', 'critical'] or
            result.overall_change_percent > 20
        )
        
        response["notification"] = {
            "should_notify": should_notify,
            "priority": "high" if result.severity.value == 'critical' else 
                       "medium" if result.severity.value == 'significant' else "low",
            "summary": f"Zona '{zone_name}': {result.overall_change_percent:.1f}% de cambio detectado ({result.severity.value})"
        }
        
        return response
        
    except Exception as e:
        print(f"❌ Compare with suggestions error: {e}")
        return {"success": False, "error": str(e)}


@app.post('/comparison/quick-diff')
def quick_diff_check(data: dict):
    """
    Quick check if images are significantly different (for polling).
    
    Expects:
        {
            "image_previous_base64": "...",
            "image_current_base64": "...",
            "change_threshold": 10.0  # Minimum % to consider "changed"
        }
    
    Returns:
        {
            "has_changes": true/false,
            "change_percent": 15.5,
            "severity": "moderate"
        }
    """
    try:
        img_prev_b64 = data.get('image_previous_base64')
        img_curr_b64 = data.get('image_current_base64')
        change_threshold = data.get('change_threshold', 10.0)
        
        if not img_prev_b64 or not img_curr_b64:
            return {"success": False, "error": "Both images are required"}
        
        # Quick comparison without visuals
        result = compare_images_from_base64(
            img_prev_b64, 
            img_curr_b64,
            generate_visuals=False
        )
        
        return {
            "success": True,
            "has_changes": result.overall_change_percent >= change_threshold,
            "change_percent": result.overall_change_percent,
            "severity": result.severity.value
        }
        
    except Exception as e:
        print(f"❌ Quick diff error: {e}")
        return {"success": False, "error": str(e)}
