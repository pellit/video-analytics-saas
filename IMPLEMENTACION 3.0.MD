# 📐 Architect's Eye - Análisis Inteligente de Planos CAD

## Implementación v3.0 - Feature Completa

---

## 🎯 Visión General

El módulo "Architect's Eye" permite analizar archivos CAD (DXF/DWG) usando inteligencia artificial, simulando el ojo de un experto en arquitectura e ingeniería. El sistema convierte planos técnicos en descripciones inteligentes y análisis detallados.

### Concepto Clave: Rasterización + VLM

1. **Rasterización (El Ojo)**: Convertir el archivo matemático (vectores CAD) en una imagen visual (PNG)
2. **VLM (El Cerebro)**: Usar Moondream2 para describir lo que "ve" en el plano

---

## 🏗️ Arquitectura

```
┌─────────────────┐      ┌─────────────────┐      ┌──────────────────────┐
│   Frontend      │      │    Backend      │      │   Python Worker      │
│  BlueprintPanel │◄────►│   Laravel API   │◄────►│   (CAD Processor)    │
│      .vue       │      │ CadController   │      │                      │
└─────────────────┘      └─────────────────┘      └──────────────────────┘
         │                       │                         │
         │ HTTP Polling          │ Redis                   │ Moondream2
         │ (status)              │ 'cad_control'           │ + ezdxf
         ▼                       ▼                         ▼
    ┌──────────┐          ┌──────────┐            ┌──────────────┐
    │ Progreso │          │ Database │            │ Renders PNG  │
    │ en vivo  │          │cad_projects│           │ + Análisis   │
    └──────────┘          └──────────┘            └──────────────┘
```

---

## 📁 Estructura de Archivos

### Backend (Laravel)

| Archivo | Descripción |
|---------|-------------|
| `database/migrations/2025_12_06_200000_create_cad_projects_table.php` | Migración con tablas para proyectos, lotes, comparaciones y analytics |
| `app/Models/CadProject.php` | Modelo Eloquent con casts, scopes y helpers |
| `app/Http/Controllers/CadController.php` | Controller con CRUD, upload, callbacks del worker |
| `routes/api/user.php` | Rutas protegidas bajo prefijo `/cad/` |
| `routes/api.php` | Ruta interna `/internal/cad/callback` para worker |

### AI Engine (Python)

| Archivo | Descripción |
|---------|-------------|
| `src/core/cad.py` | Módulo principal: `CADProcessor` con renderizado y análisis VLM |
| `src/worker_manager.py` | Integración: listener Redis `cad_control`, callbacks HTTP |
| `requirements.txt` | Dependencias: `ezdxf>=1.0.0`, `matplotlib>=3.7.0` |

### Frontend (Vue)

| Archivo | Descripción |
|---------|-------------|
| `src/components/BlueprintPanel.vue` | Panel completo con upload, lista, detalle y análisis |
| `src/components/UserDashboard.vue` | Integración: tab "📐 Planos" en sidebar |

---

## 🗄️ Modelo de Datos

### Tabla Principal: `cad_projects`

```sql
- id                          -- PK
- user_id                     -- FK a users
- name                        -- Nombre del proyecto
- description                 -- Descripción opcional
- project_type                -- architecture, engineering, electrical, etc.
- original_filename           -- Nombre original del archivo
- file_path                   -- Ruta en storage
- file_type                   -- dxf, dwg, pdf
- file_size                   -- Tamaño en bytes
- status                      -- pending, rendering, analyzing, completed, error
- progress                    -- 0-100
- current_step                -- Paso actual (para UI)
- error_message               -- Mensaje de error si falla
- render_image_path           -- PNG renderizado
- render_thumbnail_path       -- Thumbnail para lista
- analysis_general            -- JSON: descripción general
- analysis_rooms              -- JSON: habitaciones detectadas
- analysis_safety             -- JSON: elementos de seguridad
- analysis_structural         -- JSON: elementos estructurales
- analysis_dimensions         -- JSON: dimensiones estimadas
- analysis_materials          -- JSON: materiales sugeridos
- analysis_compliance         -- JSON: cumplimiento normativo (futuro)
- metadata                    -- JSON: info del CAD (layers, blocks, etc)
- tags                        -- JSON: tags para búsqueda
- processing_started_at       -- Timestamp inicio
- processing_completed_at     -- Timestamp fin
- processing_duration_seconds -- Duración total
```

### Tablas Futuras (Preparadas)

| Tabla | Propósito |
|-------|-----------|
| `cad_batch_jobs` | Análisis por lotes de múltiples archivos |
| `cad_batch_project` | Pivote batch ↔ project |
| `cad_comparisons` | Comparación entre versiones de planos |
| `cad_analytics` | Métricas agregadas para dashboards |

---

## 🔄 Flujo de Procesamiento

```
1. Usuario sube archivo DXF
         ↓
2. Laravel guarda archivo y crea registro (status: pending)
         ↓
3. Laravel publica en Redis 'cad_control': { action: 'PROCESS_CAD', ... }
         ↓
4. Worker Python recibe mensaje y ejecuta proceso:
   
   a) [5-30%] RENDERIZADO
      - ezdxf lee el archivo DXF
      - matplotlib renderiza a PNG 300dpi
      - Genera thumbnail 400x400
      - Callback: status='rendering'
   
   b) [30-95%] ANÁLISIS CON IA
      - Moondream2 analiza la imagen con 6 prompts especializados:
        • General (40%): "Describe this floor plan..."
        • Rooms (50%): "List all rooms..."
        • Safety (60%): "Identify safety elements..."
        • Structural (70%): "Identify structural elements..."
        • Dimensions (80%): "Estimate dimensions..."
        • Materials (90%): "Suggest materials..."
      - Callbacks con progreso en cada paso
   
   c) [100%] COMPLETADO
      - Callback final con todos los análisis
      - status='completed'

5. Frontend hace polling cada 2s y actualiza UI
         ↓
6. Usuario ve plano renderizado + análisis por tabs
```

---

## 🎨 Tipos de Análisis

| Tab | Icono | Prompt Base | Uso |
|-----|-------|-------------|-----|
| General | 🏠 | "Describe this floor plan in detail..." | Vista general del plano |
| Espacios | 🚪 | "List all rooms or spaces visible..." | Identificar habitaciones |
| Seguridad | 🔥 | "Identify safety elements: exits, extinguishers..." | Evaluación de seguridad |
| Estructura | 🏗️ | "Identify structural elements: columns, beams..." | Análisis estructural |
| Dimensiones | 📏 | "Estimate dimensions of spaces shown..." | Medidas aproximadas |
| Materiales | 🧱 | "Suggest materials based on drawing style..." | Recomendaciones |

---

## 🚀 API Endpoints

### Protegidos (Auth Required)

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/cad/project-types` | Listar tipos de proyecto disponibles |
| GET | `/api/cad/analytics` | Dashboard de estadísticas |
| GET | `/api/cad/projects` | Listar proyectos (paginado, filtrable) |
| POST | `/api/cad/projects` | Subir nuevo archivo CAD |
| GET | `/api/cad/projects/{id}` | Detalle de proyecto |
| PATCH | `/api/cad/projects/{id}` | Actualizar metadata |
| DELETE | `/api/cad/projects/{id}` | Eliminar proyecto |
| GET | `/api/cad/projects/{id}/status` | Estado de procesamiento |
| POST | `/api/cad/projects/{id}/reanalyze` | Re-analizar proyecto |

### Interno (Worker)

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/api/internal/cad/callback` | Callback del worker (X-WORKER-KEY) |

---

## 📡 Redis Channel

**Canal**: `cad_control`

**Mensaje de Procesamiento**:
```json
{
  "action": "PROCESS_CAD",
  "project_id": 123,
  "file_path": "/var/www/html/storage/app/public/cad_files/1/plan.dxf",
  "file_type": "dxf",
  "project_type": "architecture",
  "user_id": 1,
  "callback_url": "https://app.com/api/internal/cad/callback"
}
```

---

## 🔧 Configuración

### Variables de Entorno

```bash
# Worker
ENABLE_CAD=true              # Habilitar procesamiento CAD
ENABLE_VLM=true              # Habilitar Moondream2 (requerido para análisis)
WORKER_API_KEY=your-key      # Key para callbacks

# Backend (Laravel)
WORKER_API_KEY=your-key      # Mismo key que worker
```

### Dependencias Python

```txt
ezdxf>=1.0.0          # Lectura/manipulación de DXF
matplotlib>=3.7.0     # Renderizado a imagen
torch==2.1.0+cpu      # PyTorch CPU (para Moondream)
transformers>=4.36.0  # Hugging Face (para Moondream)
```

---

## 🔮 Roadmap - Futuras Iteraciones

### Fase 2: Análisis por Lotes
- [ ] Endpoint `/api/cad/batches` para crear lotes
- [ ] Upload múltiple de archivos
- [ ] Procesamiento en paralelo
- [ ] Resumen agregado del lote

### Fase 3: Comparación de Versiones
- [ ] Subir múltiples versiones del mismo plano
- [ ] Detección de diferencias (diff visual)
- [ ] Timeline de cambios
- [ ] Overlay de versiones

### Fase 4: Analytics Avanzadas
- [ ] Dashboard con métricas agregadas
- [ ] Estadísticas por tipo de proyecto
- [ ] Tendencias temporales
- [ ] Exportación de reportes PDF

### Fase 5: Cumplimiento Normativo
- [ ] Checklist de normas (código de edificación)
- [ ] Validación automática de anchos de pasillos
- [ ] Verificación de salidas de emergencia
- [ ] Accesibilidad (rampas, ascensores)

### Fase 6: Integración CAD Avanzada
- [ ] Soporte nativo DWG (ODAFileConverter)
- [ ] Soporte PDF (pdf2image + OCR)
- [ ] Extracción de tablas de materiales
- [ ] Lectura de anotaciones/cotas

---

## 📋 Checklist de Implementación

- [x] Migración de base de datos
- [x] Modelo CadProject
- [x] CadController con CRUD completo
- [x] Rutas API protegidas
- [x] Módulo cad.py con CADProcessor
- [x] Integración en worker_manager.py
- [x] Listener Redis 'cad_control'
- [x] BlueprintPanel.vue con UI completa
- [x] Integración en UserDashboard
- [x] Dependencias en requirements.txt
- [x] Documentación actualizada
- [ ] Tests unitarios
- [ ] Tests de integración
- [ ] Deploy a producción

---

## 📝 Notas de Desarrollo

### Rendimiento
- El renderizado de DXF grandes puede tomar 10-30 segundos
- El análisis con Moondream2 toma ~5-10 segundos por prompt en CPU
- Total estimado por proyecto: 1-3 minutos

### Limitaciones Actuales
- Solo archivos DXF (DWG requiere conversión externa)
- PDF no soportado aún
- Máximo 100MB por archivo
- Moondream2 requiere ~4GB RAM

### Debugging
```bash
# Ver logs del worker
docker logs video-analytics-saas-ai_worker-1 -f | grep CAD

# Verificar Redis
redis-cli SUBSCRIBE cad_control

# Probar endpoint
curl -X POST http://localhost:8000/api/cad/projects \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@plan.dxf" \
  -F "name=Test Plan" \
  -F "project_type=architecture"
```

---

## Referencia Original

El concepto original de "simular el ojo humano" se basaba en:

1. El Flujo de Trabajo ("The Architect's Eye")
Ingesta: El usuario sube el archivo .dwg o .dxf en el Frontend.

Conversión (El Cristalino): El sistema convierte el archivo vectorial (matemático) en una imagen de alta resolución (PNG).

Interpretación (La Retina + Cerebro):

Moondream2 (VLM): Mira la imagen completa para entender el contexto (ej: "Es un plano de planta de una casa con 3 habitaciones").

OpenCV/YOLO (Opcional): Puede detectar símbolos específicos (puertas, extintores) si lo entrenas.

Visualización: Se muestra en el Dashboard como una "Cámara Estática" con anotaciones inteligentes.

2. Preparación del Entorno (ai_engine)
Necesitamos herramientas para leer archivos CAD. La librería de Python ezdxf es excelente para esto, pero trabaja nativamente con DXF (el formato de intercambio estándar). Para DWG (propietario), usaremos un conversor o asumiremos DXF por ahora para mantenerlo 100% open source.

Actualiza ai_engine/requirements.txt:

Plaintext

ezdxf
matplotlib  # Para renderizar el CAD a imagen
scikit-image
Actualiza ai_engine/Dockerfile: Necesitamos librerías de sistema para el renderizado de fuentes.

Dockerfile

# ... (lo que ya tenías)
RUN apt-get update && apt-get install -y --no-install-recommends \
    # ... anteriores ...
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
3. El Módulo de Procesamiento CAD (src/core/cad.py)
Crea este archivo en ai_engine/src/core/cad.py. Este script toma un archivo CAD, lo convierte a imagen y se lo pasa a la IA.

Python

import ezdxf
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
import matplotlib.pyplot as plt
import cv2
import numpy as np
import os

def convert_cad_to_image(dxf_path, output_image_path):
    """
    Simula la 'vista': Convierte vectores DXF a una imagen PNG (Rasterización).
    """
    try:
        # 1. Cargar el archivo DXF
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()

        # 2. Configurar el renderizado (Fondo negro, líneas blancas para alto contraste)
        fig = plt.figure()
        ax = fig.add_axes([0, 0, 1, 1])
        ctx = RenderContext(doc)
        
        # Configurar colores para mejor visión de la IA (Fondo blanco es mejor para Moondream)
        ctx.set_current_layout(msp)
        
        out = MatplotlibBackend(ax)
        Frontend(ctx, out).draw_layout(msp, finalize=True)

        # 3. Guardar imagen temporal
        fig.savefig(output_image_path, dpi=300)
        plt.close(fig)
        
        # 4. Leer con OpenCV para devolver formato compatible
        img = cv2.imread(output_image_path)
        return img

    except Exception as e:
        print(f"❌ Error renderizando CAD: {e}")
        return None

def analyze_cad_content(image_path, vlm_engine):
    """
    Usa Moondream para 'leer' el plano.
    """
    image = cv2.imread(image_path)
    
    # Prompts específicos para arquitectura
    prompts = [
        "Describe this architectural floor plan. What rooms can you see?",
        "Are there any safety hazards or emergency exits visible?",
        "Estimate the number of rooms in this drawing."
    ]
    
    results = {}
    for p in prompts:
        answer = vlm_engine.analyze_image(image, p)
        results[p] = answer
        
    return results
4. Integración en el Worker (worker_manager.py)
Modificamos el worker para escuchar un nuevo tipo de tarea: PROCESS_CAD.

Python

# ... imports ...
from src.core.cad import convert_cad_to_image, analyze_cad_content

# ... (código existente) ...

def process_cad_task(data):
    """
    Hilo para procesar planos arquitectónicos
    """
    global vlm_engine
    
    file_path = data.get('file_path') # Ruta donde Laravel guardó el archivo
    camera_id = data.get('camera_id')
    
    print(f"📐 Procesando plano CAD: {file_path}")
    
    # 1. Convertir CAD a Imagen ("Ver")
    image_output_path = f"/app/public/cad_renders/{camera_id}.png"
    os.makedirs(os.path.dirname(image_output_path), exist_ok=True)
    
    cad_image = convert_cad_to_image(file_path, image_output_path)
    
    if cad_image is not None:
        # 2. Cargar Inteligencia (Moondream)
        if vlm_engine is None:
            vlm_engine = MoondreamAnalyzer()
            
        # 3. Interpretar ("Pensar")
        # Le pedimos un resumen general
        analysis = vlm_engine.analyze_image(cad_image, "Describe this blueprint in detail. Identify the type of building and rooms.")
        
        print(f"🏗️ Análisis CAD: {analysis}")
        
        # 4. Notificar a Laravel
        r.publish('camera_events', json.dumps({
            'type': 'CAD_ANALYSIS_COMPLETE',
            'camera_id': camera_id,
            'image_url': image_output_path, # URL de la imagen renderizada
            'description': analysis
        }))

# En redis_listener_loop agregar:
# elif action == 'PROCESS_CAD':
#     threading.Thread(target=process_cad_task, args=(data,)).start()
5. Backend Laravel (Subida de Archivos)
Necesitas un endpoint para subir el archivo .dxf.

backend/routes/api/user.php:

PHP

Route::post('/cameras/upload-cad', [CameraController::class, 'uploadCad']);
backend/app/Http/Controllers/CameraController.php:

PHP

public function uploadCad(Request $request) {
    $request->validate([
        'file' => 'required|file|extensions:dxf,dwg',
        'name' => 'required'
    ]);

    // 1. Guardar archivo
    $path = $request->file('file')->store('cad_files', 'public');
    $fullPath = storage_path('app/public/' . $path);

    // 2. Crear "Cámara" tipo CAD
    $camera = Auth::user()->cameras()->create([
        'name' => $request->name,
        'url' => $path, // Guardamos la ruta del archivo
        'type' => 'cad', // Nuevo campo en BD necesario
        'status' => 'processing'
    ]);

    // 3. Enviar trabajo a Python
    // Nota: Necesitas mapear el volumen para que Python acceda al archivo
    $message = json_encode([
        'action' => 'PROCESS_CAD',
        'camera_id' => $camera->id,
        'file_path' => "/app/storage/" . $path // Ruta dentro del contenedor Python
    ]);
    Redis::publish('video_control', $message);

    return response()->json($camera);
}
6. Frontend Vue (Visualización)
En tu SmartPlayer.vue o UserDashboard.vue, agregas la lógica para mostrar esto.

HTML

<template>
  <div class="video-card">
    <img v-if="camera.type === 'video'" :src="streamUrl" />
    
    <div v-else-if="camera.type === 'cad'" class="cad-viewer">
       <img :src="camera.latest_analysis_image" class="blueprint-img" />
       
       <div class="ai-overlay">
          <h4>👁️ Análisis IA</h4>
          <p>{{ camera.latest_analysis_text }}</p>
       </div>
    </div>
  </div>
</template>
Resumen de la "Simulación del Ojo Humano"
Con esta implementación logras exactamente lo que pediste:

Ojo (Visualización): ezdxf + matplotlib actúan como el ojo, transformando datos matemáticos abstractos (DXF) en una representación visual comprensible (PNG).

Cerebro (Interpretación): Moondream2 actúa como el córtex visual, mirando esa imagen generada y explicando: "Veo un plano de evacuación con dos salidas al norte".



a implementar el "Ojo Humano" que lee planos (CAD) en tu arquitectura actual, sin romper lo que ya tienes y optimizando recursos, este es el flujo tecnológico ideal.

El concepto clave aquí es Rasterización + VLM (Vision Language Model).

Rasterización (El Ojo): Convertir el archivo matemático (vectores del CAD) en una imagen visual (PNG/JPG) que la IA pueda "ver".

VLM (El Cerebro): Usar un modelo como Moondream2 (que ya configuramos para CPU) para que describa lo que ve.

🛠️ Tecnologías Recomendadas
Para mantenerlo en el ecosistema Python (Worker) y Laravel (Backend):

Lector de CAD: ezdxf (Librería Python).

Por qué: Es la mejor librería open-source para manipular archivos DXF. Es ligera y no requiere software externo.

Nota: Para archivos .dwg (formato cerrado), se recomienda convertirlos a .dxf antes, o usar el conversor binario ODAFileConverter (pero añade complejidad). Empezaremos con DXF nativo.

Renderizador (El Ojo): Matplotlib.

Por qué: ezdxf tiene un add-on que usa Matplotlib para "dibujar" el plano y exportarlo como imagen PNG de alta resolución.

Analista (El Cerebro): Moondream2 (Ya lo tienes).

Por qué: Es lo suficientemente inteligente para distinguir "habitaciones", "puertas" y "muros" sin necesitar una GPU de $10,000 USD.

🔄 El Flujo de Trabajo (Pipeline)
Fragmento de código

sequenceDiagram
    participant User as Usuario (Vue)
    participant API as Laravel API
    participant Storage as Disco/S3
    participant Redis as Redis Queue
    participant Worker as Python Worker
    participant AI as Moondream2

    User->>API: 1. Sube archivo .dxf (POST /cameras/upload-cad)
    API->>Storage: 2. Guarda archivo físico
    API->>DB: 3. Crea registro en 'cameras' (type='cad', status='processing')
    API->>Redis: 4. Publica tarea 'PROCESS_CAD'
    
    Redis->>Worker: 5. Worker toma la tarea
    Worker->>Worker: 6. Convierte DXF -> PNG (Renderizado)
    Worker->>AI: 7. Envía PNG + Prompt ("Describe este plano...")
    AI-->>Worker: 8. Devuelve descripción ("Es una casa de 3 ambientes...")
    
    Worker->>Redis: 9. Publica evento 'CAD_COMPLETE'
    Redis->>API: 10. Actualiza DB con resultado
    API->>User: 11. Notificación WebSocket (Tu plano está listo)
💻 Implementación Paso a Paso
Paso 1: Actualizar Dependencias del Worker
Necesitas agregar las librerías de dibujo CAD.

Edita ai_engine/requirements.txt:

Plaintext

# ... (lo que ya tenías)
ezdxf
matplotlib
Importante: Tendrás que reconstruir la imagen Docker (docker compose build ai_worker) para instalar esto.

Paso 2: Crear el Módulo de Conversión (src/core/cad.py)
Este script es el "Ojo". Toma un archivo técnico y saca una foto.

Crea el archivo ai_engine/src/core/cad.py:

Python

import ezdxf
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
import matplotlib.pyplot as plt
import os

def render_dxf_to_image(dxf_path, output_image_path):
    """
    Convierte un archivo DXF en una imagen PNG de alta resolución.
    """
    try:
        print(f"📐 Leyendo DXF: {dxf_path}")
        # 1. Cargar documento DXF
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()

        # 2. Configurar el contexto de renderizado
        # Usamos fondo blanco y líneas negras para que la IA lea mejor
        ctx = RenderContext(doc)
        
        # 3. Configurar Matplotlib
        fig = plt.figure(figsize=(20, 20), dpi=100) # Alta resolución
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_axis_off() # Quitar ejes X/Y
        
        # 4. Dibujar
        out = MatplotlibBackend(ax)
        Frontend(ctx, out).draw_layout(msp, finalize=True)

        # 5. Guardar
        print(f"🖼️ Guardando imagen renderizada en: {output_image_path}")
        fig.savefig(output_image_path, dpi=150, bbox_inches='tight', pad_inches=0)
        plt.close(fig)
        
        return True

    except Exception as e:
        print(f"❌ Error renderizando CAD: {e}")
        return False
Paso 3: Integrar en el Worker (worker_manager.py)
Agregamos la lógica para manejar el nuevo tipo de tarea.

Python

# ... imports ...
from src.core.cad import render_dxf_to_image
from src.core.vlm import MoondreamAnalyzer

# ... (código existente) ...

# Variable global para el motor de IA
vlm_engine = None

def process_cad_task(data):
    global vlm_engine
    
    camera_id = data.get('camera_id')
    # Ruta relativa dentro del contenedor (montada en volumen)
    # Laravel guarda en storage/app/public, Docker lo ve en /app/storage/...
    file_path = data.get('file_path') 
    
    # Rutas de salida
    output_dir = "/app/public/renders"
    os.makedirs(output_dir, exist_ok=True)
    image_filename = f"cad_{camera_id}.png"
    output_path = f"{output_dir}/{image_filename}"

    print(f"🏗️ Iniciando procesamiento CAD para ID {camera_id}")

    # 1. RENDERIZADO (El Ojo)
    success = render_dxf_to_image(file_path, output_path)
    
    if success:
        # 2. INTELIGENCIA (El Cerebro)
        if vlm_engine is None:
            vlm_engine = MoondreamAnalyzer() # Carga diferida para ahorrar RAM
            
        # Leemos la imagen que acabamos de generar
        import cv2
        img_cv2 = cv2.imread(output_path)
        
        # Preguntas clave para arquitectura
        prompt = "Describe this floor plan. Identify rooms, exits, and potential safety hazards."
        analysis = vlm_engine.analyze_image(img_cv2, prompt)
        
        print(f"🤖 Análisis IA: {analysis}")

        # 3. RESPUESTA
        # Enviamos la URL pública de la imagen y el texto
        r.publish('video_control', json.dumps({
            'type': 'CAD_PROCESSED',
            'camera_id': camera_id,
            'image_url': f"/storage/renders/{image_filename}", # URL web
            'analysis': analysis
        }))
    else:
        print("❌ Falló el renderizado del CAD")

# En el bucle de escucha de Redis (redis_listener_loop):
# ...
# elif action == 'PROCESS_CAD':
#     threading.Thread(target=process_cad_task, args=(data,)).start()
Paso 4: Backend Laravel (El Endpoint)
Necesitas modificar la base de datos para soportar tipos de cámaras y el archivo del plano.

Migración:

PHP

Schema::table('cameras', function (Blueprint $table) {
    $table->string('type')->default('video'); // 'video', 'satellite', 'cad'
    $table->string('file_path')->nullable();  // Para el archivo DXF
    $table->text('ai_summary')->nullable();   // Para guardar el análisis
});
Controlador (CameraController.php):

PHP

public function uploadCad(Request $request) {
    $request->validate(['file' => 'required|file', 'name' => 'required']);

    // Guardar archivo en disco
    $path = $request->file('file')->store('cad_files', 'public');

    // Crear registro
    $camera = Auth::user()->cameras()->create([
        'name' => $request->name,
        'url' => 'processing...', // Temporal
        'type' => 'cad',
        'file_path' => $path,
        'status' => 'processing'
    ]);

    // Enviar tarea a Python
    // Nota: Pasamos la ruta absoluta del sistema de archivos Docker
    Redis::publish('video_control', json_encode([
        'action' => 'PROCESS_CAD',
        'camera_id' => $camera->id,
        'file_path' => "/var/www/html/storage/app/public/" . $path 
    ]));

    return $camera;
}
Resumen de la Estrategia
Simulamos el ojo humano usando matplotlib para "dibujar" el plano matemático en una foto PNG de alta calidad.

Interpretamos esa foto con Moondream2 (optimizada para CPU) que entiende qué es una pared, una puerta o una ventana.

Integramos esto en tu app existente como un tipo de cámara especial que, en lugar de mostrar video en vivo, muestra la imagen estática analizada.



## OPTIMIZACION DE CODIGO

¡Manos a la obra\! Aquí tienes la secuencia de implementación definitiva para el módulo **"Ojo de Arquitecto"** (CAD a IA).

He organizado esto para que los contenedores puedan compartir los archivos (Laravel sube el archivo, Python lo lee) y para integrar las optimizaciones de limpieza de planos que diseñamos.

-----

### Paso 1: Infraestructura (El Volumen Compartido)

Para que Laravel (API) le pase el archivo `.dxf` a Python (Worker), ambos necesitan ver la misma carpeta de almacenamiento.

**1. Edita `docker-compose.yml` (y `dev` si lo usas):**
Define un volumen llamado `app_storage` y móntalo en ambos servicios.

```yaml
services:
  api:
    # ...
    volumes:
      - app_storage:/var/www/html/storage  # <--- AGREGAR ESTO

  ai_worker:
    # ...
    volumes:
      - app_storage:/app/storage           # <--- AGREGAR ESTO (Misma ruta interna relativa)

volumes:
  db_data:
  label_studio_data:
  app_storage:                             # <--- DECLARARLO AL FINAL
```

-----

### Paso 2: El Cerebro AI (Python)

Preparamos el worker para entender planos y usar Moondream.

**1. Actualiza `ai_engine/requirements.txt`:**
Agrega estas librerías al final:

```text
ezdxf
matplotlib
```

**2. Crea el módulo de renderizado `ai_engine/src/core/cad.py`:**
Este es el código optimizado que "limpia" el plano antes de verlo.

```python
import ezdxf
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
import matplotlib.pyplot as plt
import os

def clean_and_render_cad(dxf_path, output_image_path):
    try:
        print(f"📐 Procesando CAD: {dxf_path}")
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()

        # 1. LIMPIEZA: Borrar ruido (Cotas, Textos)
        for entity in msp:
            if entity.dxftype() in ['MTEXT', 'TEXT', 'DIMENSION', 'HATCH', 'LEADER']:
                msp.delete_entity(entity)

        # 2. RENDERIZADO: Alto contraste (Negro sobre Blanco)
        ctx = RenderContext(doc)
        fig = plt.figure(figsize=(20, 20), dpi=150)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_axis_off()
        
        out = MatplotlibBackend(ax)
        
        # Forzar líneas negras y gruesas
        def config_draw(properties):
            properties.color = '#000000'
            if properties.lineweight < 0.25: properties.lineweight = 0.5 
            return properties

        Frontend(ctx, out).draw_layout(msp, finalize=True)
        
        # Guardar
        os.makedirs(os.path.dirname(output_image_path), exist_ok=True)
        fig.savefig(output_image_path, dpi=150, bbox_inches='tight', pad_inches=0)
        plt.close(fig)
        return True
    except Exception as e:
        print(f"❌ Error CAD: {e}")
        return False
```

**3. Actualiza `ai_engine/src/worker_manager.py`:**
Agrega la lógica para manejar la tarea `PROCESS_CAD`.

```python
# ... imports ...
from src.core.cad import clean_and_render_cad
from src.core.vlm import MoondreamAnalyzer # Asegúrate de tener este archivo del paso anterior

# ... (código existente) ...

# Estado global
vlm_engine = None

def process_cad_task(data):
    global vlm_engine
    camera_id = data.get('camera_id')
    # Ruta mapeada en el volumen compartido
    file_path = f"/app/storage/app/public/{data.get('file_path')}"
    
    # Salida (carpeta pública para que Laravel la sirva)
    output_filename = f"render_{camera_id}.png"
    output_path = f"/app/storage/app/public/renders/{output_filename}"

    print(f"🏗️ Iniciando CAD ID {camera_id}")

    if clean_and_render_cad(file_path, output_path):
        # Cargar IA
        if vlm_engine is None: vlm_engine = MoondreamAnalyzer()
        
        # Analizar
        import cv2
        img = cv2.imread(output_path)
        prompt = "Describe this architectural floor plan. Identify rooms, structure and exits."
        analysis = vlm_engine.analyze_image(img, prompt)
        
        print(f"🤖 Resultado: {analysis}")

        # Avisar a Laravel
        r.publish('video_control', json.dumps({
            'type': 'CAD_COMPLETE',
            'camera_id': camera_id,
            'image_url': f"/storage/renders/{output_filename}",
            'analysis': analysis
        }))

# En redis_listener_loop agregar:
# elif action == 'PROCESS_CAD':
#     threading.Thread(target=process_cad_task, args=(data,)).start()
```

-----

### Paso 3: Backend Laravel (API)

**1. Migración para la BD:**
En tu PC local:

```bash
docker compose exec api php artisan make:migration add_type_to_cameras_table
```

Edita la migración:

```php
public function up(): void {
    Schema::table('cameras', function (Blueprint $table) {
        $table->string('type')->default('video'); // video, cad
        $table->string('file_path')->nullable();
        $table->text('ai_summary')->nullable();
        $table->string('latest_image_url')->nullable();
    });
}
```

**2. Actualiza `CameraController.php`:**
Agrega el método para subir y el listener de Redis (o simplemente guarda el resultado cuando el Frontend pregunte, para simplificar por ahora, guardaremos el estado).

```php
public function uploadCad(Request $request) {
    $request->validate(['file' => 'required|file', 'name' => 'required']);
    
    // Guardar en el disco 'public' (que es el volumen compartido)
    $path = $request->file('file')->store('cad_files', 'public');
    
    $camera = Auth::user()->cameras()->create([
        'name' => $request->name,
        'type' => 'cad',
        'file_path' => $path,
        'status' => 'processing'
    ]);

    // Avisar a Python
    // Nota: enviamos solo el nombre relativo, Python ya sabe el prefijo del volumen
    \Illuminate\Support\Facades\Redis::publish('video_control', json_encode([
        'action' => 'PROCESS_CAD',
        'camera_id' => $camera->id,
        'file_path' => $path 
    ]));

    return $camera;
}

// Método para actualizar resultado (llamado desde Python o un Job, 
// o simplificamos haciendo que Python actualice vía API si prefieres, 
// por ahora dejemos que el Frontend haga polling o espere el evento)
```

**3. Rutas (`routes/api/user.php`):**

```php
Route::post('/cameras/upload-cad', [CameraController::class, 'uploadCad']);
```

-----

### Paso 4: Frontend Vue (La Interfaz)

**1. Modificar `UserDashboard.vue`:**
Agregar botón de subir CAD y la visualización.

```html
<button @click="showCadModal = true" class="btn-cad">📐 Subir Plano</button>

<div v-if="activeCamera" class="video-box">
    
    <img v-if="activeCamera.type === 'video'" :src="STREAM_URL" class="stream" />
    
    <div v-else-if="activeCamera.type === 'cad'" class="cad-view">
        <div v-if="activeCamera.status === 'processing'" class="loading">
           ⚙️ Analizando Plano con IA...
        </div>
        <div v-else>
           <img :src="activeCamera.latest_image_url" class="blueprint" />
           <div class="ai-report">
              <h4>Análisis IA:</h4>
              <p>{{ activeCamera.ai_summary }}</p>
           </div>
        </div>
    </div>

</div>
```

-----

### Paso 5: Despliegue

1.  **Sube todo a Git**
2.  **Redeploy** en Dockploy (Esto reconstruirá la imagen de Python con las nuevas librerías y montará el volumen compartido).
3.  **Ejecuta la migración** en la consola de Dockploy:
    ```bash
    php artisan migrate --force
    ```
4.  **Crea el link simbólico** en Laravel (vital para ver las imágenes):
    ```bash
    docker exec -it code-api-1 php artisan storage:link
    ```