¡Es una idea brillante\! Integrar imágenes satelitales como si fueran "cámaras lentas" (actualizadas cada cierto tiempo en lugar de 30 FPS) le da un valor enorme a tu plataforma para agricultura, construcción o seguridad perimetral.

Aquí tienes el enfoque completo: las **fuentes de datos** (gratuitas y de pago), el **pseudocódigo** para tu Worker de Python y cómo integrarlo en tu arquitectura actual.

-----

### 1\. Fuentes de Imágenes Satelitales (APIs)

Para que esto funcione como una "cámara", necesitas una API que te permita pedir una foto reciente de una coordenada específica.

  * **Sentinel Hub (ESA - Agencia Espacial Europea):**

      * *Tipo:* Freemium.
      * *Actualización:* Cada 5 días aprox.
      * *Resolución:* 10 metros/píxel (Gratis).
      * *Uso:* Ideal para detectar cambios grandes (construcciones, deforestación, inundaciones).
      * *Ventaja:* Tienen una API muy fácil de usar (`Sentinel Hub OGC API`).

  * **Google Earth Engine / Google Maps Static API:**

      * *Tipo:* Pago (con capa gratuita generosa).
      * *Actualización:* Varía (puede ser meses).
      * *Uso:* Bueno para referencia visual, malo para monitoreo en tiempo real.

  * **Planet (Planet Labs):**

      * *Tipo:* Pago (Enterprise).
      * *Actualización:* **Diaria** (Daily imagery).
      * *Resolución:* Muy alta (3 metros o 50 cm).
      * *Uso:* Si tu cliente paga bien, esta es la mejor opción para "casi tiempo real".

  * **NASA GIBS (Global Imagery Browse Services):**

      * *Tipo:* Gratis.
      * *Actualización:* Diaria.
      * *Resolución:* Baja (ideal para clima o grandes desastres).

-----

### 2\. Estrategia de Integración

No puedes tratar un satélite *exactamente* igual que un video de 30 FPS porque la imagen no cambia cada segundo. La estrategia es **"Timelapse bajo demanda"**.

1.  **En Laravel:** El usuario define una "Zona" (polígono o coordenadas) y una frecuencia (ej: "Revisar cada 24hs").
2.  **En Redis:** Laravel programa un Job (Tarea) que se ejecuta solo cuando toca revisar.
3.  **En Python:** El Worker descarga la imagen, corre la IA (YOLO) y guarda el resultado.

-----

### 3\. Pseudocódigo del Worker Satelital

Este script sería un nuevo módulo dentro de tu `ai_engine`. En lugar de `video_processing_loop`, tendrías `satellite_processing_loop`.

```python
# Módulos necesarios
import requests
import cv2
import numpy as np
from datetime import datetime

# Configuración de API (Ejemplo con Sentinel Hub)
API_KEY = "tu_api_key"
BASE_URL = "https://services.sentinel-hub.com/api/v1/process"

def fetch_satellite_image(lat, lon, zoom_level):
    """
    Descarga la última imagen disponible de una coordenada.
    Devuelve la imagen en formato OpenCV (numpy array).
    """
    # 1. Definir el Bounding Box (Área alrededor del punto)
    bbox = calculate_bbox(lat, lon, zoom_level)
    
    # 2. Configurar parámetros de la petición (Fecha, Bandas de color, Nubes)
    payload = {
        "input": {
            "bounds": {"bbox": bbox, "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}},
            "data": [{
                "type": "sentinel-2-l2a",
                "dataFilter": {
                    "timeRange": {"from": "2023-10-01T00:00:00Z", "to": datetime.now().isoformat()}
                }
            }]
        },
        "output": {"width": 1024, "height": 1024, "responses": [{"format": {"type": "image/jpeg"}}]}
    }
    
    # 3. Llamar a la API
    response = requests.post(BASE_URL, json=payload, headers={"Authorization": f"Bearer {API_KEY}"})
    
    if response.status_code == 200:
        # 4. Convertir bytes a imagen OpenCV
        image_bytes = np.frombuffer(response.content, np.uint8)
        image = cv2.imdecode(image_bytes, cv2.IMREAD_COLOR)
        return image
    else:
        print("Error descargando imagen satelital")
        return None

def process_satellite_task(task_data):
    """
    Esta función se ejecuta cuando Redis recibe una orden tipo 'CHECK_SATELLITE'
    """
    camera_id = task_data['camera_id']
    coords = task_data['coordinates'] # {lat: -32.9, lon: -60.6}
    
    # 1. Obtener la imagen
    frame = fetch_satellite_image(coords['lat'], coords['lon'], zoom_level=15)
    
    if frame is not None:
        # 2. Correr IA (Igual que con las cámaras de video)
        # Nota: Para satélite, YOLO normal puede fallar si los objetos son muy pequeños.
        # Se suele usar YOLO entrenado con vistas aéreas (DOTA dataset).
        results = model(frame) 
        annotated_frame = results[0].plot()
        
        # 3. Contar objetos (Ej: Contar coches en un estacionamiento, árboles, etc.)
        detections = len(results[0].boxes)
        
        # 4. Guardar resultado
        # A diferencia del video, aquí guardamos la FOTO en disco/S3 porque es un evento único
        filename = save_image_to_storage(annotated_frame, camera_id)
        
        # 5. Notificar a Laravel
        redis_client.publish('camera_events', json.dumps({
            'camera_id': camera_id,
            'type': 'satellite_update',
            'image_url': filename,
            'detections_count': detections,
            'timestamp': datetime.now().isoformat()
        }))

# Bucle principal del worker (Integrado en tu worker_manager.py actual)
def redis_satellite_listener():
    pubsub = r.pubsub()
    pubsub.subscribe('satellite_control') # Canal separado para no bloquear video
    
    for message in pubsub.listen():
        if message['type'] == 'message':
            data = json.loads(message['data'])
            # Lanzar en un hilo para no bloquear
            threading.Thread(target=process_satellite_task, args=(data,)).start()
```

### 4\. Adaptación en tu Frontend (Vue)

Para que el usuario lo vea "como una cámara", en tu componente `UserDashboard.vue`:

1.  Agrega un tipo de cámara en tu base de datos: `type: 'satellite'`.
2.  En el Dashboard:
      * Si es `type === 'video'`, muestra el tag `<img src="stream_url">` (lo que ya tienes).
      * Si es `type === 'satellite'`, muestra una imagen estática `<img src="ultima_foto_url">` y agrega un botón **"🔄 Actualizar Satélite"**.

### Recomendación de Modelo IA

Para imágenes satelitales, el modelo `yolov8n.pt` estándar (entrenado con fotos a nivel de calle) **funcionará mal**. Los coches se ven como rectángulos planos desde arriba.

**Solución:** Usa un modelo YOLOv8 entrenado con el dataset **DOTA** (imágenes aéreas) o **VisDrone**.

  * Puedes encontrar pesos (`.pt`) gratuitos en HuggingFace buscando "yolov8 aerial" o "yolov8 satellite".
  * Cargas ese modelo específico solo cuando procesas tareas de satélite: `model_satellite = YOLO('yolov8_aerial.pt')`.

Para integrar interpretación general de imágenes (entender el contexto, ej: *"Esto es un campo inundado"* vs *"Esto es un estacionamiento"*) en un entorno **sin GPU y optimizado para CPU**, la mejor opción actual es **Moondream2**.

Es un modelo VLM (Vision Language Model) increíblemente pequeño (**1.8B parámetros**) diseñado para correr en laptops, móviles y servidores modestos, pero con una capacidad de descripción sorprendente.

Aquí tienes la solución completa: **Fuente de Satélite (Sentinel Hub)** + **Interpretación (Moondream)**.

-----

### Parte 1: El Modelo LLM Liviano (Moondream2)

**Por qué este y no LLaVA o GPT-4?**

  * **Peso:** Pesa menos de 3GB en RAM.
  * **Velocidad:** En CPU moderna tarda 2-4 segundos en describir una imagen.
  * **Licencia:** Apache 2.0 (Uso comercial libre).

#### 1\. Instalación

Agrega esto a tu `ai_engine/requirements.txt`:

```text
transformers
einops
timm
torch
pillow
```

#### 2\. Código de Inferencia (`ai_engine/src/core/vlm.py`)

Crea este módulo para manejar la "inteligencia general".

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from PIL import Image

class SceneInterpreter:
    def __init__(self):
        print("🧠 Cargando Moondream2 (CPU Optimized)...")
        self.model_id = "vikhyatk/moondream2"
        self.revision = "2024-04-02" # Versión estable
        
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_id, 
            revision=self.revision,
            trust_remote_code=True
        )
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_id, revision=self.revision)

    def analyze(self, image_cv2, prompt="Describe this satellite image in detail. Is there flooding or fire?"):
        """
        Analiza la imagen y responde a la pregunta.
        """
        # Convertir OpenCV (BGR) a PIL (RGB)
        image_pil = Image.fromarray(cv2.cvtColor(image_cv2, cv2.COLOR_BGR2RGB))
        
        # Codificar imagen
        enc_image = self.model.encode_image(image_pil)
        
        # Generar respuesta
        answer = self.model.answer_question(enc_image, prompt, self.tokenizer)
        return answer

# Uso:
# interpreter = SceneInterpreter()
# description = interpreter.analyze(frame, "What kind of terrain is this? Are there buildings?")
```

-----

### Parte 2: Fuente de Imágenes Satelitales (Sentinel Hub)

Para monitorear áreas, usaremos **Sentinel Hub**. Tienen una capa gratuita generosa para pruebas y desarrollo.

1.  Regístrate en [Sentinel Hub](https://www.sentinel-hub.com/).
2.  Obtén tus credenciales `CLIENT_ID` y `CLIENT_SECRET`.

#### Código del Worker Satelital (`ai_engine/src/core/satellite.py`)

Este script se encarga de autenticarse, pedir la foto más reciente sin nubes y devolvértela.

```python
import requests
import numpy as np
import cv2
from datetime import datetime, timedelta
from oauthlib.oauth2 import BackendApplicationClient
from requests_oauthlib import OAuth2Session

# CONFIGURACIÓN
CLIENT_ID = "TU_CLIENT_ID"
CLIENT_SECRET = "TU_CLIENT_SECRET"
EVALSCRIPT = """
// Script simple para color real (RGB)
return [B04, B03, B02];
"""

def get_token():
    client = BackendApplicationClient(client_id=CLIENT_ID)
    oauth = OAuth2Session(client=client)
    token = oauth.fetch_token(
        token_url='https://services.sentinel-hub.com/oauth/token',
        client_secret=CLIENT_SECRET
    )
    return token['access_token']

def fetch_area(lat, lon, zoom=15):
    """
    Descarga una imagen de 512x512 de la zona
    """
    token = get_token()
    
    # Calcular BBox (Caja geográfica) simple alrededor del punto
    delta = 0.01 # Aprox 1km
    bbox = [lon - delta, lat - delta, lon + delta, lat + delta]
    
    url = "https://services.sentinel-hub.com/api/v1/process"
    
    # Buscamos imágenes del último mes
    date_to = datetime.now()
    date_from = date_to - timedelta(days=30)
    
    payload = {
        "input": {
            "bounds": {
                "bbox": bbox,
                "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}
            },
            "data": [{
                "type": "sentinel-2-l2a",
                "dataFilter": {
                    "timeRange": {
                        "from": date_from.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "to": date_to.strftime("%Y-%m-%dT%H:%M:%SZ")
                    },
                    "mosaickingOrder": "leastCC" # Dame la que tenga menos nubes
                }
            }]
        },
        "output": {
            "width": 512,
            "height": 512,
            "responses": [{"identifier": "default", "format": {"type": "image/jpeg"}}]
        },
        "evalscript": EVALSCRIPT
    }
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    response = requests.post(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        # Convertir a formato OpenCV
        image_bytes = np.frombuffer(response.content, np.uint8)
        img = cv2.imdecode(image_bytes, cv2.IMREAD_COLOR)
        return img
    else:
        print(f"Error Satélite: {response.text}")
        return None
```

-----

### Parte 3: Integración Final (El Cerebro)

Ahora modificamos tu `worker_manager.py` para que, cuando llegue una tarea tipo `SATELLITE_CHECK`, use ambos módulos.

**Lógica del Flujo:**

1.  Descargar foto satelital.
2.  Correr **YOLO** para contar objetos específicos (ej: "Hay 50 camiones").
3.  Correr **Moondream** para validar contexto (ej: "¿Es esto un estacionamiento o una carretera?").
4.  Si Moondream dice "Es un lago" y YOLO contó "50 camiones", **alerta de error** (Falso positivo).

**Pseudocódigo de Integración:**

```python
# ... imports de satellite.py y vlm.py ...

def process_satellite_job(job_data):
    lat, lon = job_data['lat'], job_data['lon']
    
    # 1. Obtener Imagen
    satellite_img = fetch_area(lat, lon)
    if satellite_img is None: return

    # 2. Detección Dura (YOLO - CPU ONNX)
    # Contamos cosas
    yolo_results = model_yolo(satellite_img)
    car_count = len([x for x in yolo_results[0].boxes.cls if x == 2]) # Clase 2 = Auto

    # 3. Interpretación Semántica (Moondream - CPU)
    # Verificamos coherencia
    interpreter = SceneInterpreter()
    context = interpreter.analyze(satellite_img, "Is this an urban area, a forest, or a body of water?")
    
    print(f"Reporte: Detectados {car_count} vehículos.")
    print(f"Contexto visual: {context}")

    # 4. Guardar en Base de Datos (Vía API Laravel)
    # Enviar { car_count, context, image_url } a Laravel
```

### Resumen

1.  **Moondream2** es tu mejor amigo para entender imágenes en CPU.
2.  **Sentinel Hub** es tu proveedor de imágenes (usa la API de Process).
3.  **Lógica Híbrida:** Usa YOLO para *contar* y Moondream para *explicar*.

¿Te gustaría que preparemos el `Dockerfile` para incluir estas nuevas librerías (`transformers`, `torch` cpu) sin que la imagen pese 10GB?

Esta es la configuración definitiva para integrar **Inteligencia Geoespacial (Sentinel)** y **Comprensión Visual (Moondream2)** en tu arquitectura actual, optimizando todo para **CPU** para no inflar tu servidor ni tu factura.

Vamos a actualizar tu servicio `ai_worker`.

-----

### Paso 1: `ai_engine/requirements.txt` (Optimizado para CPU)

El truco para que la imagen no pese 10GB es instalar **PyTorch versión CPU**. Si instalas la normal, descarga los drivers de Nvidia (CUDA) que pesan 4GB y no te sirven.

Edita `ai_engine/requirements.txt`:

```text
# --- Base ---
redis
fastapi
uvicorn
numpy
requests
python-dotenv

# --- Video / YOLO ---
opencv-python-headless
ultralytics
yt-dlp

# --- Satélite ---
sentinelhub-py
oauthlib
requests-oauthlib
shapely

# --- LLM / Moondream (CPU Optimized) ---
# Transformers para correr el modelo
transformers
timmm
einops
pillow

# Instalar PyTorch versión CPU explícitamente
--extra-index-url https://download.pytorch.org/whl/cpu
torch
torchvision
```

-----

### Paso 2: `ai_engine/Dockerfile` (Reconstrucción)

Actualizamos el Dockerfile para que procese estas librerías correctamente y cree directorios de caché para que no descargue el modelo de 3GB cada vez que reinicias.

Edita `ai_engine/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 1. Dependencias de sistema (agregamos git para algunas libs de python)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    git \
    && rm -rf /var/lib/apt/lists/*

# 2. Configurar caché de HuggingFace (Para que los modelos se guarden en el volumen)
ENV HF_HOME="/app/models/huggingface"
ENV TORCH_HOME="/app/models/torch"

# 3. Instalar Python Libs
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copiar código
COPY . .

# 5. Ejecutar
CMD ["python", "-u", "src/worker_manager.py"]
```

-----

### Paso 3: Módulo de Satélite (`src/core/satellite.py`)

Crea este archivo en `ai_engine/src/core/satellite.py`. Usaremos la librería oficial `sentinelhub` que maneja la autenticación compleja automáticamente.

```python
import os
import numpy as np
import cv2
from datetime import date, timedelta
from sentinelhub import SHConfig, SentinelHubRequest, DataCollection, MimeType, BBox, CRS

# Configura tus credenciales en el .env de Dockploy
CLIENT_ID = os.environ.get("SENTINEL_CLIENT_ID")
CLIENT_SECRET = os.environ.get("SENTINEL_CLIENT_SECRET")

def get_latest_satellite_image(lat, lon, km_radius=1):
    """
    Descarga la imagen más reciente (últimos 30 días) sin nubes.
    """
    if not CLIENT_ID or not CLIENT_SECRET:
        print("❌ Error: Faltan credenciales de Sentinel Hub")
        return None

    config = SHConfig()
    config.sh_client_id = CLIENT_ID
    config.sh_client_secret = CLIENT_SECRET

    # 1. Crear Bounding Box (Área de interés)
    # Aproximación simple: 1 grado lat ~= 111km. 
    delta = km_radius / 111.0 
    bbox = BBox(bbox=[lon - delta, lat - delta, lon + delta, lat + delta], crs=CRS.WGS84)

    # 2. Script de Evaluación (Evalscript)
    # Pide color verdadero (RGB) y multiplica por 2.5 para dar brillo
    evalscript = """
    //VERSION=3
    function setup() {
        return {
            input: ["B04", "B03", "B02"],
            output: { bands: 3 }
        };
    }
    function evaluatePixel(sample) {
        return [2.5 * sample.B04, 2.5 * sample.B03, 2.5 * sample.B02];
    }
    """

    # 3. Configurar Petición
    request = SentinelHubRequest(
        evalscript=evalscript,
        input_data=[
            SentinelHubRequest.input_data(
                data_collection=DataCollection.SENTINEL_2_L2A,
                time_interval=(date.today() - timedelta(days=30), date.today()),
                maxcc=0.1, # Máximo 10% de nubes
                mosaicking_order="leastCC" # Priorizar la imagen más limpia
            )
        ],
        responses=[SentinelHubRequest.output_response("default", MimeType.PNG)],
        bbox=bbox,
        size=(512, 512), # Tamaño de salida
        config=config
    )

    try:
        # 4. Descargar
        print(f"🛰️ Solicitando imagen satelital para {lat}, {lon}...")
        data = request.get_data()
        
        if len(data) > 0:
            # Sentinel devuelve formato RGB (0-1) o (0-255). 
            # Convertimos a formato OpenCV (BGR 0-255)
            image = np.array(data[-1]) * 255
            image = image.astype(np.uint8)
            image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
            return image
        else:
            print("⚠️ No se encontraron imágenes limpias en la fecha.")
            return None
            
    except Exception as e:
        print(f"❌ Error Sentinel: {e}")
        return None
```

-----

### Paso 4: Módulo LLM Moondream (`src/core/vlm.py`)

Crea este archivo en `ai_engine/src/core/vlm.py`.

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from PIL import Image
import cv2
import torch

class MoondreamAnalyzer:
    def __init__(self):
        print("🧠 Cargando Moondream2 (Optimizado para CPU)...")
        self.model_id = "vikhyatk/moondream2"
        self.revision = "2024-04-02"
        
        # Carga optimizada
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_id, 
            revision=self.revision, 
            trust_remote_code=True,
            # float32 es más lento pero 100% compatible con cualquier CPU
            # Si tu CPU es moderna, podrías probar torch.float16
            torch_dtype=torch.float32 
        )
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_id, revision=self.revision)
        print("✅ Moondream Listo.")

    def analyze_image(self, cv2_image, question):
        try:
            # Convertir OpenCV a PIL
            image = Image.fromarray(cv2.cvtColor(cv2_image, cv2.COLOR_BGR2RGB))
            
            # Codificar
            enc_image = self.model.encode_image(image)
            
            # Preguntar
            answer = self.model.answer_question(enc_image, question, self.tokenizer)
            return answer
        except Exception as e:
            return f"Error analizando imagen: {e}"
```

-----

### Paso 5: Actualizar `worker_manager.py`

Ahora integramos todo en tu worker principal. Haremos que escuche un nuevo tipo de acción: `ANALYZE_SATELLITE`.

```python
# ... (imports anteriores de fastapi, redis, etc) ...
from src.core.satellite import get_latest_satellite_image
from src.core.vlm import MoondreamAnalyzer

# ... (configuraciones de app y redis) ...

# Estado global para VLM (Cargamos bajo demanda o al inicio)
vlm_engine = None 

# ... (Tu código existente de video_processing_loop) ...

def process_satellite_task(data):
    """
    Hilo separado para procesar satélite sin congelar el video
    """
    global vlm_engine
    camera_id = data.get('camera_id')
    lat = float(data.get('lat'))
    lon = float(data.get('lon'))
    prompt = data.get('prompt', "Describe this satellite image. Is there construction or water?")

    print(f"🛰️ Iniciando análisis satelital Cam {camera_id}")

    # 1. Obtener Foto
    image = get_latest_satellite_image(lat, lon)
    
    if image is not None:
        # 2. Cargar Moondream si no está cargado (Lazy Loading para ahorrar RAM al inicio)
        if vlm_engine is None:
            vlm_engine = MoondreamAnalyzer()
        
        # 3. Interpretar
        description = vlm_engine.analyze_image(image, prompt)
        print(f"🤖 Interpretación IA: {description}")

        # 4. Guardar imagen (Simulado, aquí subirías a S3/Storage)
        # En producción: guardar en /app/public/snapshots/ y enviar URL
        filename = f"/app/models/sat_{camera_id}.jpg" 
        cv2.imwrite(filename, image)

        # 5. Responder a Laravel (vía Redis PubSub o API)
        # Aquí publicamos en un canal de eventos
        r.publish('camera_events', json.dumps({
            'type': 'SATELLITE_RESULT',
            'camera_id': camera_id,
            'description': description,
            'image_path': filename
        }))
    else:
        print("❌ Falló la descarga de satélite")

def redis_listener_loop():
    # ... (Tu código de conexión) ...
    
    for message in pubsub.listen():
        if message['type'] == 'message':
            data = json.loads(message['data'])
            action = data.get('action')
            
            if action == 'START':
                # ... (Lógica de video existente) ...
                pass
            
            elif action == 'ANALYZE_SATELLITE':
                # Nueva acción! Lanzamos en hilo aparte
                threading.Thread(target=process_satellite_task, args=(data,)).start()

# ... (Resto del código igual) ...
```

-----

### Paso 6: Configurar Variables en Dockploy

Para que esto funcione, necesitas registrarte en Sentinel Hub (es gratis para desarrollo) y obtener tus claves.

1.  Ve a [Sentinel Hub Dashboard](https://www.google.com/search?q=https://apps.sentinel-hub.com/dashboard/%23/account/settings).
2.  Crea un "OAuth Client".
3.  Copia el ID y el Secret.

En **Dockploy**, agrega estas variables al servicio `ai_worker`:

```ini
SENTINEL_CLIENT_ID=tu_id_copiado
SENTINEL_CLIENT_SECRET=tu_secret_copiado
```

### Paso 7: Desplegar

1.  Sube todo a Git.
2.  Dale **Redeploy** (O "Rebuild without cache" para que instale PyTorch y Transformers).

### Cómo probarlo (Vía Redis CLI)

Una vez desplegado, entra a tu servidor y lanza una orden de prueba:

```bash
docker exec -it saas_redis redis-cli PUBLISH video_control '{"action": "ANALYZE_SATELLITE", "camera_id": 99, "lat": -32.94, "lon": -60.63, "prompt": "Describe la imagen. ¿Es una zona urbana?"}'
```

El worker descargará la foto de Rosario (por las coordenadas), Moondream la mirará y escribirá en el log:
`🤖 Interpretación IA: The image shows an urban area with high density buildings...`




📋 Plan de Implementación por Etapas
ETAPA 1: Estabilización del Sistema Actual ⚡
Prioridad: ALTA - Antes de agregar nuevas features

Tarea	Descripción	Tiempo Est.
1.1	Arreglar problema de YouTube/yt-dlp (nodejs)	30 min
1.2	Verificar que RT-DETR funciona correctamente	15 min
1.3	Commit y pruebas de video funcionando	15 min
ETAPA 2: Módulo Satélite (Sentinel Hub) 🛰️
Nueva fuente de "cámaras lentas"

Tarea	Descripción	Tiempo Est.
2.1	Crear ai_engine/src/core/satellite.py	45 min
2.2	Agregar dependencias (sentinelhub-py, etc.)	15 min
2.3	Backend Laravel: Modelo SatelliteZone	30 min
2.4	API endpoints para crear/gestionar zonas	45 min
2.5	Worker: Canal satellite_control en Redis	30 min
2.6	Frontend: UI para agregar "cámara satelital"	1 hr
ETAPA 3: LLM Vision (Moondream2) 🧠
Interpretación inteligente de imágenes

Tarea	Descripción	Tiempo Est.
3.1	Crear ai_engine/src/core/vlm.py	30 min
3.2	Optimizar Dockerfile (HF_HOME, cache)	20 min
3.3	Endpoint API para análisis bajo demanda	30 min
3.4	Integración: Analizar snapshots de cámaras	45 min
3.5	Frontend: Botón "🤖 Analizar con IA"	30 min
ETAPA 4: Integración Híbrida 🔗
YOLO + Moondream trabajando juntos

Tarea	Descripción	Tiempo Est.
4.1	Validación cruzada (YOLO detecta + Moondream confirma)	1 hr
4.2	Alertas inteligentes con contexto	45 min
4.3	Dashboard de reportes satelitales	1 hr