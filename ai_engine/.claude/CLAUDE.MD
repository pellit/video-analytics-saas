# Resumen del módulo `ai_engine` — Contexto y Auditoría

Este documento recoge el contexto operativo del módulo `ai_engine`, cómo se cargan y exponen los modelos en el entorno Jetson (según `docker-compose.jetson.yml` y `ai_engine/Dockerfile`) y un resumen de auditoría con prioridades y pasos pendientes basados en la propuesta de arquitectura SOLID.

## 1. Visión general

`ai_engine` es el servicio de inferencia que expone una API (FastAPI / Uvicorn) para detección de objetos, estimación de pose, profundidad monocular y evaluadores deportivos. Está pensado para ejecutarse en NVIDIA Jetson (Nano/TX) y usa aceleración (CUDA / TensorRT) cuando está disponible.

## 2. Cómo se carga la IA (resumen técnico)

- **Archivo de orquestación:** `docker-compose.jetson.yml`
  - Servicio: `inference_api` (container_name: `jetson_inference`).
  - `build.context`: `./ai_engine`, `dockerfile`: `Dockerfile.jetson` (en Jetson la imagen build usa Dockerfile específico).
  - `command` (override): `python3.11 -m uvicorn src.inference_api:app --host 0.0.0.0 --port 5050 --workers 1` — esto inicia la API en el contenedor.
  - Variables de entorno críticas: `ENABLE_CUDA=true`, `CUDA_VISIBLE_DEVICES`, `YOLO_SIZE`, `CONFIDENCE_THRESHOLD`, `NMS_THRESHOLD`, `MODELS_DIR=/app/ai_engine/models`, `NFS_MEDIA_ROOT`.
  - Volúmenes importantes:
    - Host `./ai_engine/onnx` → Contenedor `/app/ai_engine/models` (sobrescribe los modelos que el Dockerfile pudiera descargar).
    - Host `./ai_engine/src` → Contenedor `/app/src` (código fuente montado para edición/hot-reload).
    - `jetson_tensorrt_cache` para persistencia de compilados TensorRT.

- **Dockerfile (base):** `ai_engine/Dockerfile` (y variantes `Dockerfile.jetson`) — instalación de dependencias, copiado del código y preparación de carpetas.
  - Instala dependencias del sistema (`libgl1`, `ffmpeg`, `nodejs`, etc.) y `pip install -r requirements.txt`.
  - Copia el repo dentro de `/app` y crea `/app/models` y `/app/ai_engine/models`.
  - Si existe `hit_detect.onnx` en la raíz, lo copia a `/app/models/hit_detect.onnx`.
  - Attempta descargar modelos de rostro (OpenCV Zoo) durante el build si faltan.
  - CMD por defecto: `python -u src/worker_manager.py` (pero `docker-compose.jetson.yml` lo sobreescribe ejecutando Uvicorn).

## 3. Qué implica esta configuración (consecuencias operativas)

- Para añadir o actualizar modelos ONNX/TensorRT basta colocar el fichero en `./ai_engine/onnx` en el host — el contenedor los verá en `/app/ai_engine/models` al arrancar.
- La opción de montar `./ai_engine/src` permite iterar sobre el código sin rebuild completo del contenedor.
- La persistencia de cache TensorRT acelera reconstrucciones sucesivas.

## 4. Auditoría de estado (Resumen y faltantes)

Basado en la auditoría previa y el análisis del código actual:

- **Models (domain dataclasses)**: 🟢 Listo — `PlayerState`, `BallState`, `FrameData` están definidos y sirven de contrato común.
- **Evaluadores (Technical, Mental...)**: 🟢 Listo — evaluadores desacoplados aplican a `FrameData`.
- **Orquestador (`orchestrator.py`)**: 🟡 Parcial — coordina servicios pero depende de `cv2.VideoCapture`. Falta abstracción de fuente de datos (`IDataProvider`) para soportar pruebas sin cámara o fuentes virtuales.
- **Physics Engine**: 🔴 Crítico / Faltante — `orchestrator.py` importa `PhysicsEngine` desde `.core.physics_engine` pero ese módulo no está presente en el repo. Necesario para:
  - Convertir bounding boxes/píxeles a metros (pixel→m)
  - Suavizar señales (Kalman / moving average)
  - Calcular velocidades/acceleraciones (m/s)
- **Percepción / Visión**: 🟡 Parcial — tienes `hit_detection_service_optimized.py` y `smart_loader.py`, pero la conversión física (pixel→m) debe moverse a la capa de física.
- **Audio / Voz**: 🔴 Pendiente — `AudioState` existe pero no hay integración de Whisper/Vosk, por lo que `MentalEvaluator` no recibe transcripciones reales.

## 5. Propuesta de arquitectura (aplicando SOLID)

Objetivo: separar Percepción (visión), Física y Evaluación para poder añadir habilidades sin cambiar el core.

- Core Data (contratos): `FrameData` unified — contiene `player_feet_location`, `ball_location (x,y,z)`, `pixel_to_meter_scale`, `keypoints`.
- PerceptionEngine: Ejecuta modelos (YOLO, Pose, MiDaS) y produce `FrameData` bruto (pixeles + profundidades estimadas).
- PhysicsEngine: Toma `FrameData` y produce `PhysicalState` con velocidades, aceleraciones, filtrado y métricas físicas.
- SkillEvaluator (interfaz): Recibe `PhysicalState` y `FrameData` y calcula métricas (Juggling, Dribbling, Sprint, Power).
- IDataProvider (abstracción): Fuente de frames — puede ser `CameraProvider` (cv2.VideoCapture), `VideoFileProvider`, o `SimulatedProvider` para pruebas unitarias.

Beneficios: testabilidad, reutilización de cálculos (velocidades), apertura a nuevas métricas sin toquetear la percepción.

## 6. Pasos prioritarios (acción recomendada)

1. Implementar `src/core/physics_engine.py` con:
   - funciones `pixel_to_meter`, `smooth_signal`, `estimate_velocity`, `estimate_impact`.
2. Introducir `IDataProvider` y refactorizar `orchestrator.py` para depender de la abstracción.
3. Integrar un transcriptor de audio (Whisper/Vosk) para popular `AudioState` si vas a usar `MentalEvaluator`.
4. Mover utilidades físicas/calibración a `ai_engine/src/core_physics.py` para reutilización entre evaluadores.

## 7. Cómo ejecutar / pruebas rápidas

- Levantar en Jetson (recomendado rebuild si cambias dependencias):

```bash
docker compose -f docker-compose.jetson.yml up --build -d
```

- Ejecutar la API directamente (desarrollo local, volumen `src` montado):

```bash
python3.11 -m uvicorn src.inference_api:app --host 0.0.0.0 --port 5050 --workers 1
```

- Añadir un modelo ONNX: copiar el `.onnx` a `./ai_engine/onnx` y reiniciar el contenedor; Docker Compose lo monta en `/app/ai_engine/models`.

## 8. Referencias

- Documentación principal: `ai_engine/AI_ENGINE_DOCS.MD` (resumen operativo y endpoints).
- Orquestación: `docker-compose.jetson.yml` (ruta raíz del repo).
- Dockerfile principal: `ai_engine/Dockerfile` y variantes `Dockerfile.jetson`.
