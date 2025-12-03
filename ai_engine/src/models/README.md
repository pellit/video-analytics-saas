# AI Detection Models

Este módulo proporciona una capa de abstracción para diferentes modelos de detección de objetos.

## Modelos Disponibles

### 1. YOLO-NAS (Predeterminado) ✅ RECOMENDADO

**Librería:** `super-gradients` (Deci AI)  
**Licencia:** Apache 2.0  
**Estado:** HABILITADO por defecto

YOLO-NAS es un modelo de detección de objetos de última generación desarrollado por Deci AI. Ofrece el mejor equilibrio entre velocidad y precisión.

**Variantes disponibles:**
- `yolo_nas_s` - Pequeño (más rápido)
- `yolo_nas_m` - Mediano (equilibrado)
- `yolo_nas_l` - Grande (más preciso)

### 2. RT-DETR ✅ HABILITADO

**Librería:** `transformers` (HuggingFace)  
**Licencia:** Apache 2.0  
**Estado:** HABILITADO

RT-DETR es un detector de objetos en tiempo real basado en la arquitectura DETR (DEtection TRansformer). Ofrece excelente precisión con rendimiento en tiempo real.

**Variantes disponibles:**
- `PekingU/rtdetr_r50vd` - ResNet-50 backbone
- `PekingU/rtdetr_r101vd` - ResNet-101 backbone

### 3. Ultralytics YOLO ⚠️ DESHABILITADO

**Librería:** `ultralytics`  
**Licencia:** AGPL-3.0 (⚠️ RESTRICTIVA)  
**Estado:** DESHABILITADO por defecto

> ⚠️ **ADVERTENCIA LEGAL:** La licencia AGPL-3.0 requiere:
> - Distribución de código fuente abierto si se usa en producción
> - Licencia comercial de Ultralytics para uso propietario
> 
> **Solo habilitar para pruebas/desarrollo.**

**Variantes disponibles:**
- `yolov8n.pt` - Nano
- `yolov8s.pt` - Small
- `yolov8m.pt` - Medium
- `yolov8l.pt` - Large
- `yolov8x.pt` - XLarge

## Configuración

### Variables de Entorno

```bash
# Seleccionar modelo (predeterminado: yolo_nas)
DETECTION_MODEL=yolo_nas          # Opciones: yolo_nas, rt_detr, ultralytics

# Ruta personalizada del modelo (opcional)
DETECTION_MODEL_PATH=yolo_nas_m   # Variante específica

# Habilitar ultralytics (solo para pruebas)
ENABLE_ULTRALYTICS=true           # ⚠️ Solo desarrollo
```

### Uso en Docker Compose

```yaml
services:
  ai_engine:
    environment:
      - DETECTION_MODEL=yolo_nas
      - DETECTION_MODEL_PATH=yolo_nas_s
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
