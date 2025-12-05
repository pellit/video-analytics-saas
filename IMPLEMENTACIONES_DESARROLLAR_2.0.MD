Esta es la implementación de la arquitectura **Híbrida de Alto Rendimiento**.

**El Concepto:**

1.  **MediaMTX (Go):** Se encarga de distribuir el video. Es infinitamente más eficiente que Python para esto.
2.  **Python:** Solo "mira" el video para detectar (YOLO) y envía coordenadas (Texto JSON) a Redis. **Ya no dibuja ni recodifica video.**
3.  **Vue (Cliente):** Recibe el video limpio y dibuja las cajas usando la GPU de la computadora del usuario (Canvas).

Aquí tienes el paso a paso:

-----

### Paso 1: Infraestructura (Docker Compose)

Vamos a agregar **MediaMTX**, un servidor de streaming ultraligero escrito en Go.

Edita tu `docker-compose.yml` y agrega este servicio:

```yaml
  media_server:
    image: bluenviron/mediamtx:latest
    container_name: saas_media
    ports:
      - "8554:8554" # Entrada RTSP (Para que Python envíe el video)
      - "8889:8889" # Salida WebRTC (Para que el navegador lo vea con latencia < 500ms)
      - "8888:8888" # Salida HLS (Opcional, para móviles)
    environment:
      MTX_PROTOCOLS: "tcp"
    networks:
      - saas_net
```

*(Dale a **Redeploy** para que este servidor empiece a correr).*

-----

### Paso 2: El Cerebro (Python Worker)

Vamos a modificar el worker para que haga dos cosas a la vez:

1.  **Streaming:** Empujar el video crudo hacia el MediaServer (usando FFmpeg).
2.  **IA:** Detectar y enviar solo DATOS (JSON) a Redis.

**Instala FFmpeg en el Dockerfile (`ai_engine/Dockerfile`):**
Asegúrate de que `ffmpeg` esté instalado (ya lo pusimos, pero verifica).

**Actualiza `ai_engine/src/worker_manager.py`:**

```python
import subprocess
import json
# ... otros imports ...

# Configuración del servidor de medios (nombre del servicio en docker)
RTSP_URL = "rtsp://media_server:8554/live" 

def start_ffmpeg_process(width, height, fps):
    """Inicia un subproceso FFmpeg para enviar video al servidor Go"""
    command = [
        'ffmpeg',
        '-y',
        '-f', 'rawvideo',
        '-vcodec', 'rawvideo',
        '-pix_fmt', 'bgr24',
        '-s', f'{width}x{height}',
        '-r', str(fps),
        '-i', '-',
        '-c:v', 'libx264',
        '-preset', 'ultrafast', # Mínima CPU
        '-f', 'rtsp',
        RTSP_URL
    ]
    return subprocess.Popen(command, stdin=subprocess.PIPE)

def video_processing_loop():
    # ... código de conexión ...
    
    ffmpeg_process = None
    
    while True:
        if cap is None:
             # ... obtener URL de yt-dlp ...
             cap = cv2.VideoCapture(real_url)
             
             # Obtener dimensiones originales una vez
             w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
             h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
             fps = 30 
             
             # Iniciar el tubo hacia el servidor de medios
             if ffmpeg_process: ffmpeg_process.kill()
             ffmpeg_process = start_ffmpeg_process(w, h, fps)

        success, frame = cap.read()
        if not success: continue

        # 1. ENVIAR VIDEO CRUDO (Sin pintar) AL SERVIDOR GO
        # Esto consume muy poco porque 'ultrafast' no comprime fuerte
        try:
            ffmpeg_process.stdin.write(frame.tobytes())
        except Exception:
            pass # Manejar reconexión si ffmpeg muere

        # 2. IA (YOLO)
        # Usamos el modelo optimizado que elegiste
        results = model(frame, imgsz=320, verbose=False)
        
        # 3. EXTRAER DATOS (NO DIBUJAR)
        detections = []
        for r in results[0].boxes:
            # Normalizamos coordenadas (0 a 1) para que funcione en cualquier tamaño de pantalla
            x, y, w, h = r.xywhn[0].tolist() 
            conf = float(r.conf[0])
            cls = int(r.cls[0])
            
            if conf > 0.4:
                detections.append({
                    "x": x, "y": y, "w": w, "h": h,
                    "class": model.names[cls],
                    "id": getattr(r, 'id', None) # Si usas tracking
                })

        # 4. ENVIAR DATOS A REDIS (Laravel Reverb los tomará)
        if len(detections) > 0:
            r.publish('camera_events', json.dumps({
                'camera_id': global_state['camera_id'],
                'type': 'detections',
                'data': detections,
                'ts': time.time()
            }))
```

-----

### Paso 3: El Cliente (Componente Vue Inteligente)

Aquí creamos un componente que superpone un `<canvas>` sobre el video.

Crea `frontend/src/components/SmartPlayer.vue`:

```html
<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'

const props = defineProps(['streamUrl', 'cameraId'])
const videoRef = ref(null)
const canvasRef = ref(null)
const detections = ref([])

// 1. Conexión WebSocket (Usando Laravel Echo/Reverb)
// Asumimos que ya tienes configurado Echo en tu main.js
// Si no, aquí usaríamos una conexión WS directa simple para el ejemplo
const connectToDataStream = () => {
    window.Echo.channel('camera_events')
        .listen('.detections', (e) => {
            if(e.camera_id === props.cameraId) {
                detections.value = e.data
                drawBoxes()
            }
        })
}

// 2. Dibujar en el Canvas
const drawBoxes = () => {
    const canvas = canvasRef.value
    const video = videoRef.value
    if (!canvas || !video) return

    // Ajustar canvas al tamaño real del video en pantalla
    canvas.width = video.clientWidth
    canvas.height = video.clientHeight
    
    const ctx = canvas.getContext('2d')
    ctx.clearRect(0, 0, canvas.width, canvas.height)

    detections.value.forEach(det => {
        // Convertir coordenadas normalizadas (0-1) a píxeles
        const x = (det.x - det.w / 2) * canvas.width
        const y = (det.y - det.h / 2) * canvas.height
        const w = det.w * canvas.width
        const h = det.h * canvas.height

        // Dibujar caja
        ctx.strokeStyle = '#00FF00'
        ctx.lineWidth = 2
        ctx.strokeRect(x, y, w, h)

        // Dibujar etiqueta
        ctx.fillStyle = '#00FF00'
        ctx.fillRect(x, y - 20, w, 20)
        ctx.fillStyle = 'black'
        ctx.fillText(det.class, x + 5, y - 5)
    })
}

onMounted(() => {
    connectToDataStream()
    // Loop de animación para limpiar si deja de haber datos
    setInterval(() => {
        if(Date.now() - lastDataTime > 500) detections.value = []
    }, 1000)
})
</script>

<template>
    <div class="smart-player">
        <iframe 
            :src="`http://TU_IP:8889/${cameraId}/`" 
            class="video-layer"
            frameborder="0"
            ref="videoRef"
        ></iframe>

        <canvas ref="canvasRef" class="overlay-layer"></canvas>
    </div>
</template>

<style scoped>
.smart-player { position: relative; width: 100%; height: 100%; }
.video-layer { width: 100%; height: 100%; object-fit: contain; }
.overlay-layer { position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; }
</style>
```

### ¿Por qué esto es mejor?

1.  **Cero Lag de Video:** MediaMTX envía el video usando WebRTC o HLS optimizado. Python no toca el transporte de red.
2.  **Cero Pintura en Servidor:** Tu CPU ya no calcula pixeles verdes. Solo hace matemáticas.
3.  **Seguridad:** El usuario recibe el video desde el puerto 8889 (MediaMTX) y los datos por el puerto de WebSocket seguro. Nunca toca el proceso de Python.
4.  **Escalabilidad:** Si entran 100 usuarios a ver la cámara, **MediaMTX  (Go)** maneja esa carga (y es supereficiente). Tu Python sigue procesando **una sola vez** el stream, sin importar cuántos miren.

**Requisito:** Para que el `iframe` de MediaMTX funcione en modo WebRTC, tu servidor debe tener los puertos UDP abiertos o usar el modo TCP (`MTX_PROTOCOLS: "tcp"`).