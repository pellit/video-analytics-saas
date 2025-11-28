import os
import json
import time
import threading
import cv2
import redis
import numpy as np
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from ultralytics import YOLO

# Configuración
app = FastAPI()
REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)

# Estado Global (Compartido entre hilos)
global_state = {
    "active": False,
    "camera_id": None,
    "url": None,
    "current_frame": None, # Aquí guardamos la imagen procesada
    "lock": threading.Lock()
}

# Cargar modelo una sola vez al inicio
print("⏳ Cargando modelo YOLO...")
model = YOLO('yolov8n.pt')
print("✅ Modelo cargado.")

def video_processing_loop():
    """Bucle infinito que procesa video si hay una cámara activa"""
    print("🚀 Hilo de procesamiento iniciado")
    
    cap = None
    
    while True:
        # 1. Verificar si debemos trabajar
        if not global_state["active"]:
            if cap:
                cap.release()
                cap = None
            time.sleep(1)
            continue

        # 2. Inicializar video si es necesario
        if cap is None:
            print(f"Opening stream: {global_state['url']}")
            cap = cv2.VideoCapture(global_state['url'])
        
        # 3. Leer Frame
        success, frame = cap.read()
        if not success:
            print("Error leyendo frame o fin del stream. Reintentando...")
            cap.release()
            cap = None
            time.sleep(1)
            continue

        # 4. Inferencia IA (YOLO)
        results = model(frame, verbose=False)
        annotated_frame = results[0].plot()

        # 5. Guardar en variable global para el streaming
        with global_state["lock"]:
            global_state["current_frame"] = annotated_frame.copy()

        # 6. (Opcional) Enviar métricas a Redis cada 30 frames
        # ... lógica de conteo aquí ...

def redis_listener_loop():
    """Escucha órdenes de Laravel para cambiar de cámara"""
    print("👂 Escuchando Redis 'video_control'...")
    pubsub = r.pubsub()
    pubsub.subscribe('video_control')

    for message in pubsub.listen():
        if message['type'] == 'message':
            data = json.loads(message['data'])
            action = data.get('action')
            
            if action == 'START':
                print(f"▶ START cámara {data.get('camera_id')}")
                global_state["active"] = True
                global_state["camera_id"] = data.get('camera_id')
                global_state["url"] = data.get('url') # URL de YouTube
            
            elif action == 'STOP':
                print("⏹ STOP recibido")
                global_state["active"] = False

def generate_mjpeg():
    """Generador para el endpoint de video"""
    while True:
        frame = None
        with global_state["lock"]:
            if global_state["current_frame"] is not None:
                frame = global_state["current_frame"]
        
        if frame is None:
            # Si no hay frame, enviamos imagen negra o esperamos
            time.sleep(0.1)
            continue

        # Convertir a JPEG
        (flag, encodedImage) = cv2.imencode(".jpg", frame)
        if not flag:
            continue
            
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + bytearray(encodedImage) + b'\r\n')
        
        time.sleep(0.03) # Limitamos a ~30 FPS

# --- API ENDPOINTS ---

@app.get("/")
def health():
    return {"status": "running", "active": global_state["active"]}

@app.get("/video_feed")
def video_feed():
    return StreamingResponse(generate_mjpeg(), media_type="multipart/x-mixed-replace; boundary=frame")

# --- ARRANQUE DE HILOS ---
@app.on_event("startup")
def startup_event():
    # Lanzamos los hilos en background
    threading.Thread(target=redis_listener_loop, daemon=True).start()
    threading.Thread(target=video_processing_loop, daemon=True).start()