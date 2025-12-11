import requests
import base64
import json
import cv2
import numpy as np

# Configuración
API_URL = "http://192.168.0.37:5050/detect" # Si estás en otra PC, pon la IP de la Jetson
IMAGE_PATH = "frontend/test-results/01-login-page.png" # Asegúrate de tener una foto jpg llamada test.jpg ahí

# 1. Cargar imagen y convertir a Base64
with open(IMAGE_PATH, "rb") as img_file:
    b64_string = base64.b64encode(img_file.read()).decode('utf-8')

# 2. Crear payload
payload = {
    "image_base64": b64_string,
    "confidence": 0.4,
    "nms_threshold": 0.4
}

# 3. Enviar petición
print(f"Enviando a {API_URL}...")
try:
    response = requests.post(API_URL, json=payload)
    
    if response.status_code == 200:
        data = response.json()
        print("\n✅ ÉXITO! Respuesta del servidor:")
        print(f"Tiempo de Inferencia: {data['time_ms']} ms")
        print(f"Detecciones encontradas: {len(data['detections'])}")
        print(json.dumps(data['detections'], indent=2))
    else:
        print(f"❌ Error {response.status_code}: {response.text}")

except Exception as e:
    print(f"❌ Error de conexión: {e}")
