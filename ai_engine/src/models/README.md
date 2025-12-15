# AI Detection Models

Este módulo proporciona una capa de abstracción para diferentes modelos de detección de objetos.

## Modelos Disponibles

### 1. ONNX Runtime ⚡ RECOMENDADO (Más rápido)

**Librería:** `onnxruntime`  
**Licencia:** Apache 2.0  
**Estado:** HABILITADO por defecto

ONNX Runtime es la opción más eficiente para CPU:
- **2-3x más rápido** que PyTorch directo
- Docker image mucho más pequeño
- Sin dependencias pesadas (PyTorch/TensorFlow)

**Uso:**
```bash
# 1. Generar el modelo ONNX (una sola vez, en local)
pip install super-gradients onnx
python export_yolonas.py

# 2. Copiar yolo_nas_s.onnx a ai_engine/models/
```

### 2. YOLO-NAS ✅ HABILITADO

**Librería:** `super-gradients` (Deci AI)  
**Licencia:** Apache 2.0  
**Estado:** HABILITADO (fallback si no hay ONNX)

YOLO-NAS es un modelo de detección de objetos de última generación desarrollado por Deci AI.

**Variantes disponibles:**
- `yolo_nas_s` - Pequeño (más rápido)
- `yolo_nas_m` - Mediano (equilibrado)
- `yolo_nas_l` - Grande (más preciso)

### 3. RT-DETR ✅ HABILITADO

**Librería:** `transformers` (HuggingFace)  
**Licencia:** Apache 2.0  
**Estado:** HABILITADO

RT-DETR es un detector basado en Transformers con excelente precisión.

**Variantes disponibles:**
- `PekingU/rtdetr_r50vd` - ResNet-50 backbone
- `PekingU/rtdetr_r101vd` - ResNet-101 backbone

### 4. Ultralytics YOLO ⚠️ DESHABILITADO

**Librería:** `ultralytics`  
**Licencia:** AGPL-3.0 (⚠️ RESTRICTIVA)  
**Estado:** DESHABILITADO por defecto

> ⚠️ **ADVERTENCIA LEGAL:** La licencia AGPL-3.0 requiere:
> - Distribución de código fuente abierto si se usa en producción
> - Licencia comercial de Ultralytics para uso propietario

## Configuración

### Variables de Entorno

```bash
# Seleccionar modelo (predeterminado: onnx)
DETECTION_MODEL=onnx              # Opciones: onnx, yolo_nas, rt_detr, ultralytics

# Ruta personalizada del modelo (opcional)
DETECTION_MODEL_PATH=yolo_nas_s.onnx

# Habilitar ultralytics (solo para pruebas)
ENABLE_ULTRALYTICS=true           # ⚠️ Solo desarrollo
```

### Uso en Docker Compose

```yaml
services:
  ai_engine:
    environment:
      - DETECTION_MODEL=onnx
    volumes:
      - ./ai_engine/models:/app/models:ro
```

## Exportar Modelo ONNX

```bash
# Instalar dependencias (solo para exportar)
pip install super-gradients onnx

# Exportar modelo
python export_yolonas.py --size small --input-size 640

# Opciones:
#   --size small|medium|large
#   --input-size 640 (estándar) o 320 (máxima velocidad)
```

## Uso Programático

```python
from models import get_detector, ModelFactory

# Obtener detector por defecto (desde env vars)
detector = get_detector()

# Obtener detector específico
detector = get_detector(model_type='rt_detr')

# Ver modelos disponibles
print(ModelFactory.list_available_models())
```

## Conversión de Modelos vía API (Super Admin)

El AI Worker expone nuevos endpoints (también disponibles en la Jetson) para automatizar la conversión de modelos desde el panel de Super Admin.

### 1. PyTorch (.pt/.pth) ➝ ONNX

```
POST /models/convert/pytorch-to-onnx
Form-Data:
  - weights: archivo .pt / .pth
  - config: JSON con la configuración
```

Ejemplo:

```bash
curl -X POST "$WORKER_URL/models/convert/pytorch-to-onnx" \
  -H "Accept: application/json" \
  -F "weights=@/path/a/tu_modelo.pth" \
  -F 'config={
        "model_name": "mi_detector",
        "framework": "torchscript",
        "batch_size": 1,
        "input_height": 640,
        "input_width": 640,
        "input_channels": 3,
        "opset": 13,
        "overwrite": true
      }'
```

Campos clave:

- `framework`: `torchscript`, `state_dict` (requiere `model_class` y `model_kwargs`) o `ultralytics`.
- `output_filename`: nombre del ONNX destino (por defecto `<model_name>.onnx`).
- `dynamic_batch`, `half_precision`, `simplify`: banderas adicionales para el export.

### 2. ONNX ➝ TensorRT (.engine FP16)

```
POST /models/convert/onnx-to-tensorrt
Form-Data:
  - model_file: archivo ONNX
  - config: JSON con la configuración
```

Ejemplo:

```bash
curl -X POST "$WORKER_URL/models/convert/onnx-to-tensorrt" \
  -F "model_file=@models/yolo_nas_s.onnx" \
  -F 'config={
        "model_name": "yolo_nas_s_fp16",
        "engine_filename": "yolo_nas_s_fp16.engine",
        "fp16": true,
        "workspace_size_mb": 1024,
        "keep_onnx_copy": true,
        "overwrite": true,
        "input_shapes": {
          "images": [1, 3, 640, 640]
        }
      }'
```

Notas:

- Si `keep_onnx_copy` es `true`, el ONNX se guarda en `ai_engine/models/`.
- Para redes con dimensiones dinámicas, usa `input_shapes` o `input_profiles` (min/opt/max por tensor).
- La Jetson utiliza TensorRT FP16 para duplicar el rendimiento; en servidores sin TensorRT el endpoint devolverá un error claro.

## API Endpoints

### GET /models

Lista todos los modelos disponibles y sus estados.

**Respuesta:**
```json
{
  "current_model": "YOLONASDetector",
  "available_models": {
    "yolo_nas": {
      "name": "YOLO-NAS",
      "license": "Apache 2.0",
      "status": "ENABLED (Recommended)"
    },
    ...
  },
  "class_names": { "0": "person", "1": "bicycle", ... }
}
```

### GET /models/info

Información del modelo actualmente cargado.

**Respuesta:**
```json
{
  "name": "YOLONASDetector",
  "is_loaded": true,
  "device": "cuda",
  "total_classes": 80
}
```

## Estructura de Archivos

```
ai_engine/src/models/
├── __init__.py          # Exports públicos
├── base.py              # Clase base abstracta
├── factory.py           # Factory para crear detectores
├── yolo_nas.py          # Implementación YOLO-NAS
├── rt_detr.py           # Implementación RT-DETR
├── ultralytics_yolo.py  # Implementación Ultralytics (deshabilitada)
└── README.md            # Esta documentación
```

## Migración desde Ultralytics

Si estabas usando ultralytics anteriormente, la migración es automática:

1. El sistema usará YOLO-NAS por defecto
2. La interfaz de detección es idéntica
3. Los resultados tienen el mismo formato

Para volver temporalmente a ultralytics (solo testing):

```bash
export ENABLE_ULTRALYTICS=true
export DETECTION_MODEL=ultralytics
```
