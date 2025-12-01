#!/bin/bash

# 1. Crear directorio raíz
mkdir -p video-analytics-saas
cd video-analytics-saas

echo "📂 Creando estructura de directorios..."

# 2. Crear subdirectorios de servicios
mkdir -p backend
mkdir -p frontend
mkdir -p ai_engine/src
mkdir -p ai_engine/models
mkdir -p infrastructure/nginx
mkdir -p infrastructure/redis

# 3. Crear docker-compose.yml (ORQUESTADOR)
cat <<EOF > docker-compose.yml
version: '3.8'

services:
  # --- BACKEND (LARAVEL) ---
  api:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: saas_api
    ports:
      - "8000:8000"
    environment:
      - DB_HOST=db
      - REDIS_HOST=redis
      - DB_DATABASE=saas_video
      - DB_USERNAME=root
      - DB_PASSWORD=secret
    depends_on:
      - db
      - redis
    volumes:
      - ./backend:/var/www/html
    networks:
      - saas_net

  # --- FRONTEND (VUE) ---
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: saas_frontend
    ports:
      - "5173:5173"
    volumes:
      - ./frontend:/app
      - /app/node_modules
    networks:
      - saas_net

  # --- AI WORKER (PYTHON) ---
  ai_worker:
    build:
      context: ./ai_engine
      dockerfile: Dockerfile
    container_name: saas_ai_worker
    command: python src/worker_manager.py
    environment:
      - REDIS_HOST=redis
      - PYTHONUNBUFFERED=1
    volumes:
      - ./ai_engine/src:/app/src
      - ./ai_engine/models:/app/models
    depends_on:
      - redis
    networks:
      - saas_net

  # --- INFRAESTRUCTURA ---
  redis:
    image: redis:alpine
    container_name: saas_redis
    ports:
      - "6379:6379"
    networks:
      - saas_net

  db:
    image: mysql:8.0
    container_name: saas_db
    environment:
      MYSQL_DATABASE: saas_video
      MYSQL_ROOT_PASSWORD: secret
    volumes:
      - db_data:/var/lib/mysql
    networks:
      - saas_net

networks:
  saas_net:
    driver: bridge

volumes:
  db_data:
EOF

# 4. Configurar AI ENGINE (Python)
echo "🐍 Configurando Worker Python..."

# Dockerfile Python
cat <<EOF > ai_engine/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema para OpenCV (glib)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "src/worker_manager.py"]
EOF

# Requirements.txt
cat <<EOF > ai_engine/requirements.txt
redis
opencv-python-headless
ultralytics
vosk
numpy
sentence-transformers
requests
EOF

# Código Base del Worker (worker_manager.py)
cat <<EOF > ai_engine/src/worker_manager.py
import redis
import json
import time
import os

# Configuración Redis
REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)

def process_video(task_data):
    """Simulación del proceso de video (Aquí irá tu lógica YOLO)"""
    camera_id = task_data.get('camera_id')
    url = task_data.get('url')
    print(f"🎥 [WORKER] Iniciando análisis en Cámara {camera_id} ({url})")
    
    # Simular bucle de procesamiento
    # En el futuro, aquí instancias la clase VideoAnalyticsProcess
    for i in range(5):
        time.sleep(2)
        print(f"👁️ [WORKER] Detectando en cámara {camera_id}... Frame {i}")
        # Simular envío de evento a Laravel
        r.publish('camera_events', json.dumps({
            'camera_id': camera_id,
            'event': 'person_detected',
            'confidence': 0.95
        }))

def main():
    print(f"🚀 Worker de IA iniciado. Conectando a Redis en {REDIS_HOST}...")
    pubsub = r.pubsub()
    pubsub.subscribe('video_control')

    print("✅ Esperando comandos de Laravel en el canal 'video_control'...")

    for message in pubsub.listen():
        if message['type'] == 'message':
            try:
                data = json.loads(message['data'])
                print(f"📩 Mensaje recibido: {data}")
                
                if data.get('action') == 'START':
                    process_video(data)
                elif data.get('action') == 'STOP':
                    print(f"🛑 Deteniendo cámara {data.get('camera_id')}")
            except Exception as e:
                print(f"❌ Error procesando mensaje: {e}")

if __name__ == "__main__":
    main()
EOF

# 5. Configurar BACKEND (Dockerfile Base para Laravel)
echo "🐘 Configurando Dockerfile Backend..."
cat <<EOF > backend/Dockerfile
FROM php:8.2-fpm

# Instalar dependencias del sistema y extensiones PHP
RUN apt-get update && apt-get install -y \
    git \
    curl \
    libpng-dev \
    libonig-dev \
    libxml2-dev \
    zip \
    unzip

RUN docker-php-ext-install pdo_mysql mbstring exif pcntl bcmath gd

# Instalar Redis extension
RUN pecl install redis && docker-php-ext-enable redis

# Instalar Composer
COPY --from=composer:latest /usr/bin/composer /usr/bin/composer

WORKDIR /var/www/html
EOF

# 6. Configurar FRONTEND (Dockerfile Base para Vue)
echo "🎨 Configurando Dockerfile Frontend..."
cat <<EOF > frontend/Dockerfile
FROM node:18-alpine
WORKDIR /app
CMD ["npm", "run", "dev", "--", "--host"]
EOF

# 7. Git Ignore
cat <<EOF > .gitignore
/backend/vendor
/backend/.env
/frontend/node_modules
/frontend/dist
/ai_engine/__pycache__
/ai_engine/models/*
.DS_Store
.idea
.vscode
EOF

echo "✅ ¡Estructura del proyecto creada exitosamente en la carpeta 'video-analytics-saas'!"
echo "👉 Sigue las instrucciones del chat para inicializar Laravel y Vue."