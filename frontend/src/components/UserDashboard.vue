<script setup>
import { ref, onMounted, computed, watch, nextTick, onUnmounted } from 'vue'
const props = defineProps(['token', 'user'])
const emit = defineEmits(['logout'])

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'
// Prefer explicit stream URL; fallback to computed from API URL to be compatible with existing setups
const getStreamUrl = () => {
    if (import.meta.env.VITE_STREAM_URL) return import.meta.env.VITE_STREAM_URL;
    if (import.meta.env.VITE_API_URL) {
        try {
            const url = new URL(import.meta.env.VITE_API_URL);
            url.port = '5000';
            url.pathname = '/video_feed';
            return url.toString();
        } catch (e) {
            console.error('Error parsing API URL for stream', e);
        }
    }
    return 'http://192.168.0.38:5000/video_feed';
}
const STREAM_URL = getStreamUrl();

const cameras = ref([])
const activeCamera = ref(null)
const isProcessing = ref(false)
const showAdd = ref(false)
const newCam = ref({ name: '', url: '' })

const fetchCameras = async () => {
  try {
    const res = await fetch(`${API_URL}/cameras`, { headers: { 'Authorization': `Bearer ${props.token}`, 'Accept': 'application/json' } })
    if (res.ok) {
        cameras.value = await res.json()
        if (cameras.value.length > 0) activeCamera.value = cameras.value[0]
    } else {
        if (res.status === 401) {
            alert('Sesión expirada. Por favor inicie sesión nuevamente.')
            emit('logout')
            return
        }
        const body = await res.json().catch(() => null)
        console.error('Error fetching cameras', res.status, body)
        alert(body?.message || 'No se pudieron cargar las cámaras')
    }
  } catch (e) {
    console.error(e)
    alert('Error de red al cargar cámaras')
  }
}

const isYouTubeUrl = (url) => {
  if (!url) return false
  return url.includes('youtube.com') || url.includes('youtu.be')
}

const getYoutubeEmbedUrl = (url) => {
  if (!url) return ''
  const idMatch = url.match(/(?:v=|youtu\.be\/)([a-zA-Z0-9_-]+)/)
  return idMatch ? `https://www.youtube.com/embed/${idMatch[1]}` : ''
}

const addCamera = async () => {
  try {
    // Default detection_enabled to true for new cameras so they are analyzed immediately
    const payload = { ...newCam.value, detection_enabled: true, detection_model: 'yolov8n' }
    const res = await fetch(`${API_URL}/cameras`, {
      method: 'POST', headers: { 'Authorization': `Bearer ${props.token}`, 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
    })
    const data = await res.json().catch(() => null)
    if (!res.ok) {
      console.error('Create camera failed', res.status, data)
      alert(data?.message || 'No se pudo crear la cámara')
      return
    }
    alert('Cámara creada correctamente')
    showAdd.value = false; newCam.value = { name: '', url: '' }; fetchCameras()
  } catch (e) {
    console.error(e)
    alert('Error de red al crear la cámara')
  }
}

// New alert form state
const newAlertName = ref('Auto Alert')
const newAlertEvent = ref('person_detected')
const newAlertThreshold = ref(0.5)
const runInBackground = ref(true) // Default: Keep running in background

// COCO Classes for Multi-select
const availableClasses = [
  'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', 'boat', 
  'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench', 'bird', 'cat', 
  'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe', 'backpack', 
  'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee', 'skis', 'snowboard', 'sports ball', 
  'kite', 'baseball bat', 'baseball glove', 'skateboard', 'surfboard', 'tennis racket', 
  'bottle', 'wine glass', 'cup', 'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple', 
  'sandwich', 'orange', 'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair', 
  'couch', 'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse', 
  'remote', 'keyboard', 'cell phone', 'microwave', 'oven', 'toaster', 'sink', 'refrigerator', 
  'book', 'clock', 'vase', 'scissors', 'teddy bear', 'hair drier', 'toothbrush'
]

const updateCameraSettings = async (camera) => {
  try {
    const res = await fetch(`${API_URL}/cameras/${camera.id}`, {
      method: 'PATCH', headers: { 'Authorization': `Bearer ${props.token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        detection_enabled: camera.detection_enabled, 
        detection_model: camera.detection_model, 
        detection_classes: camera.detection_classes, // Send selected classes
        face_recognition_enabled: camera.face_recognition_enabled, // Send face recognition setting
        depth_enabled: camera.depth_enabled,
        bev_enabled: camera.bev_enabled,
        tracking: camera.tracking 
      })
    })
    if (!res.ok) {
      const body = await res.json().catch(() => null)
      alert('No se pudo actualizar configuración: ' + (body?.message || res.status))
    } else {
      alert('Configuración actualizada')
    }
  } catch (e) { console.error(e); alert('Error red al actualizar cámara') }
}

const activeWorkerStreams = ref([])
const WORKER_URL = STREAM_URL.replace('/video_feed', '')

const fetchWorkerStatus = async () => {
    try {
        const res = await fetch(`${WORKER_URL}/health`)
        if (res.ok) {
            const data = await res.json()
            activeWorkerStreams.value = data.active_streams || []
        }
    } catch (e) {
        // Silent fail, worker might be down or unreachable
    }
}

// Poll worker status every 5 seconds
setInterval(fetchWorkerStatus, 5000)
onMounted(fetchWorkerStatus)

const isCameraRunning = (id) => activeWorkerStreams.value.includes(String(id))

// Watch for camera changes to handle background processing preference
watch(activeCamera, async (newCam, oldCam) => {
    // Sync local state with worker state
    if (newCam) {
        const running = isCameraRunning(newCam.id)
        // If running in background, we can choose to show it or not.
        // For now, let's assume if it's running, we show it as processing but maybe hidden video?
        // Let's just sync isProcessing to true if running, so user sees it immediately.
        if (running) {
            isProcessing.value = true
        } else {
            isProcessing.value = false
        }
    }
})

// Watch activeWorkerStreams to update UI if external start/stop happens
watch(activeWorkerStreams, (streams) => {
    if (activeCamera.value) {
        const running = streams.includes(String(activeCamera.value.id))
        if (running && !isProcessing.value) {
             // It started externally (or we just loaded), update UI
             isProcessing.value = true
        } else if (!running && isProcessing.value) {
             // It stopped externally
             isProcessing.value = false
        }
    }
})

const showVideo = ref(true)

const toggleAnalysis = async (start, backgroundOnly = false) => {
  const endpoint = start ? 'start' : 'stop'
  
  // If starting, ensure detection is enabled locally so we view the stream instead of embed
  if (start && activeCamera.value && !activeCamera.value.detection_enabled) {
      activeCamera.value.detection_enabled = true
      // Optionally save this preference to backend
      updateCameraSettings(activeCamera.value)
  }

  const res = await fetch(`${API_URL}/camera/${endpoint}`, {
    method: 'POST', headers: { 'Authorization': `Bearer ${props.token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ id: activeCamera.value.id, url: activeCamera.value.url })
  })
  
  if (res.status === 401) {
      alert('Sesión expirada. Por favor inicie sesión nuevamente.')
      emit('logout')
      return
  }

  if (!res.ok) {
      const body = await res.json().catch(() => null)
      alert('Error al cambiar estado: ' + (body?.message || res.status))
      return
  }

  // Update local state immediately for responsiveness
  if (start) {
      isProcessing.value = true
      showVideo.value = !backgroundOnly
      // Force fetch status to confirm
      setTimeout(fetchWorkerStatus, 1000)
  } else {
      isProcessing.value = false
      showVideo.value = true // Reset for next time
  }

  // start/stop detections polling only when this camera is processing and detection is enabled
  if (start && activeCamera.value?.detection_enabled) startPollingDetections()
  else stopPollingDetections()
}

// Utilities to detect YouTube and build embed URL
const getYouTubeEmbedUrl = (url) => {
  if (!url) return null
  try {
    const u = new URL(url)
    // youtu.be short link
    if (u.hostname === 'youtu.be') {
      const id = u.pathname.replace('/', '')
      return `https://www.youtube-nocookie.com/embed/${id}?autoplay=1`
    }
    // youtube.com watch?v=ID
    if (u.hostname.includes('youtube.com')) {
      const id = u.searchParams.get('v')
      if (id) return `https://www.youtube-nocookie.com/embed/${id}?autoplay=1`
      // Handle embed URL directly
      if (u.pathname.includes('/embed/')) {
        return url
      }
    }
  } catch (e) {
    return null
  }
  return null
}

const activeStreamUrl = computed(() => {
  if (!activeCamera.value) return null
  // If the camera has a YouTube URL, return its embed URL, unless detection is enabled
  // When detection is enabled, show the worker MJPEG annotated stream instead
  if (activeCamera.value.detection_enabled && isProcessing.value) {
    // By default, the worker exposes MJPEG at STREAM_URL, but we allow `camera_id` param just for clarity
    return `${STREAM_URL}?camera_id=${activeCamera.value.id}`
  }
  // If not detection-enabled, show the source (embed or static stream)
  const embed = getYouTubeEmbedUrl(activeCamera.value.url)
  if (embed) return embed
  // otherwise return the configured STREAM_URL for the service
  return STREAM_URL
})
const isYouTube = computed(() => {
  return !!activeStreamUrl.value && activeStreamUrl.value.includes('youtube')
})

onMounted(fetchCameras)

// Watchers to start/stop detection polling when camera changes or processing toggles
watch([activeCamera, isProcessing], ([newCam, processing]) => {
  if (!newCam) { stopPollingDetections(); return }
  if (processing && newCam?.detection_enabled) startPollingDetections()
  else stopPollingDetections()
})

// SSE subscription for real-time events (detections/alerts)
let eventSource = null
const initSSE = () => {
  if (!props.token) return
  // We pass the token as a query param since EventSource doesn't support Authorization header
  const url = `${API_URL.replace('/api', '')}/api/sse/stream?token=${encodeURIComponent(props.token)}`
  eventSource = new EventSource(url + '&_t=' + Math.random())
  eventSource.addEventListener('detections', (e) => {
    try {
      const data = JSON.parse(e.data)
      if (activeCamera.value && data.camera_id === activeCamera.value.id) {
        // push to detections
        detections.value.unshift(data)
        // limit length
        if (detections.value.length > 20) detections.value.pop()
      }
    } catch (e) {}
  })
  eventSource.addEventListener('alerts', (e) => {
    try { const payload = JSON.parse(e.data); alerts.value.unshift(payload); if (alerts.value.length>20) alerts.value.pop() } catch(e){}
  })
  eventSource.onopen = () => console.log('SSE connected')
  eventSource.onerror = (err) => { console.warn('SSE error', err); }
}
onMounted(() => { initSSE() })
onUnmounted(async () => { 
    if (eventSource) eventSource.close() 
    // Stop processing if background mode is disabled
    if (activeCamera.value && isProcessing.value && !runInBackground.value) {
        try {
            // Use sendBeacon or fetch (fetch might be cancelled on unload, but onUnmounted is Vue lifecycle)
            await fetch(`${API_URL}/camera/stop`, {
                method: 'POST', 
                headers: { 'Authorization': `Bearer ${props.token}`, 'Content-Type': 'application/json' }, 
                body: JSON.stringify({ id: activeCamera.value.id })
            })
        } catch(e) { console.error("Error stopping on unmount", e) }
    }
})
</script>

<template>
  <div class="dashboard-user control-center">
    <!-- Sidebar / Camera List -->
    <div class="sidebar">
      <div class="sidebar-header">
        <h3>Cámaras</h3>
        <button @click="showAdd = true" class="btn-icon" title="Añadir Cámara">+</button>
      </div>
      <div class="cam-list">
        <div v-for="cam in cameras" :key="cam.id" 
             class="cam-item" :class="{active: activeCamera?.id === cam.id}"
             @click="activeCamera = cam">
             <span class="status-dot" :class="{online: isCameraRunning(cam.id)}"></span>
             {{ cam.name }}
        </div>
      </div>
    </div>

    <!-- Main Content -->
    <div class="main-content" v-if="activeCamera">
      <header class="control-header">
        <div class="header-left">
          <h2>{{ activeCamera.name }}</h2>
          <span class="badge" :class="isProcessing ? 'badge-success' : 'badge-secondary'">
            {{ isProcessing ? (showVideo ? 'EN VIVO' : 'EN 2DO PLANO') : 'DETENIDO' }}
          </span>
        </div>
        <div class="header-actions">
          <template v-if="!isProcessing">
            <button @click="toggleAnalysis(true, false)" class="btn-start">
              <i class="icon">▶</i> Iniciar
            </button>
            <button @click="toggleAnalysis(true, true)" class="btn-secondary" title="Iniciar sin video">
              <i class="icon">⚡</i> 2do Plano
            </button>
          </template>
          <template v-else>
             <button @click="showVideo = !showVideo" class="btn-secondary">
              {{ showVideo ? 'Ocultar Video' : 'Ver Video' }}
            </button>
            <button @click="toggleAnalysis(false)" class="btn-stop">
              <i class="icon">⏹</i> Detener
            </button>
          </template>
        </div>
      </header>

      <div class="video-grid">
        <!-- Video Feed -->
        <div class="video-box">
            <iframe v-if="isProcessing && isYouTube && showVideo" :src="activeStreamUrl" frameborder="0" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen class="stream"></iframe>
            <div v-else-if="isProcessing && showVideo" class="stream-wrapper">
              <img :src="activeStreamUrl" class="stream" @load="onStreamLoad" @error="onStreamError" />
              <div v-if="streamLoadError" class="stream-error">
                <p>No se pudo cargar el stream.</p>
                <small>{{ streamErrorUrl }}</small>
              </div>
            </div>
            <div v-else class="placeholder">
              <div class="placeholder-content">
                <i class="icon-camera-off"></i>
                <p>{{ isProcessing ? 'Ejecutando en Segundo Plano' : 'Análisis Detenido' }}</p>
              </div>
            </div>
        </div>

        <!-- Control Panel (Right Side) -->
        <div class="control-panel">
          
          <!-- Settings Tab -->
          <div class="panel-section" v-if="user?.role === 'superadmin'">
            <h3>Configuración AI</h3>
            
            <div class="setting-group">
              <label class="switch">
                <input type="checkbox" v-model="activeCamera.detection_enabled">
                <span class="slider round"></span>
                <span class="label-text">Detección de Objetos</span>
              </label>
            </div>

            <div class="setting-group" v-if="activeCamera.detection_enabled">
              <label>Modelo</label>
              <select v-model="activeCamera.detection_model" class="dark-select">
                  <option value="yolov8n">YOLOv8 Nano (Rápido)</option>
                  <option value="yolov8s">YOLOv8 Small</option>
                  <option value="yolov8m">YOLOv8 Medium</option>
                  <option value="yolov8l">YOLOv8 Large (Preciso)</option>
                  <option value="yolo11n">YOLO11 Nano (Nuevo)</option>
                  <option value="yolo11s">YOLO11 Small</option>
                  <option value="yolo11m">YOLO11 Medium</option>
              </select>
            </div>

            <div class="setting-group" v-if="activeCamera.detection_enabled">
              <label>Clases a Detectar</label>
              <div class="multi-select-box">
                <label v-for="cls in availableClasses" :key="cls" class="checkbox-item">
                  <input type="checkbox" :value="cls" v-model="activeCamera.detection_classes">
                  {{ cls }}
                </label>
              </div>
            </div>

            <div class="setting-group">
              <label class="switch">
                <input type="checkbox" v-model="activeCamera.face_recognition_enabled">
                <span class="slider round"></span>
                <span class="label-text">Reconocimiento Facial (YuNet/SFace)</span>
              </label>
            </div>

            <div class="setting-group">
              <label class="switch">
                <input type="checkbox" v-model="activeCamera.depth_enabled">
                <span class="slider round"></span>
                <span class="label-text">Estimación de Profundidad (Depth Anything v2)</span>
              </label>
            </div>

            <div class="setting-group" v-if="activeCamera.depth_enabled">
              <label class="switch">
                <input type="checkbox" v-model="activeCamera.bev_enabled">
                <span class="slider round"></span>
                <span class="label-text">Vista de Pájaro (BEV)</span>
              </label>
            </div>

            <div class="setting-group">
              <label class="switch">
                <input type="checkbox" v-model="activeCamera.tracking">
                <span class="slider round"></span>
                <span class="label-text">Seguimiento (Tracking)</span>
              </label>
            </div>

             <div class="setting-group">
              <label class="switch">
                <input type="checkbox" v-model="runInBackground">
                <span class="slider round"></span>
                <span class="label-text">Ejecutar en 2do plano</span>
              </label>
            </div>

            <button @click="updateCameraSettings(activeCamera)" class="btn-save">Guardar Cambios</button>
          </div>

          <!-- Alerts Creator -->
          <div class="panel-section" v-if="user?.role === 'superadmin'">
            <h3>Crear Regla</h3>
            <div class="form-row">
              <input v-model="newAlertName" placeholder="Nombre" class="dark-input" />
              <input v-model.number="newAlertThreshold" placeholder="Umbral" type="number" step="0.1" class="dark-input small" />
            </div>
            <select v-model="newAlertEvent" class="dark-select">
              <option value="person_detected">Persona Detectada</option>
              <option value="car_detected">Vehículo Detectado</option>
              <option value="intrusion">Intrusión en Zona</option>
            </select>
            <button @click="createAlert(activeCamera, newAlertName, newAlertEvent, newAlertThreshold)" class="btn-action">Crear Alerta</button>
          </div>

        </div>
      </div>

      <!-- Bottom Panel: Logs & Alerts -->
      <div class="bottom-panel">
        <div class="panel-col">
          <h3>Alertas Recientes</h3>
          <ul class="log-list">
            <li v-for="a in alerts" :key="a.id" class="log-item alert">
              <span class="time">{{ new Date(a.created_at).toLocaleTimeString() }}</span>
              <span class="event">{{ a.event }}</span>
              <span class="details">{{ a.payload?.label }} ({{ (a.payload?.score * 100).toFixed(0) }}%)</span>
            </li>
          </ul>
        </div>
        <div class="panel-col">
          <h3>Detecciones en Vivo</h3>
          <ul class="log-list">
            <li v-for="d in detections" :key="d.id" class="log-item detection">
              <span class="time">{{ new Date(d.created_at).toLocaleTimeString() }}</span>
              <span class="event">{{ d.event }}</span>
              <span class="details">{{ d.payload?.label }}</span>
            </li>
          </ul>
        </div>
      </div>

    </div>
    
    <!-- Empty State -->
    <div v-else class="empty-state">
      <p>Seleccione una cámara para comenzar</p>
    </div>

    <!-- Add Camera Modal -->
    <div v-if="showAdd" class="modal-overlay">
        <div class="modal-box">
            <h3>Nueva Cámara</h3>
            <input v-model="newCam.name" placeholder="Nombre de la cámara" class="dark-input">
            <input v-model="newCam.url" placeholder="RTSP / HTTP / YouTube URL" class="dark-input">
            <div class="modal-actions">
              <button @click="showAdd = false" class="btn-cancel">Cancelar</button>
              <button @click="addCamera" class="btn-confirm">Guardar</button>
            </div>
        </div>
    </div>

  </div>
</template>

<style scoped>
/* Control Center Theme */
.control-center {
  display: flex;
  height: 100vh;
  background-color: #1a1a1a;
  color: #e0e0e0;
  font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  overflow: hidden;
}

/* Sidebar */
.sidebar {
  width: 250px;
  background-color: #252526;
  border-right: 1px solid #333;
  display: flex;
  flex-direction: column;
}
.sidebar-header {
  padding: 15px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #333;
}
.btn-icon {
  background: #333;
  border: none;
  color: white;
  width: 30px;
  height: 30px;
  border-radius: 4px;
  cursor: pointer;
}
.cam-list {
  flex: 1;
  overflow-y: auto;
}
.cam-item {
  padding: 12px 15px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 10px;
  border-bottom: 1px solid #2d2d2d;
  transition: background 0.2s;
}
.cam-item:hover { background-color: #2d2d2d; }
.cam-item.active { background-color: #37373d; border-left: 3px solid #007acc; }
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #666;
}
.status-dot.online { background-color: #4caf50; }

/* Main Content */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}
.control-header {
  padding: 15px 20px;
  background-color: #1e1e1e;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #333;
}
.header-left { display: flex; align-items: center; gap: 15px; }
.badge { padding: 4px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold; }
.badge-success { background-color: #1b5e20; color: #a5d6a7; }
.badge-secondary { background-color: #424242; color: #bdbdbd; }

.video-grid {
  display: grid;
  grid-template-columns: 1fr 300px;
  gap: 1px;
  background-color: #333;
  height: 60vh;
}
.video-box {
  background-color: #000;
  position: relative;
  display: flex;
  justify-content: center;
  align-items: center;
}
.stream-wrapper { width: 100%; height: 100%; position: relative; }
.stream { width: 100%; height: 100%; object-fit: contain; }
.placeholder { color: #666; text-align: center; }

/* Control Panel */
.control-panel {
  background-color: #252526;
  padding: 15px;
  overflow-y: auto;
  border-left: 1px solid #333;
}
.panel-section { margin-bottom: 25px; }
.panel-section h3 { font-size: 0.9rem; text-transform: uppercase; color: #888; margin-bottom: 10px; border-bottom: 1px solid #333; padding-bottom: 5px; }

.setting-group { margin-bottom: 15px; }
.setting-group label { display: block; margin-bottom: 5px; font-size: 0.9rem; }

/* Form Elements */
.dark-select, .dark-input {
  width: 100%;
  background-color: #3c3c3c;
  border: 1px solid #555;
  color: white;
  padding: 8px;
  border-radius: 4px;
}
.multi-select-box {
  height: 150px;
  overflow-y: auto;
  background-color: #1e1e1e;
  border: 1px solid #333;
  padding: 5px;
  border-radius: 4px;
}
.checkbox-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px;
  font-size: 0.9rem;
  cursor: pointer;
}
.checkbox-item:hover { background-color: #333; }

/* Switch */
.switch {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
}
.switch input { opacity: 0; width: 0; height: 0; }
.slider {
  position: relative;
  display: inline-block;
  width: 34px;
  height: 20px;
  background-color: #ccc;
  transition: .4s;
  border-radius: 34px;
}
.slider:before {
  position: absolute;
  content: "";
  height: 14px;
  width: 14px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  transition: .4s;
  border-radius: 50%;
}
input:checked + .slider { background-color: #2196F3; }
input:checked + .slider:before { transform: translateX(14px); }
.label-text { font-size: 0.9rem; }

/* Buttons */
.btn-save { width: 100%; background-color: #007acc; color: white; border: none; padding: 10px; border-radius: 4px; cursor: pointer; margin-top: 10px; }
.btn-save:hover { background-color: #005999; }
.btn-action { width: 100%; background-color: #444; color: white; border: none; padding: 8px; border-radius: 4px; cursor: pointer; margin-top: 10px; }
.btn-start { background-color: #2e7d32; color: white; border: none; padding: 8px 15px; border-radius: 4px; cursor: pointer; display: flex; align-items: center; gap: 5px; }
.btn-stop { background-color: #c62828; color: white; border: none; padding: 8px 15px; border-radius: 4px; cursor: pointer; display: flex; align-items: center; gap: 5px; }

/* Bottom Panel */
.bottom-panel {
  flex: 1;
  background-color: #1e1e1e;
  border-top: 1px solid #333;
  display: grid;
  grid-template-columns: 1fr 1fr;
  overflow: hidden;
}
.panel-col {
  padding: 15px;
  overflow-y: auto;
  border-right: 1px solid #333;
}
.log-list { list-style: none; padding: 0; margin: 0; }
.log-item {
  padding: 8px;
  border-bottom: 1px solid #333;
  font-size: 0.9rem;
  display: flex;
  gap: 10px;
}
.log-item .time { color: #888; font-family: monospace; }
.log-item .event { color: #4fc3f7; font-weight: bold; }
.log-item.alert .event { color: #ffb74d; }

/* Modal */
.modal-overlay { position: fixed; top:0; left:0; width:100%; height:100%; background: rgba(0,0,0,0.7); display: flex; justify-content: center; align-items: center; z-index: 1000; }
.modal-box { background: #252526; padding: 25px; border-radius: 8px; width: 400px; display: flex; flex-direction: column; gap: 15px; border: 1px solid #444; }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; }
.btn-confirm { background: #007acc; color: white; border: none; padding: 8px 15px; border-radius: 4px; cursor: pointer; }
.btn-cancel { background: transparent; color: #ccc; border: 1px solid #555; padding: 8px 15px; border-radius: 4px; cursor: pointer; }

.empty-state { display: flex; justify-content: center; align-items: center; height: 100%; color: #666; }
</style>