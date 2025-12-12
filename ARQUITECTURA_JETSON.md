# Arquitectura Distribuida con Jetson Nano

## 📋 Resumen

Esta arquitectura permite distribuir la carga de procesamiento de IA entre el servidor principal y dispositivos edge como **Jetson Nano**, aprovechando la GPU CUDA de la Jetson para acelerar la inferencia.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SERVIDOR PRINCIPAL                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ Frontend │  │ Backend  │  │  Redis   │  │ AI Worker│  │Streaming │      │
│  │  (Vue)   │  │ (Laravel)│  │          │  │ (Python) │  │ (ffmpeg) │      │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘      │
│       │             │             │             │             │             │
│       └─────────────┴─────────────┴─────────────┴─────────────┘             │
│                                    │                                         │
└────────────────────────────────────┼─────────────────────────────────────────┘
                                     │
                              HTTP POST /detect
                              (frame base64)
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           JETSON NANO (Edge)                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      Inference API (FastAPI)                        │    │
│  │                                                                     │    │
│  │   POST /detect          ──►  YOLO/ONNX  ──►  JSON detections       │    │
│  │   POST /detect/batch    ──►  (CUDA GPU)                             │    │
│  │   POST /detect/faces    ──►  YuNet                                  │    │
│  │                                                                     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│   GPU: NVIDIA Maxwell (128 CUDA cores)                                       │
│   RAM: 4GB compartida CPU/GPU                                                │
│   TensorRT: Disponible para máxima velocidad                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 🚀 Ventajas de esta Arquitectura

| Aspecto | Sin Jetson | Con Jetson |
|---------|------------|------------|
| **Inferencia** | CPU servidor (~2 FPS) | GPU Jetson (~15-30 FPS) |
| **Carga servidor** | Alta (CPU al 100%) | Baja (solo streaming) |
| **Latencia** | Variable | Consistente |
| **Escalabilidad** | Limitada | Múltiples Jetsons |
| **Costo** | Servidor potente | Jetson Nano (~$99) |

## 📦 Archivos Creados

```
video-analytics-saas/
├── docker-compose.jetson.yml      # Docker Compose para Jetson
├── ai_engine/
│   ├── Dockerfile.jetson          # Dockerfile optimizado ARM64+CUDA
│   ├── requirements.jetson.txt    # Dependencias para Jetson
│   └── src/
│       ├── inference_api.py       # API de inferencia (solo detección)
│       └── edge_client.py         # Cliente para servidor principal
```

## 🔧 Instalación

### En la Jetson Nano

#### 1. Preparar el Sistema

```bash
# Instalar JetPack SDK (si no está instalado)
# https://developer.nvidia.com/embedded/jetpack

# Instalar Docker con soporte NVIDIA
sudo apt-get update
sudo apt-get install -y nvidia-docker2
sudo systemctl restart docker

# Verificar CUDA
nvcc --version
nvidia-smi
```

#### 2. Transferir Archivos

```bash
# Desde el servidor principal
scp -r ai_engine/ jetson@<jetson-ip>:~/inference/
scp docker-compose.jetson.yml jetson@<jetson-ip>:~/inference/
```

#### 3. Construir y Ejecutar

```bash
# En la Jetson Nano
cd ~/inference

# Construir imagen
docker-compose -f docker-compose.jetson.yml build

# Ejecutar
docker-compose -f docker-compose.jetson.yml up -d

# Ver logs
docker-compose -f docker-compose.jetson.yml logs -f
```

#### 4. Verificar Funcionamiento

```bash
# Health check
curl http://localhost:5050/health

# Respuesta esperada:
# {
#   "status": "healthy",
#   "device": "jetson-nano",
#   "model": "yolo_fastest",
#   "cuda_available": true,
#   "tensorrt_available": true
# }
```

### En el Servidor Principal

#### 1. Configurar Variables de Entorno

```bash
# En .env o docker-compose.override.yml
JETSON_INFERENCE_URL=http://<jetson-ip>:5050

# O múltiples dispositivos (load balancing)
EDGE_INFERENCE_URLS=http://jetson1:5050,http://jetson2:5050

# Timeout para requests (segundos)
EDGE_INFERENCE_TIMEOUT=5.0

# Fallback a inferencia local si Jetson no disponible
EDGE_FALLBACK_LOCAL=true
```

#### 2. Reiniciar AI Worker

```bash
docker-compose restart ai_worker
```

## 📡 API de Inferencia

### Endpoints

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/models` | GET | Listar modelos disponibles |
| `/models/change` | POST | Cambiar modelo |
| `/detect` | POST | Detectar en una imagen |
| `/detect/upload` | POST | Detectar (file upload) |
| `/detect/batch` | POST | Detectar múltiples imágenes |
| `/detect/faces` | POST | Detección especializada de rostros |

### Ejemplo: Detectar Objetos

```python
import base64
import requests

# Leer imagen
with open("frame.jpg", "rb") as f:
    image_b64 = base64.b64encode(f.read()).decode()

# Enviar a Jetson
response = requests.post(
    "http://jetson-nano:5050/detect",
    json={
        "image_base64": image_b64,
        "confidence_threshold": 0.5,
        "classes": ["person", "car"],  # Opcional: filtrar clases
        "max_detections": 100
    }
)

result = response.json()
print(f"Detecciones: {result['count']}")
print(f"Tiempo inferencia: {result['inference_time_ms']:.1f}ms")

for det in result["detections"]:
    print(f"  - {det['class_name']}: {det['confidence']:.2f}")
```

### Ejemplo: Uso del Cliente Python

```python
from ai_engine.src.edge_client import EdgeInferenceClient
import cv2

# Crear cliente
client = EdgeInferenceClient("http://jetson-nano:5050")

# Capturar frame
cap = cv2.VideoCapture("rtsp://camera-ip/stream")
ret, frame = cap.read()

# Detectar
result = client.detect(
    frame,
    confidence_threshold=0.5,
    classes=["person", "car"]
)

if result.success:
    print(f"Detectados: {result.count} objetos")
    print(f"Tiempo total: {result.inference_time_ms + result.network_time_ms:.1f}ms")
    
    for det in result.detections:
        x1, y1, x2, y2 = det.bbox_pixels
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
```

## ⚡ Optimizaciones para Jetson

### TensorRT (Máxima Velocidad)

TensorRT puede acelerar la inferencia 2-3x convirtiendo modelos ONNX a motores optimizados.

```bash
# Convertir modelo ONNX a TensorRT
/usr/src/tensorrt/bin/trtexec \
    --onnx=models/yolov8n.onnx \
    --saveEngine=models/yolov8n.trt \
    --fp16
```

Luego configurar:

```yaml
# docker-compose.jetson.yml
environment:
  - ENABLE_TENSORRT=true
  - TENSORRT_ENGINE_PATH=/app/models/yolov8n.trt
```

### Modelos Recomendados

| Modelo | FPS (Jetson Nano) | Precisión | Uso |
|--------|-------------------|-----------|-----|
| `yolo_fastest` | ~25-30 FPS | Media | **Recomendado** |
| `mobilenet_ssd` | ~30-35 FPS | Baja | Máxima velocidad |
| `yolov4_tiny` | ~15-20 FPS | Media-Alta | Balance |
| `onnx` (YOLOv8n) | ~8-12 FPS | Alta | Precisión |

### Memoria

Jetson Nano tiene 4GB de RAM compartida entre CPU y GPU:

```yaml
# docker-compose.jetson.yml
deploy:
  resources:
    limits:
      memory: 3G  # Dejar 1GB para sistema
```

## 🔄 Arquitectura Multi-Jetson

Para mayor throughput, puedes usar múltiples dispositivos:

```
                    ┌──────────────┐
                    │   Servidor   │
                    │   Principal  │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ Jetson 1 │ │ Jetson 2 │ │ Jetson 3 │
        │ Cam 1-5  │ │ Cam 6-10 │ │ Cam 11-15│
        └──────────┘ └──────────┘ └──────────┘
```

Configuración:

```bash
# .env
EDGE_INFERENCE_URLS=http://192.168.1.101:5050,http://192.168.1.102:5050,http://192.168.1.103:5050
```

El `EdgeInferenceClient` hace load balancing automático con health checks.

## 🐛 Troubleshooting

### Error: "CUDA out of memory"

```bash
# Reducir batch size o resolución
DETECTION_RESOLUTION=low

# O usar modelo más ligero
DETECTION_MODEL=mobilenet_ssd
```

### Error: "Connection refused"

```bash
# Verificar que la API está corriendo
docker-compose -f docker-compose.jetson.yml logs

# Verificar puerto
sudo netstat -tlnp | grep 5050

# Verificar firewall
sudo ufw allow 5050/tcp
```

### Performance Baja

```bash
# Verificar uso de GPU
tegrastats

# Aumentar poder (Jetson Nano)
sudo nvpmodel -m 0  # Max performance
sudo jetson_clocks  # Max clocks
```

## 📊 Benchmarks Esperados

| Configuración | FPS | Latencia Total |
|---------------|-----|----------------|
| Solo servidor (CPU) | 2-3 | 300-500ms |
| Jetson (yolo_fastest) | 25-30 | 50-80ms |
| Jetson (TensorRT FP16) | 35-45 | 30-50ms |
| Multi-Jetson (3x) | 75-90 | 50-80ms |

---

## 🔗 Referencias

- [NVIDIA Jetson Nano Developer Kit](https://developer.nvidia.com/embedded/jetson-nano-developer-kit)
- [JetPack SDK](https://developer.nvidia.com/embedded/jetpack)
- [ONNX Runtime for Jetson](https://elinux.org/Jetson_Zoo#ONNX_Runtime)
- [TensorRT](https://developer.nvidia.com/tensorrt)
