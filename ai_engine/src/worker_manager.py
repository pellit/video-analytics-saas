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
r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)

global_state = {
    "active": False,
    "camera_id": None,
    "url": None,
    "current_frame": None,
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

def video_processing_loop():
    print("🚀 Hilo de procesamiento iniciado")
    cap = None
    
    while True:
        if not global_state["active"]:
            if cap:
                cap.release()
                cap = None
            time.sleep(0.5)
            continue

        if cap is None:
            raw_url = global_state['url']
            print(f"🔍 Buscando stream para: {raw_url}")
            
            if "youtube" in raw_url or "youtu.be" in raw_url:
                real_url = get_stream_url(raw_url)
                print(f"▶ Stream URL obtenida (imprimiendo primeros 50 chars): {real_url[:50]}...")
            else:
                real_url = raw_url

            # Aumentamos el buffer para evitar cortes
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;udp"
            cap = cv2.VideoCapture(real_url)
            
            # Verificación extra
            if not cap.isOpened():
                print("❌ ERROR CRÍTICO: OpenCV no pudo abrir la URL.")
                cap = None
                time.sleep(2)
                continue
        
        success, frame = cap.read()
        
        if not success:
            # Si falla la lectura, no imprimas error en cada frame (ensucia el log)
            # Solo reintenta suavemente
            time.sleep(0.1)
            continue

        # Inferencia YOLO
        results = model(frame, verbose=False)
        annotated_frame = results[0].plot()

        with global_state["lock"]:
            global_state["current_frame"] = annotated_frame.copy()

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
                    global_state["url"] = data.get('url')
                    global_state["camera_id"] = data.get('camera_id')
                    global_state["active"] = True
                elif action == 'STOP':
                    global_state["active"] = False
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
def video_feed():
    return StreamingResponse(generate_mjpeg(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.on_event("startup")
def startup_event():
    threading.Thread(target=redis_listener_loop, daemon=True).start()
    threading.Thread(target=video_processing_loop, daemon=True).start()