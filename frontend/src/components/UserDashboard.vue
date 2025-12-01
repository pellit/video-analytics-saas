<script setup>
import { ref, onMounted, computed, watch, nextTick, onUnmounted } from 'vue'
const props = defineProps(['token'])

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'
// Prefer explicit stream URL; fallback to computed from API URL to be compatible with existing setups
const STREAM_URL = import.meta.env.VITE_STREAM_URL || (import.meta.env.VITE_API_URL ? import.meta.env.VITE_API_URL.replace('/api', ':5000/video_feed') : 'http://192.168.0.38:5000/video_feed')

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
    const res = await fetch(`${API_URL}/cameras`, {
      method: 'POST', headers: { 'Authorization': `Bearer ${props.token}`, 'Content-Type': 'application/json' }, body: JSON.stringify(newCam.value)
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

const updateCameraSettings = async (camera) => {
  try {
    const res = await fetch(`${API_URL}/cameras/${camera.id}`, {
      method: 'PATCH', headers: { 'Authorization': `Bearer ${props.token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ detection_enabled: camera.detection_enabled, detection_model: camera.detection_model, tracking: camera.tracking })
    })
    if (!res.ok) {
      const body = await res.json().catch(() => null)
      alert('No se pudo actualizar configuración: ' + (body?.message || res.status))
    } else {
      alert('Configuración actualizada')
    }
  } catch (e) { console.error(e); alert('Error red al actualizar cámara') }
}

// Watch for camera changes to handle background processing preference
watch(activeCamera, async (newCam, oldCam) => {
    if (oldCam && isProcessing.value && !runInBackground.value) {
        console.log(`Stopping camera ${oldCam.id} (Background disabled)`)
        try {
            await fetch(`${API_URL}/camera/stop`, {
                method: 'POST', 
                headers: { 'Authorization': `Bearer ${props.token}`, 'Content-Type': 'application/json' }, 
                body: JSON.stringify({ id: oldCam.id })
            })
        } catch(e) { console.error("Error stopping camera", e) }
    }
    // Reset UI state for new camera (we assume stopped initially or user manually starts)
    isProcessing.value = false 
})

const createAlert = async (camera, name, event, threshold) => {
  try {
    const res = await fetch(`${API_URL}/alerts`, {
      method: 'POST', headers: { 'Authorization': `Bearer ${props.token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ camera_id: camera.id, name, event, threshold })
    })
    if (res.ok) { alert('Alerta creada') } else { alert('Error creando alerta') }
  } catch (e) { console.error(e); alert('Error de red al crear alerta') }
}

const alerts = ref([])
const fetchAlerts = async () => {
  try {
    const res = await fetch(`${API_URL}/alerts/recent`, { headers: { 'Authorization': `Bearer ${props.token}`, 'Accept': 'application/json' } })
    if (res.ok) alerts.value = await res.json()
  } catch (e) { console.error(e) }
}
setInterval(fetchAlerts, 5000)

// Detections polling
const detections = ref([])
const fetchDetections = async () => {
  if (!activeCamera.value) return
  try {
    const res = await fetch(`${API_URL}/cameras/${activeCamera.value.id}/detections`, { headers: { 'Authorization': `Bearer ${props.token}` } })
    if (res.ok) detections.value = await res.json()
  } catch (e) { console.error('fetchDetections error', e) }
}
let detectionsInterval = null
const startPollingDetections = () => {
  fetchDetections()
  detectionsInterval = setInterval(fetchDetections, 2000)
}
const stopPollingDetections = () => {
  if (detectionsInterval) clearInterval(detectionsInterval)
  detections.value = []
}

// Canvas overlay drawing
const streamImg = ref(null)
const overlayCanvas = ref(null)
let imgNaturalW = 0
let imgNaturalH = 0

const streamLoadError = ref(false)
const onStreamLoad = (e) => {
  imgNaturalW = e.target.naturalWidth
  imgNaturalH = e.target.naturalHeight
  // set canvas size to actual image pixel size for correct scaling
  const canvas = overlayCanvas.value
  if (canvas) {
    canvas.width = imgNaturalW
    canvas.height = imgNaturalH
    drawDetections()
  }
}

const onStreamError = (e) => {
  console.error('Stream load error', e)
  streamLoadError.value = true
  // Hide processing flag if it was on; keep camera active so user can try again
  isProcessing.value = false
}

const drawDetections = () => {
  const canvas = overlayCanvas.value
  const img = streamImg.value
  if (!canvas || !img || detections.value.length === 0) {
    if (canvas) {
      const ctx = canvas.getContext('2d')
      ctx.clearRect(0,0,canvas.width, canvas.height)
    }
    return
  }
  const ctx = canvas.getContext('2d')
  // scale to displayed size
  // Use natural pixel coordinates since canvas matches natural size
  const scaleX = 1
  const scaleY = 1
  ctx.clearRect(0,0,canvas.width, canvas.height)
  ctx.strokeStyle = 'lime'
  ctx.lineWidth = 3
  ctx.font = '18px Arial'
  ctx.fillStyle = 'lime'
  for (const d of detections.value) {
    const bbox = d.payload?.bbox || d.payload?.bbox || []
    if (!bbox || bbox.length < 4) continue
    const [x1, y1, x2, y2] = bbox
    const w = (x2 - x1)
    const h = (y2 - y1)
    ctx.strokeRect(x1, y1, w, h)
    ctx.fillText(`${d.payload?.label || d.event} (${Math.round((d.payload?.score||0)*100)}%)`, x1 + 5, y1 + 20)
  }
}

watch(detections, () => {
  // redraw overlay when detections change
  nextTick(() => drawDetections())
})

const toggleAnalysis = async (start) => {
  const endpoint = start ? 'start' : 'stop'
  await fetch(`${API_URL}/camera/${endpoint}`, {
    method: 'POST', headers: { 'Authorization': `Bearer ${props.token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ id: activeCamera.value.id, url: activeCamera.value.url })
  })
  isProcessing.value = start
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
  <div class="dashboard-user">
    <div class="cam-bar">
        <div v-for="cam in cameras" :key="cam.id" 
             class="cam-chip" :class="{active: activeCamera?.id === cam.id}"
             @click="activeCamera = cam; isProcessing = false">
             {{ cam.name }}
        </div>
        <button @click="showAdd = true" class="btn-add">+</button>
    </div>

    <div v-if="showAdd" class="modal">
        <div class="modal-content">
            <h3>Nueva Cámara</h3>
            <input v-model="newCam.name" placeholder="Nombre">
            <input v-model="newCam.url" placeholder="URL">
            <button @click="addCamera">Guardar</button>
            <button @click="showAdd = false">Cancelar</button>
        </div>
    </div>

    <div v-if="activeCamera" class="video-section">
        <header>
            <h2>{{ activeCamera.name }}</h2>
            <div class="header-actions">
              <button v-if="!isProcessing" @click="toggleAnalysis(true)" class="btn-start">▶ Iniciar</button>
            <button v-else @click="toggleAnalysis(false)" class="btn-stop">⏹ Detener</button>
              <div v-if="user?.role === 'superadmin'" class="camera-settings">
                  <label><input type="checkbox" v-model="activeCamera.detection_enabled" /> Detección</label>
                  <select v-model="activeCamera.detection_model">
                      <option value="yolov8n">yolov8n</option>
                      <option value="yolov8s">yolov8s</option>
                      <option value="yolov8m">yolov8m</option>
                      <option value="yolov8l">yolov8l</option>
                  </select>
                  <label><input type="checkbox" v-model="activeCamera.tracking" /> Seguimiento</label>
                  <label title="Si está desactivado, el análisis se detendrá al cambiar de cámara o salir"><input type="checkbox" v-model="runInBackground" /> Background</label>
                  <button @click="updateCameraSettings(activeCamera)">Guardar Config</button>
              </div>
            </div>
        </header>
        <div v-if="user?.role === 'superadmin'" class="alert-creator">
          <input v-model="newAlertName" placeholder="Nombre alerta" />
          <select v-model="newAlertEvent">
            <option value="person_detected">person_detected</option>
            <option value="car_detected">car_detected</option>
          </select>
          <input v-model.number="newAlertThreshold" placeholder="Umbral (0-1)" type="number" min="0" max="1" step="0.01" />
          <button @click="createAlert(activeCamera, newAlertName, newAlertEvent, newAlertThreshold)">Crear Alerta</button>
        </div>
        <div class="video-box">
            <iframe v-if="isProcessing && isYouTube" :src="activeStreamUrl" frameborder="0" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen class="stream"></iframe>
            <div v-else-if="isProcessing" class="stream" style="position: relative; width: 100%; height: 100%;">
              <img ref="streamImg" :src="activeStreamUrl" class="stream" @load="onStreamLoad" @error="onStreamError" style="position: absolute; left:0; top:0; width:100%; height:100%; object-fit: contain;" />
              <canvas ref="overlayCanvas" class="overlay-canvas" style="position: absolute; left:0; top:0; width:100%; height:100%; pointer-events: none;"></canvas>
              <div v-if="streamLoadError" class="stream-error">No se pudo cargar el stream. Verifica que el worker esté corriendo y que la cámara esté activa.</div>
            </div>
            <div v-else class="placeholder">Stream Inactivo</div>
        </div>
    </div>
    <div class="alerts-panel">
      <h3>Alertas recientes</h3>
      <ul>
        <li v-for="a in alerts" :key="a.id">{{ new Date(a.created_at).toLocaleTimeString() }} - {{ a.event }} en cam {{ a.camera_id }} ({{ a.payload?.label }}:{{ a.payload?.score }})</li>
      </ul>
    </div>
        <div class="detections-panel" v-if="detections.length > 0">
          <h3>Detections (últimos)</h3>
          <ul>
            <li v-for="d in detections" :key="d.id">{{ new Date(d.created_at).toLocaleTimeString() }} - {{ d.event }} - {{ d.payload?.label }} ({{ d.payload?.score }})</li>
          </ul>
        </div>
  </div>
</template>

<style scoped>
.cam-bar { display: flex; gap: 10px; padding-bottom: 20px; overflow-x: auto; }
.cam-chip { background: white; padding: 8px 15px; border-radius: 20px; cursor: pointer; border: 1px solid #ddd; }
.cam-chip.active { background: #7367f0; color: white; border-color: #7367f0; }
.video-box { background: black; height: 400px; display: flex; justify-content: center; align-items: center; color: white; border-radius: 10px; overflow: hidden; }
.stream { height: 100%; width: 100%; object-fit: contain; }
.stream-error { position:absolute; left:0; top:0; right:0; bottom:0; display:flex; justify-content:center; align-items:center; background:rgba(0,0,0,0.6); color:#fff; z-index:10; }
.btn-start { background: #28c76f; color: white; padding: 8px 20px; border: none; border-radius: 5px; cursor: pointer; }
.btn-stop { background: #ea5455; color: white; padding: 8px 20px; border: none; border-radius: 5px; cursor: pointer; }
header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.modal { position: fixed; top:0; left:0; width:100%; height:100%; background: rgba(0,0,0,0.5); display: flex; justify-content: center; align-items: center; }
.modal-content { background: white; padding: 20px; display: flex; flex-direction: column; gap: 10px; border-radius: 8px; }
</style>