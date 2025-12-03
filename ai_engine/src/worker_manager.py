import os
import json
import time
import threading
import base64
import cv2
import redis
import numpy as np
import requests
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from yt_dlp import YoutubeDL
from .depth_service import DepthService
from .models import get_detector, ModelFactory

app = FastAPI()

# --- Model Management ---
MODELS_DIR = os.path.join(os.path.dirname(__file__), "../models")
os.makedirs(MODELS_DIR, exist_ok=True)

YUNET_PATH = os.path.join(MODELS_DIR, "face_detection_yunet_2023mar.onnx")
SFACE_PATH = os.path.join(MODELS_DIR, "face_recognition_sface_2021dec.onnx")

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

# Get detector from environment (default: YOLO-NAS)
# Set DETECTION_MODEL env var to change: 'yolo_nas', 'rt_detr', or 'ultralytics'
try:
    model = get_detector()
    model.load_model()
    class_names = model.get_class_names()
    print(f"✅ Modelo {model.__class__.__name__} cargado correctamente.")
except Exception as e:
    print(f"❌ Error cargando modelo: {e}")
    print("⚠️ Intentando cargar modelo de respaldo YOLO-NAS...")
    from .models.yolo_nas import YOLONASDetector
    model = YOLONASDetector()
    model.load_model()
    class_names = model.get_class_names()
    print("✅ Modelo de respaldo cargado.")

# 1. MEJORA: Forzamos formato compatible con OpenCV
def get_stream_url(youtube_url):
    try:
        # Pedimos explícitamente MP4 y video+audio combinados o el mejor compatible
        ydl_opts = {
            'format': 'best[ext=mp4]/best', 
            'quiet': True,
            'force_generic_extractor': False
        }
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            return info['url']
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
        if face_enabled and os.path.exists(YUNET_PATH):
            try:
                h, w, _ = frame.shape
                # Instantiate detector for current frame size
                face_detector = cv2.FaceDetectorYN.create(YUNET_PATH, "", (w, h))
                
                # Detect
                retval, faces = face_detector.detect(frame)
                if faces is not None:
                    for face in faces:
                        # Face format: x1, y1, w, h, x_re, y_re, x_le, y_le, x_nt, y_nt, x_rcm, y_rcm, x_lcm, y_lcm, score
                        box = face[0:4].astype(np.int32)
                        score = face[-1]
                        
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
                        
                        # Draw modern face detection (corner arcs style)
                        x, y, fw, fh = box
                        x1, y1, x2, y2 = x, y, x + fw, y + fh
                        
                        # Platform color for faces (magenta/pink tones)
                        face_color = (200, 100, 220)  # BGR - pinkish
                        
                        # Corner arc length
                        arc_len = min(fw, fh) // 4
                        arc_len = max(12, min(arc_len, 35))
                        thickness = 2
                        
                        # Draw corner arcs
                        cv2.line(annotated_frame, (x1, y1), (x1 + arc_len, y1), face_color, thickness)
                        cv2.line(annotated_frame, (x1, y1), (x1, y1 + arc_len), face_color, thickness)
                        cv2.ellipse(annotated_frame, (x1 + 6, y1 + 6), (6, 6), 180, 0, 90, face_color, thickness)
                        
                        cv2.line(annotated_frame, (x2 - arc_len, y1), (x2, y1), face_color, thickness)
                        cv2.line(annotated_frame, (x2, y1), (x2, y1 + arc_len), face_color, thickness)
                        cv2.ellipse(annotated_frame, (x2 - 6, y1 + 6), (6, 6), 270, 0, 90, face_color, thickness)
                        
                        cv2.line(annotated_frame, (x1, y2 - arc_len), (x1, y2), face_color, thickness)
                        cv2.line(annotated_frame, (x1, y2), (x1 + arc_len, y2), face_color, thickness)
                        cv2.ellipse(annotated_frame, (x1 + 6, y2 - 6), (6, 6), 90, 0, 90, face_color, thickness)
                        
                        cv2.line(annotated_frame, (x2, y2 - arc_len), (x2, y2), face_color, thickness)
                        cv2.line(annotated_frame, (x2 - arc_len, y2), (x2, y2), face_color, thickness)
                        cv2.ellipse(annotated_frame, (x2 - 6, y2 - 6), (6, 6), 0, 0, 90, face_color, thickness)
                        
                        # Simple face label (just icon indicator, no percentage)
                        label = "Face"
                        font = cv2.FONT_HERSHEY_SIMPLEX
                        (tw, th), _ = cv2.getTextSize(label, font, 0.4, 1)
                        label_y = y1 - 6 if y1 > 20 else y2 + th + 10
                        
                        # Semi-transparent background
                        overlay = annotated_frame.copy()
                        cv2.rectangle(overlay, (x1, label_y - th - 4), (x1 + tw + 8, label_y + 4), (40, 40, 40), -1)
                        cv2.addWeighted(overlay, 0.6, annotated_frame, 0.4, 0, annotated_frame)
                        cv2.rectangle(annotated_frame, (x1, label_y - th - 4), (x1 + tw + 8, label_y + 4), face_color, 1)
                        cv2.putText(annotated_frame, label, (x1 + 4, label_y), font, 0.4, face_color, 1, cv2.LINE_AA)
                        
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


@app.on_event("startup")
def startup_event():
    # Start the Redis listener thread on startup
    threading.Thread(target=redis_listener_loop, daemon=True).start()