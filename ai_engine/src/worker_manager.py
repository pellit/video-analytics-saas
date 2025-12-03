import os
import json
import time
import threading
import cv2
import redis
import numpy as np
import requests
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from ultralytics import YOLO
from yt_dlp import YoutubeDL
from .depth_service import DepthService

app = FastAPI()

# --- Model Management ---
MODELS_DIR = os.path.join(os.path.dirname(__file__), "../models")
os.makedirs(MODELS_DIR, exist_ok=True)

YUNET_PATH = os.path.join(MODELS_DIR, "face_detection_yunet_2023mar.onnx")
SFACE_PATH = os.path.join(MODELS_DIR, "face_recognition_sface_2021dec.onnx")

# Initialize Services
depth_service = DepthService()

def download_file(url, dest):
    if os.path.exists(dest): return
    print(f"⬇️ Downloading {os.path.basename(dest)}...")
    try:
        r = requests.get(url, stream=True)
        r.raise_for_status()
        with open(dest, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"✅ Downloaded {os.path.basename(dest)}")
    except Exception as e:
        print(f"❌ Failed to download {dest}: {e}")

# Download models on import/startup
download_file("https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx", YUNET_PATH)
download_file("https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx", SFACE_PATH)

# Initialize Face Models (Lazy load or global?)
# We'll initialize detector per thread/frame size, or global if size is fixed. 
# YuNet requires input size. We'll handle it in the loop.
face_recognizer = cv2.FaceRecognizerSF.create(SFACE_PATH, "")

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

print("⏳ Cargando modelo YOLO...")
model = YOLO('yolov8n.pt')
print("✅ Modelo cargado.")

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

        # Inferencia YOLO
        classes_indices = []
        if detection_classes and hasattr(model, 'names'):
            # Map class names to indices
            for idx, cls_name in model.names.items():
                if cls_name in detection_classes:
                    classes_indices.append(idx)
        
        # Use tracking or regular detection based on config
        if tracking_enabled:
            # YOLO native tracking with BoT-SORT
            if classes_indices:
                results = model.track(frame, classes=classes_indices, verbose=False, persist=True, tracker="botsort.yaml")
            elif detection_classes and not classes_indices:
                results = model.track(frame, classes=[], verbose=False, persist=True, tracker="botsort.yaml")
            else:
                results = model.track(frame, verbose=False, persist=True, tracker="botsort.yaml")
        else:
            # Regular detection without tracking
            if classes_indices:
                results = model(frame, classes=classes_indices, verbose=False)
            elif detection_classes and not classes_indices:
                results = model(frame, classes=[], verbose=False)
            else:
                results = model(frame, verbose=False)

        # Plot results - tracking IDs are automatically shown when using track()
        annotated_frame = results[0].plot()

        # Depth / 3D Logic
        if depth_enabled:
            try:
                # Collect detections for Depth Service (including track IDs if available)
                detections_list = []
                for box in results[0].boxes:
                     label = results[0].names.get(int(box.cls), str(int(box.cls))) if results[0].names else str(int(box.cls))
                     det_item = {
                         'label': label,
                         'bbox': box.xyxy[0].tolist(),
                         'score': float(box.conf)
                     }
                     # Add track ID if tracking is enabled
                     if tracking_enabled and hasattr(box, 'id') and box.id is not None:
                         det_item['track_id'] = int(box.id)
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

        # Face Recognition Logic
        if face_enabled:
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
                        
                        # Draw
                        cv2.rectangle(annotated_frame, (box[0], box[1]), (box[0]+box[2], box[1]+box[3]), (255, 0, 0), 2)
                        cv2.putText(annotated_frame, f"Face {score:.2f}", (box[0], box[1]-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
                        
                        # Publish Face Event
                        event_obj = { 
                            'camera_id': int(camera_id), 
                            'event': 'face_detected', 
                            'payload': { 'label': 'Face', 'score': float(score), 'bbox': box.tolist() } 
                        }
                        r.publish('detections', json.dumps(event_obj))
            except Exception as e:
                print(f"⚠️ Face detection error: {e}")

        with global_state['lock']:
            stream = global_state['streams'].get(str(camera_id))
            if stream is not None:
                stream['current_frame'] = annotated_frame.copy()

        # Publicar detecciones en Redis y al Backend
        try:
            detections = results[0].boxes
            for box in detections:
                try:
                    # label and score extraction
                    label = results[0].names.get(int(box.cls), str(int(box.cls))) if results[0].names else str(int(box.cls))
                    score = float(box.conf)
                    bbox = box.xyxy.tolist()
                    payload = { 'label': label, 'score': score, 'bbox': bbox }
                    event_obj = { 'camera_id': int(camera_id), 'event': label, 'payload': payload }
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
                    print(f"⚠️ Error procesando box: {e}")
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
    return { 'status': 'ok', 'active_streams': active_ids }

@app.on_event("startup")
def startup_event():
    # Start the Redis listener thread on startup
    threading.Thread(target=redis_listener_loop, daemon=True).start()