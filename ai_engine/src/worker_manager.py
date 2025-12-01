import os
import json
import time
import threading
import cv2
import redis
import numpy as np
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from ultralytics import YOLO
from yt_dlp import YoutubeDL

app = FastAPI()

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

        # Inferencia YOLO
        results = model(frame, verbose=False)
        annotated_frame = results[0].plot()

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
                    # Send to backend worker endpoint
                    backend_url = os.environ.get('BACKEND_API_URL', 'http://localhost:8000')
                    worker_key = os.environ.get('WORKER_API_KEY')
                    if worker_key:
                        try:
                            import requests
                            headers = {'X-WORKER-KEY': worker_key, 'Content-Type': 'application/json'}
                            requests.post(f"{backend_url}/api/worker/detections", json=event_obj, headers=headers, timeout=2)
                        except Exception as e:
                            print(f"⚠️ Error enviando deteccion al backend: {e}")
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
                    with global_state['lock']:
                        if cam_id not in global_state['streams']:
                            global_state['streams'][cam_id] = { 'active': True, 'url': url, 'current_frame': None, 'lock': threading.Lock(), 'thread': None }
                        else:
                            global_state['streams'][cam_id]['active'] = True
                            global_state['streams'][cam_id]['url'] = url
                        # Launch thread if missing
                        if not global_state['streams'][cam_id].get('thread'):
                            t = threading.Thread(target=stream_thread, args=(cam_id, url), daemon=True)
                            global_state['streams'][cam_id]['thread'] = t
                            t.start()
                    # Allow workers to send a model name (eg. 'yolov8n' or 'yolov8n.pt')
                    model_name = data.get('model')
                    if model_name:
                        try:
                            print(f"⚙️ Loading model requested: {model_name}")
                            global model
                            model = YOLO(f"{model_name}.pt") if not model_name.endswith('.pt') else YOLO(model_name)
                        except Exception as e:
                            print(f"⚠️ Error loading {model_name}: {e}")
                    global_state["active"] = True
                elif action == 'STOP':
                    cam_id = str(data.get('camera_id'))
                    with global_state['lock']:
                        if cam_id in global_state['streams']:
                            global_state['streams'][cam_id]['active'] = False
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
    return { 'status': 'ok', 'active_streams': list(global_state['streams'].keys()) }

@app.on_event("startup")
def startup_event():
    # Start the Redis listener thread on startup
    threading.Thread(target=redis_listener_loop, daemon=True).start()