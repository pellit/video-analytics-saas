<script setup>
import { ref, onMounted, computed, watch, nextTick, onUnmounted } from 'vue'
import NavBar from './NavBar.vue'
import FaceRecognitionPanel from './FaceRecognitionPanel.vue'
import ToastNotification from './ToastNotification.vue'

const props = defineProps(['token', 'user'])
const emit = defineEmits(['logout', 'navigate'])

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

// COCO Classes for Multi-select (defined early for use in initializeCameraDefaults)
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

const cameras = ref([])
const activeCamera = ref(null)
const isProcessing = ref(false)
const showAdd = ref(false)
const newCam = ref({ name: '', url: '' })
const showFacePanel = ref(false) // Face recognition panel visibility

// Fullscreen HUD mode
const isFullscreen = ref(false)
const fullscreenStats = ref({
  fps: 0,
  objectsDetected: 0,
  personsCount: 0,
  vehiclesCount: 0,
  facesCount: 0,
  nearestDistance: null,
  uptime: 0,
  alertsCount: 0
})

// Toggle fullscreen HUD mode
const toggleFullscreen = () => {
  console.log('toggleFullscreen called, current:', isFullscreen.value)
  isFullscreen.value = !isFullscreen.value
  if (isFullscreen.value) {
    document.body.style.overflow = 'hidden'
  } else {
    document.body.style.overflow = ''
  }
  console.log('toggleFullscreen done, new:', isFullscreen.value)
}

// Exit fullscreen on Escape key
const handleKeydown = (e) => {
  if (e.key === 'Escape' && isFullscreen.value) {
    toggleFullscreen()
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
  document.body.style.overflow = ''
})

// Toast notification state
const toast = ref({ show: false, message: '', type: 'success' })
const showToast = (message, type = 'success') => {
  toast.value = { show: true, message, type }
}
const closeToast = () => {
  toast.value.show = false
}

// Settings panel accordion state
const settingsSection = ref('detection') // 'detection', 'face', 'advanced', 'alerts'

// Update fullscreen stats from detections
const updateFullscreenStats = (detection) => {
  const label = detection.event || detection.label || ''
  
  // Count by type
  if (label.toLowerCase().includes('person')) {
    fullscreenStats.value.personsCount++
  }
  if (['car', 'truck', 'bus', 'motorcycle', 'bicycle'].some(v => label.toLowerCase().includes(v))) {
    fullscreenStats.value.vehiclesCount++
  }
  if (label.toLowerCase().includes('face')) {
    fullscreenStats.value.facesCount++
  }
  
  fullscreenStats.value.objectsDetected = detections.value?.length || 0
  fullscreenStats.value.alertsCount = alerts.value?.length || 0
  
  // Update nearest distance from BEV
  if (detection.bev_data?.nearest_distance) {
    fullscreenStats.value.nearestDistance = detection.bev_data.nearest_distance
  }
}

// Initialize detection_classes with all available classes if null/empty
const initializeCameraDefaults = (camera) => {
  if (!camera.detection_classes || camera.detection_classes.length === 0) {
    camera.detection_classes = [...availableClasses]
  }
  // Ensure boolean fields have proper defaults
  camera.detection_enabled = camera.detection_enabled ?? false
  camera.face_recognition_enabled = camera.face_recognition_enabled ?? false
  camera.depth_enabled = camera.depth_enabled ?? false
  camera.bev_enabled = camera.bev_enabled ?? false
  camera.tracking = camera.tracking ?? false
  return camera
}


const fetchCameras = async () => {
  try {
    const res = await fetch(`${API_URL}/cameras`, { headers: { 'Authorization': `Bearer ${props.token}`, 'Accept': 'application/json' } })
    if (res.ok) {
        const data = await res.json()
        // Initialize defaults for all cameras
        cameras.value = data.map(initializeCameraDefaults)
        if (cameras.value.length > 0) activeCamera.value = cameras.value[0]
    } else {
        if (res.status === 401) {
            showToast('Sesión expirada. Por favor inicie sesión nuevamente.', 'error')
            emit('logout')
            return
        }
        const body = await res.json().catch(() => null)
        console.error('Error fetching cameras', res.status, body)
        showToast(body?.message || 'No se pudieron cargar las cámaras', 'error')
    }
  } catch (e) {
    console.error(e)
    showToast('Error de red al cargar cámaras', 'error')
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
      showToast(data?.message || 'No se pudo crear la cámara', 'error')
      return
    }
    showToast('Cámara creada correctamente', 'success')
    showAdd.value = false; newCam.value = { name: '', url: '' }; fetchCameras()
  } catch (e) {
    console.error(e)
    showToast('Error de red al crear la cámara', 'error')
  }
}

// New alert form state
const newAlertName = ref('Auto Alert')
const newAlertEvent = ref('person_detected')
const newAlertThreshold = ref(0.5)
const runInBackground = ref(true) // Default: Keep running in background

// BEV (Bird's Eye View) state
const bevCanvas = ref(null)
const bevData = ref({
  objects: [],
  nearestDistance: Infinity,
  gridSize: 10 // metros que representa el canvas
})

// Función para dibujar el BEV en el canvas
const drawBEV = () => {
  if (!bevCanvas.value) return
  const canvas = bevCanvas.value
  const ctx = canvas.getContext('2d')
  const w = canvas.width
  const h = canvas.height
  const gridSize = bevData.value.gridSize // metros totales
  const scale = w / gridSize // pixels por metro
  
  // Limpiar canvas
  ctx.fillStyle = '#1e1e1e'
  ctx.fillRect(0, 0, w, h)
  
  // Dibujar grid con medidas
  ctx.strokeStyle = '#333'
  ctx.lineWidth = 1
  ctx.font = '10px Arial'
  ctx.fillStyle = '#666'
  
  // Líneas verticales y horizontales cada metro
  for (let i = 0; i <= gridSize; i++) {
    const pos = i * scale
    // Vertical
    ctx.beginPath()
    ctx.moveTo(pos, 0)
    ctx.lineTo(pos, h)
    ctx.stroke()
    // Horizontal
    ctx.beginPath()
    ctx.moveTo(0, pos)
    ctx.lineTo(w, pos)
    ctx.stroke()
    // Etiquetas de medida
    if (i > 0 && i < gridSize) {
      ctx.fillText(`${i}m`, pos + 2, h - 5)
      ctx.fillText(`${i}m`, 2, h - pos - 2)
    }
  }
  
  // Dibujar posición de la cámara (abajo centro)
  ctx.fillStyle = '#4a90d9'
  ctx.beginPath()
  ctx.moveTo(w / 2, h - 10)
  ctx.lineTo(w / 2 - 8, h)
  ctx.lineTo(w / 2 + 8, h)
  ctx.closePath()
  ctx.fill()
  ctx.fillStyle = '#4a90d9'
  ctx.font = '11px Arial'
  ctx.fillText('📷 Cámara', w / 2 - 25, h - 15)
  
  // Dibujar círculos de distancia de referencia
  ctx.strokeStyle = '#444'
  ctx.setLineDash([5, 5])
  for (let dist of [3, 6, 9]) {
    if (dist <= gridSize) {
      ctx.beginPath()
      ctx.arc(w / 2, h, dist * scale, Math.PI, 0)
      ctx.stroke()
      ctx.fillStyle = '#555'
      ctx.fillText(`${dist}m`, w / 2 + dist * scale + 3, h - 5)
    }
  }
  ctx.setLineDash([])
  
  // Dibujar objetos detectados
  bevData.value.objects.forEach((obj, idx) => {
    const x = w / 2 + (obj.x * scale)  // x relativo al centro
    const y = h - (obj.distance * scale)  // y desde abajo (cámara)
    
    // Color según distancia
    let color = '#ff4444' // cerca (rojo)
    if (obj.distance > 6) color = '#44ff44' // lejos (verde)
    else if (obj.distance > 3) color = '#ffaa44' // medio (naranja)
    
    // Dibujar punto
    ctx.fillStyle = color
    ctx.beginPath()
    ctx.arc(x, y, 8, 0, Math.PI * 2)
    ctx.fill()
    
    // Dibujar etiqueta
    ctx.fillStyle = '#fff'
    ctx.font = 'bold 10px Arial'
    const label = obj.trackId ? `#${obj.trackId}` : obj.label.substring(0, 3)
    ctx.fillText(label, x - 8, y - 12)
    
    // Dibujar distancia
    ctx.font = '9px Arial'
    ctx.fillStyle = '#aaa'
    ctx.fillText(`${obj.distance.toFixed(1)}m`, x - 10, y + 18)
  })
}

// Procesar datos de BEV desde detecciones
const processBEVData = (detection) => {
  if (!detection.bev_data) return
  
  bevData.value.objects = detection.bev_data.objects || []
  bevData.value.nearestDistance = detection.bev_data.nearest_distance || Infinity
  
  nextTick(() => drawBEV())
}

// Polling detections stub functions (now handled by SSE, kept for compatibility)
let pollingInterval = null
const startPollingDetections = () => {
  // Detections are now received via SSE, but we can keep this as a fallback
  // or simply do nothing since SSE handles real-time updates
  console.log('Detection polling: using SSE for real-time updates')
}
const stopPollingDetections = () => {
  if (pollingInterval) {
    clearInterval(pollingInterval)
    pollingInterval = null
  }
}

const isSaving = ref(false)

// Funciones para seleccionar/deseleccionar todas las clases
const selectAllClasses = () => {
  if (activeCamera.value) {
    activeCamera.value.detection_classes = [...availableClasses]
  }
}

const deselectAllClasses = () => {
  if (activeCamera.value) {
    activeCamera.value.detection_classes = []
  }
}

const updateCameraSettings = async (camera) => {
  if (isSaving.value) return
  isSaving.value = true
  
  const wasProcessing = isProcessing.value
  
  try {
    // Si está procesando, detener primero para aplicar cambios
    if (wasProcessing) {
      console.log('Deteniendo stream para aplicar cambios...')
      await fetch(`${API_URL}/camera/stop`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${props.token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: camera.id })
      })
      isProcessing.value = false
      // Pequeña pausa para que el worker se detenga
      await new Promise(resolve => setTimeout(resolve, 500))
    }
    
    const payload = { 
      detection_enabled: camera.detection_enabled, 
      detection_model: camera.detection_model, 
      detection_classes: camera.detection_classes,
      face_recognition_enabled: camera.face_recognition_enabled,
      depth_enabled: camera.depth_enabled,
      bev_enabled: camera.bev_enabled,
      tracking: camera.tracking 
    }
    
    console.log('Guardando configuración:', payload)
    
    const res = await fetch(`${API_URL}/cameras/${camera.id}`, {
      method: 'PATCH', 
      headers: { 
        'Authorization': `Bearer ${props.token}`, 
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify(payload)
    })
    
    if (!res.ok) {
      const body = await res.json().catch(() => null)
      console.error('Error response:', res.status, body)
      showToast('No se pudo actualizar configuración: ' + (body?.message || body?.error || `Error ${res.status}`), 'error')
      // Recargar cámaras para restaurar estado original
      await fetchCameras()
      return
    }
    
    const updatedCamera = await res.json()
    // Actualizar la cámara local con los datos del servidor
    Object.assign(camera, initializeCameraDefaults(updatedCamera))
    
    showToast('Configuración actualizada correctamente', 'success')
    
    // Si estaba procesando, reiniciar con nueva configuración
    if (wasProcessing) {
      console.log('Reiniciando stream con nueva configuración...')
      await fetch(`${API_URL}/camera/start`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${props.token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: camera.id })
      })
      isProcessing.value = true
      setTimeout(fetchWorkerStatus, 1000)
    }
    
  } catch (e) { 
    console.error('Error de red:', e)
    showToast('Error de red al actualizar cámara. Verifique la conexión.', 'error')
    // Recargar cámaras para restaurar estado original
    await fetchCameras()
  } finally {
    isSaving.value = false
  }
}

const detections = ref([]) // Store detections received via SSE
const alerts = ref([]) // Store alerts received via SSE
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
      showToast('Sesión expirada. Por favor inicie sesión nuevamente.', 'error')
      emit('logout')
      return
  }

  if (!res.ok) {
      const body = await res.json().catch(() => null)
      showToast('Error al cambiar estado: ' + (body?.message || res.status), 'error')
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
        
        // Procesar datos BEV si están presentes
        if (data.bev_data) {
          processBEVData(data)
        }
        
        // Update fullscreen stats
        updateFullscreenStats(data)
      }
    } catch (e) {}
  })
  // Listener específico para eventos BEV
  eventSource.addEventListener('bev', (e) => {
    try {
      const data = JSON.parse(e.data)
      if (activeCamera.value && data.camera_id === activeCamera.value.id) {
        processBEVData(data)
      }
    } catch (e) {}
  })
  eventSource.addEventListener('alerts', (e) => {
    try { const payload = JSON.parse(e.data); alerts.value.unshift(payload); if (alerts.value.length>20) alerts.value.pop() } catch(e){}
  })
  // Debug SSE - descomentar si necesitas depurar conexión SSE
  // eventSource.onopen = () => console.log('SSE connected')
  // eventSource.onerror = (err) => { console.warn('SSE error', err); }
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

// Alerts/notifications for navbar
const navNotifications = computed(() => {
  return alerts.value.slice(0, 10).map((a, i) => ({
    id: i,
    message: a.message || `${a.camera_name}: ${a.type}`,
    time: a.created_at ? new Date(a.created_at).toLocaleTimeString() : 'Ahora',
    type: 'alert',
    read: false
  }))
})

// Count of running cameras for navbar
const runningCamerasCount = computed(() => {
  return cameras.value.filter(cam => isCameraRunning(cam.id)).length
})

// Profile modal state
const showProfileModal = ref(false)
const profileForm = ref({
  name: '',
  email: ''
})

const openProfileModal = () => {
  profileForm.value.name = props.user?.name || ''
  profileForm.value.email = props.user?.email || ''
  showProfileModal.value = true
}

const closeProfileModal = () => {
  showProfileModal.value = false
}

const saveProfile = async () => {
  // TODO: Implement profile update API call
  showToast('Perfil actualizado (pendiente implementar)', 'info')
  closeProfileModal()
}
</script>

<template>
  <div class="app-layout">
    <!-- Toast Notification -->
    <ToastNotification 
      :show="toast.show" 
      :message="toast.message" 
      :type="toast.type"
      @close="closeToast"
    />

    <!-- NavBar Component -->
    <NavBar 
      :user="user" 
      :notifications="navNotifications"
      :cameras-online="runningCamerasCount"
      current-view="dashboard"
      @logout="emit('logout')"
      @openProfile="showProfileModal = true"
      @navigate="(view) => emit('navigate', view)"
    />
    
    <div class="dashboard-user control-center">
      <!-- Sidebar / Camera List -->
      <div class="sidebar">
        <div class="sidebar-header">
          <h3>🎥 Cámaras</h3>
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
        <div class="video-box" @dblclick="toggleFullscreen" :title="isProcessing ? 'Doble clic para pantalla completa' : ''">
            <iframe v-if="isProcessing && isYouTube && showVideo" :src="activeStreamUrl" frameborder="0" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen class="stream"></iframe>
            <div v-else-if="isProcessing && showVideo" class="stream-wrapper" @dblclick.stop="toggleFullscreen">
              <img :src="activeStreamUrl" class="stream" @load="onStreamLoad" @error="onStreamError" @dblclick.stop="toggleFullscreen" />
              <div v-if="streamLoadError" class="stream-error">
                <p>No se pudo cargar el stream.</p>
                <small>{{ streamErrorUrl }}</small>
              </div>
              <!-- Fullscreen hint -->
              <div class="fullscreen-hint" v-if="!isFullscreen">
                <span>⛶ Doble clic para HUD</span>
              </div>
            </div>
            <div v-else class="placeholder" @dblclick.stop="toggleFullscreen">
              <div class="placeholder-content">
                <i class="icon-camera-off"></i>
                <p>{{ isProcessing ? 'Ejecutando en Segundo Plano' : 'Análisis Detenido' }}</p>
              </div>
            </div>
        </div>

        <!-- Control Panel (Right Side) -->
        <div class="control-panel" v-if="user?.role === 'superadmin'">
          
          <!-- Accordion Settings -->
          <div class="settings-accordion">
            
            <!-- Detection Section -->
            <div class="accordion-item" :class="{ open: settingsSection === 'detection' }">
              <button class="accordion-header" @click="settingsSection = settingsSection === 'detection' ? '' : 'detection'">
                <span class="accordion-icon">🎯</span>
                <span class="accordion-title">Detección</span>
                <span class="accordion-status" :class="{ active: activeCamera?.detection_enabled }">
                  {{ activeCamera?.detection_enabled ? 'ON' : 'OFF' }}
                </span>
                <span class="accordion-arrow">{{ settingsSection === 'detection' ? '▲' : '▼' }}</span>
              </button>
              <div class="accordion-content" v-show="settingsSection === 'detection'">
                <div class="setting-row">
                  <label class="toggle-switch">
                    <input type="checkbox" v-model="activeCamera.detection_enabled">
                    <span class="toggle-slider"></span>
                  </label>
                  <span class="setting-label">Activar detección</span>
                </div>
                
                <div v-if="activeCamera.detection_enabled" class="nested-settings">
                  <div class="setting-row">
                    <label class="setting-label">Modelo AI</label>
                    <select v-model="activeCamera.detection_model" class="compact-select">
                      <option value="onnx">⚡ ONNX (Rápido)</option>
                      <option value="yolo_nas_s">YOLO-NAS S</option>
                      <option value="yolo_nas_m">YOLO-NAS M</option>
                      <option value="rt_detr">RT-DETR</option>
                    </select>
                  </div>
                  
                  <div class="setting-row classes-row">
                    <div class="classes-header">
                      <span class="setting-label">Clases</span>
                      <span class="class-badge">{{ activeCamera.detection_classes?.length || 0 }}/{{ availableClasses.length }}</span>
                    </div>
                    <div class="class-buttons">
                      <button type="button" @click="selectAllClasses" class="btn-mini">Todas</button>
                      <button type="button" @click="deselectAllClasses" class="btn-mini ghost">Ninguna</button>
                    </div>
                  </div>
                  <div class="classes-grid">
                    <label v-for="cls in availableClasses" :key="cls" class="class-chip" :class="{ selected: activeCamera.detection_classes?.includes(cls) }">
                      <input type="checkbox" :value="cls" v-model="activeCamera.detection_classes" hidden>
                      {{ cls }}
                    </label>
                  </div>
                </div>
              </div>
            </div>

            <!-- Face Recognition Section -->
            <div class="accordion-item" :class="{ open: settingsSection === 'face' }">
              <button class="accordion-header" @click="settingsSection = settingsSection === 'face' ? '' : 'face'">
                <span class="accordion-icon">👤</span>
                <span class="accordion-title">Reconocimiento Facial</span>
                <span class="accordion-status" :class="{ active: activeCamera?.face_recognition_enabled }">
                  {{ activeCamera?.face_recognition_enabled ? 'ON' : 'OFF' }}
                </span>
                <span class="accordion-arrow">{{ settingsSection === 'face' ? '▲' : '▼' }}</span>
              </button>
              <div class="accordion-content" v-show="settingsSection === 'face'">
                <div class="setting-row">
                  <label class="toggle-switch">
                    <input type="checkbox" v-model="activeCamera.face_recognition_enabled">
                    <span class="toggle-slider"></span>
                  </label>
                  <span class="setting-label">Activar reconocimiento</span>
                </div>
                <button 
                  v-if="activeCamera.face_recognition_enabled" 
                  @click="showFacePanel = !showFacePanel"
                  class="btn-faces"
                >
                  {{ showFacePanel ? '✕ Cerrar Panel' : '👤 Gestionar Caras' }}
                </button>
              </div>
            </div>

            <!-- Advanced Section -->
            <div class="accordion-item" :class="{ open: settingsSection === 'advanced' }">
              <button class="accordion-header" @click="settingsSection = settingsSection === 'advanced' ? '' : 'advanced'">
                <span class="accordion-icon">⚙️</span>
                <span class="accordion-title">Avanzado</span>
                <span class="accordion-arrow">{{ settingsSection === 'advanced' ? '▲' : '▼' }}</span>
              </button>
              <div class="accordion-content" v-show="settingsSection === 'advanced'">
                <div class="setting-row">
                  <label class="toggle-switch">
                    <input type="checkbox" v-model="activeCamera.depth_enabled">
                    <span class="toggle-slider"></span>
                  </label>
                  <span class="setting-label">Profundidad (Depth)</span>
                </div>
                
                <div class="setting-row" v-if="activeCamera.depth_enabled">
                  <label class="toggle-switch">
                    <input type="checkbox" v-model="activeCamera.bev_enabled">
                    <span class="toggle-slider"></span>
                  </label>
                  <span class="setting-label">Vista Aérea (BEV)</span>
                </div>
                
                <div class="setting-row">
                  <label class="toggle-switch">
                    <input type="checkbox" v-model="activeCamera.tracking">
                    <span class="toggle-slider"></span>
                  </label>
                  <span class="setting-label">Tracking</span>
                </div>
                
                <div class="setting-row">
                  <label class="toggle-switch">
                    <input type="checkbox" v-model="runInBackground">
                    <span class="toggle-slider"></span>
                  </label>
                  <span class="setting-label">Ejecutar en 2do plano</span>
                </div>
              </div>
            </div>

            <!-- Alerts Section -->
            <div class="accordion-item" :class="{ open: settingsSection === 'alerts' }">
              <button class="accordion-header" @click="settingsSection = settingsSection === 'alerts' ? '' : 'alerts'">
                <span class="accordion-icon">🔔</span>
                <span class="accordion-title">Crear Alerta</span>
                <span class="accordion-arrow">{{ settingsSection === 'alerts' ? '▲' : '▼' }}</span>
              </button>
              <div class="accordion-content" v-show="settingsSection === 'alerts'">
                <div class="alert-form">
                  <input v-model="newAlertName" placeholder="Nombre de la alerta" class="form-input" />
                  <select v-model="newAlertEvent" class="form-input">
                    <option value="person_detected">Persona Detectada</option>
                    <option value="car_detected">Vehículo Detectado</option>
                    <option value="intrusion">Intrusión en Zona</option>
                  </select>
                  <div class="threshold-row">
                    <label>Umbral</label>
                    <input v-model.number="newAlertThreshold" type="number" step="0.1" min="0" max="1" class="form-input small" />
                  </div>
                  <button @click="createAlert(activeCamera, newAlertName, newAlertEvent, newAlertThreshold)" class="btn-create-alert">
                    + Crear Alerta
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- Save Button -->
          <div class="save-section">
            <button @click="updateCameraSettings(activeCamera)" class="btn-save-main" :disabled="isSaving">
              <span v-if="isSaving" class="spinner-small"></span>
              {{ isSaving ? 'Guardando...' : '💾 Guardar Cambios' }}
            </button>
            <p v-if="isProcessing" class="save-hint">El stream se reiniciará al guardar</p>
          </div>
        </div>
      </div>

      <!-- Bottom Panel: Logs, Alerts & BEV -->
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
        <!-- BEV Panel -->
        <div class="panel-col bev-panel" v-if="activeCamera?.depth_enabled && activeCamera?.bev_enabled">
          <h3>Vista de Pájaro (BEV)</h3>
          <div class="bev-container">
            <canvas ref="bevCanvas" width="300" height="300" class="bev-canvas"></canvas>
            <div class="bev-legend">
              <div class="legend-item"><span class="dot near"></span> 0-3m</div>
              <div class="legend-item"><span class="dot mid"></span> 3-6m</div>
              <div class="legend-item"><span class="dot far"></span> 6m+</div>
            </div>
            <div class="bev-stats" v-if="bevData.objects.length > 0">
              <p>Objetos: {{ bevData.objects.length }}</p>
              <p>Más cercano: {{ bevData.nearestDistance.toFixed(1) }}m</p>
            </div>
          </div>
        </div>
        <div class="panel-col bev-panel bev-disabled" v-else-if="activeCamera">
          <h3>Vista de Pájaro (BEV)</h3>
          <div class="bev-placeholder">
            <p>🦅 Activa "Estimación de Profundidad" y "Vista de Pájaro" en la configuración para ver el mapa BEV</p>
          </div>
        </div>
        
        <!-- Face Recognition Panel -->
        <div class="panel-col face-panel" v-if="showFacePanel && activeCamera?.face_recognition_enabled">
          <FaceRecognitionPanel
            :token="token"
            :camera-id="activeCamera?.id"
            :enabled="activeCamera?.face_recognition_enabled && isProcessing"
            @close="showFacePanel = false"
          />
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

    <!-- Profile Modal -->
    <Transition name="modal-fade">
      <div v-if="showProfileModal" class="modal-overlay" @click.self="closeProfileModal">
        <div class="modal-box profile-modal">
          <div class="modal-header">
            <h3>👤 Editar Perfil</h3>
            <button class="close-btn" @click="closeProfileModal">&times;</button>
          </div>
          
          <div class="profile-avatar-section">
            <div class="profile-avatar-large">
              {{ user?.name?.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2) || '?' }}
            </div>
            <span class="profile-role-badge">{{ user?.role === 'superadmin' ? '👑 Super Admin' : user?.role === 'admin' ? '⭐ Admin' : '👤 Usuario' }}</span>
          </div>
          
          <div class="profile-form">
            <div class="form-group">
              <label>Nombre</label>
              <input v-model="profileForm.name" type="text" class="dark-input" placeholder="Tu nombre">
            </div>
            <div class="form-group">
              <label>Email</label>
              <input v-model="profileForm.email" type="email" class="dark-input" placeholder="tu@email.com">
            </div>
            <div class="form-group">
              <label>Nueva Contraseña (dejar vacío para no cambiar)</label>
              <input v-model="profileForm.password" type="password" class="dark-input" placeholder="••••••••">
            </div>
          </div>
          
          <div class="modal-actions">
            <button @click="closeProfileModal" class="btn-cancel">Cancelar</button>
            <button @click="saveProfile" class="btn-confirm">
              <span>💾</span> Guardar Cambios
            </button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- Fullscreen HUD Overlay -->
    <Transition name="fade">
      <div v-if="isFullscreen && isProcessing" class="hud-overlay" @dblclick="toggleFullscreen">
        <!-- Video Background -->
        <img :src="activeStreamUrl" class="hud-video" />
        
        <!-- Close Button -->
        <button class="hud-close" @click.stop="toggleFullscreen">✕</button>
        
        <!-- Top Bar - Camera Info -->
        <div class="hud-top-bar">
          <div class="hud-camera-info">
            <span class="hud-camera-name">{{ activeCamera?.name }}</span>
            <span class="hud-status live">● EN VIVO</span>
          </div>
          <div class="hud-time">
            {{ new Date().toLocaleTimeString() }}
          </div>
        </div>
        
        <!-- Left Panel - Detection Stats -->
        <div class="hud-panel hud-left">
          <div class="hud-stat-group">
            <div class="hud-stat">
              <span class="hud-stat-icon">👤</span>
              <div class="hud-stat-data">
                <span class="hud-stat-value">{{ fullscreenStats.personsCount }}</span>
                <span class="hud-stat-label">Personas</span>
              </div>
              <div class="hud-stat-bar">
                <div class="hud-stat-fill" :style="{ width: Math.min(fullscreenStats.personsCount * 10, 100) + '%' }"></div>
              </div>
            </div>
            <div class="hud-stat">
              <span class="hud-stat-icon">🚗</span>
              <div class="hud-stat-data">
                <span class="hud-stat-value">{{ fullscreenStats.vehiclesCount }}</span>
                <span class="hud-stat-label">Vehículos</span>
              </div>
              <div class="hud-stat-bar">
                <div class="hud-stat-fill vehicles" :style="{ width: Math.min(fullscreenStats.vehiclesCount * 15, 100) + '%' }"></div>
              </div>
            </div>
            <div class="hud-stat">
              <span class="hud-stat-icon">😊</span>
              <div class="hud-stat-data">
                <span class="hud-stat-value">{{ fullscreenStats.facesCount }}</span>
                <span class="hud-stat-label">Rostros</span>
              </div>
              <div class="hud-stat-bar">
                <div class="hud-stat-fill faces" :style="{ width: Math.min(fullscreenStats.facesCount * 20, 100) + '%' }"></div>
              </div>
            </div>
          </div>
        </div>
        
        <!-- Right Panel - Alerts & Events -->
        <div class="hud-panel hud-right">
          <div class="hud-section-title">
            <span class="hud-icon">⚠️</span> Eventos Recientes
          </div>
          <div class="hud-events-list">
            <div v-for="(det, i) in (detections || []).slice(0, 5)" :key="i" class="hud-event">
              <span class="hud-event-icon">{{ det.event?.includes('person') ? '👤' : det.event?.includes('face') ? '😊' : '📦' }}</span>
              <span class="hud-event-text">{{ det.event || det.label }}</span>
              <span class="hud-event-time">{{ new Date().toLocaleTimeString() }}</span>
            </div>
            <div v-if="!detections || detections.length === 0" class="hud-event empty">
              Sin eventos recientes
            </div>
          </div>
        </div>
        
        <!-- Bottom Bar - Quick Stats -->
        <div class="hud-bottom-bar">
          <div class="hud-quick-stat">
            <span class="hud-qs-label">OBJETOS</span>
            <span class="hud-qs-value">{{ detections?.length || 0 }}</span>
          </div>
          <div class="hud-quick-stat">
            <span class="hud-qs-label">ALERTAS</span>
            <span class="hud-qs-value">{{ alerts?.length || 0 }}</span>
          </div>
          <div class="hud-quick-stat" v-if="fullscreenStats.nearestDistance">
            <span class="hud-qs-label">DISTANCIA</span>
            <span class="hud-qs-value">{{ fullscreenStats.nearestDistance.toFixed(1) }}m</span>
          </div>
          <div class="hud-quick-stat">
            <span class="hud-qs-label">MODELO</span>
            <span class="hud-qs-value">{{ activeCamera?.detection_model || 'YOLO-NAS' }}</span>
          </div>
        </div>
        
        <!-- Mini BEV Map (Bottom Right) -->
        <div class="hud-minimap" v-if="activeCamera?.bev_enabled && bevData.objects.length > 0">
          <canvas ref="hudBevCanvas" width="150" height="150"></canvas>
        </div>
        
        <!-- Corner decorations -->
        <div class="hud-corner hud-corner-tl"></div>
        <div class="hud-corner hud-corner-tr"></div>
        <div class="hud-corner hud-corner-bl"></div>
        <div class="hud-corner hud-corner-br"></div>
      </div>
    </Transition>

    </div>
  </div>
</template>

<style scoped>
/* App Layout with NavBar */
.app-layout {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: #0d1117;
}

/* Control Center Theme */
.control-center {
  display: flex;
  height: calc(100vh - 4rem);
  margin-top: 4rem;
  background-color: #0d1117;
  color: #e0e0e0;
  font-family: 'Poppins', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  overflow: hidden;
}

/* Sidebar */
.sidebar {
  width: 260px;
  background-color: #161b22;
  border-right: 1px solid #30363d;
  display: flex;
  flex-direction: column;
}
.sidebar-header {
  padding: 1rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #30363d;
}
.sidebar-header h3 {
  font-size: 0.95rem;
  font-weight: 600;
  color: #c9d1d9;
}
.btn-icon {
  background: linear-gradient(135deg, #1f6feb, #a855f7);
  border: none;
  color: white;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 1.1rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}
.btn-icon:hover {
  transform: scale(1.05);
  box-shadow: 0 4px 12px rgba(31, 111, 235, 0.3);
}
.cam-list {
  flex: 1;
  overflow-y: auto;
  padding: 0.5rem;
}
.cam-item {
  padding: 0.75rem 1rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  border-radius: 0.5rem;
  margin-bottom: 0.25rem;
  transition: all 0.2s ease;
  color: #8b949e;
  font-size: 0.9rem;
}
.cam-item:hover { 
  background-color: #21262d; 
  color: #c9d1d9;
}
.cam-item.active { 
  background-color: rgba(31, 111, 235, 0.15); 
  color: #58a6ff;
  border-left: 3px solid #1f6feb; 
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #484f58;
  flex-shrink: 0;
}
.status-dot.online { 
  background-color: #3fb950; 
  box-shadow: 0 0 8px rgba(63, 185, 80, 0.5);
  animation: pulse-dot 2s infinite;
}
@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

/* Main Content */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  background: #0d1117;
}
.control-header {
  padding: 1rem 1.5rem;
  background-color: #161b22;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #30363d;
}
.header-left { 
  display: flex; 
  align-items: center; 
  gap: 1rem; 
}
.header-left h2 {
  font-size: 1.1rem;
  font-weight: 600;
  color: #c9d1d9;
}
.badge { 
  padding: 0.35rem 0.75rem; 
  border-radius: 2rem; 
  font-size: 0.7rem; 
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.badge-success { 
  background-color: rgba(63, 185, 80, 0.15); 
  color: #3fb950; 
}
.badge-secondary { 
  background-color: rgba(139, 148, 158, 0.15); 
  color: #8b949e; 
}

.video-grid {
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 1px;
  background-color: #30363d;
  min-height: 55vh;
}
.video-box {
  background-color: #0d1117;
  position: relative;
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 300px;
  overflow: hidden;
  cursor: pointer;
}
.stream-wrapper { 
  width: 100%; 
  height: 100%; 
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  cursor: pointer;
}
.stream { 
  width: 100%; 
  height: 100%; 
  object-fit: contain;
  position: absolute;
  top: 0;
  left: 0;
  cursor: pointer;
}
iframe.stream {
  border: none;
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
}
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
.model-note {
  display: block;
  font-size: 0.75rem;
  color: #4a9;
  margin-top: 4px;
}
.multi-select-box {
  height: 150px;
  overflow-y: auto;
  background-color: #1e1e1e;
  border: 1px solid #333;
  padding: 5px;
  border-radius: 4px;
}
.class-actions {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
  align-items: center;
}
.class-count {
  margin-left: auto;
  font-size: 0.75rem;
  color: #8b949e;
  background: #21262d;
  padding: 0.25rem 0.5rem;
  border-radius: 1rem;
}
.btn-small {
  padding: 0.35rem 0.75rem;
  font-size: 0.75rem;
  background: linear-gradient(135deg, #1f6feb, #388bfd);
  border: none;
  border-radius: 0.35rem;
  color: white;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s ease;
}
.btn-small:hover { 
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(31, 111, 235, 0.3);
}
.btn-small.btn-secondary {
  background: #21262d;
  border: 1px solid #30363d;
  color: #c9d1d9;
}
.btn-small.btn-secondary:hover { 
  background: #30363d;
  transform: translateY(-1px);
}
.save-note {
  font-size: 0.75rem;
  color: #f0883e;
  margin-top: 0.5rem;
  display: flex;
  align-items: center;
  gap: 0.35rem;
}
.btn-save:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Settings Accordion */
.settings-accordion {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.accordion-item {
  background: #1c1c1c;
  border: 1px solid #333;
  border-radius: 0.5rem;
  overflow: hidden;
  transition: all 0.2s ease;
}

.accordion-item.open {
  border-color: #484f58;
}

.accordion-header {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem;
  background: transparent;
  border: none;
  color: #c9d1d9;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 500;
  transition: all 0.15s ease;
}

.accordion-header:hover {
  background: #252526;
}

.accordion-icon {
  font-size: 1rem;
}

.accordion-title {
  flex: 1;
  text-align: left;
}

.accordion-status {
  font-size: 0.65rem;
  font-weight: 600;
  padding: 0.2rem 0.5rem;
  border-radius: 0.25rem;
  background: #484f58;
  color: #8b949e;
}

.accordion-status.active {
  background: linear-gradient(135deg, #238636, #2ea043);
  color: white;
}

.accordion-arrow {
  font-size: 0.65rem;
  color: #8b949e;
}

.accordion-content {
  padding: 0.75rem;
  background: #161616;
  border-top: 1px solid #333;
}

.setting-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

.setting-row:last-child {
  margin-bottom: 0;
}

.setting-label {
  font-size: 0.8rem;
  color: #c9d1d9;
}

/* Toggle Switch (New Style) */
.toggle-switch {
  position: relative;
  width: 36px;
  height: 20px;
  flex-shrink: 0;
}

.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: #484f58;
  border-radius: 20px;
  transition: all 0.3s ease;
}

.toggle-slider:before {
  position: absolute;
  content: "";
  height: 14px;
  width: 14px;
  left: 3px;
  bottom: 3px;
  background: white;
  border-radius: 50%;
  transition: all 0.3s ease;
}

.toggle-switch input:checked + .toggle-slider {
  background: linear-gradient(135deg, #238636, #2ea043);
}

.toggle-switch input:checked + .toggle-slider:before {
  transform: translateX(16px);
}

.nested-settings {
  margin-top: 0.75rem;
  padding-top: 0.75rem;
  border-top: 1px dashed #333;
}

.compact-select {
  flex: 1;
  background: #252526;
  border: 1px solid #484f58;
  color: #c9d1d9;
  padding: 0.4rem 0.6rem;
  border-radius: 0.35rem;
  font-size: 0.8rem;
}

.classes-row {
  flex-direction: column;
  align-items: stretch;
}

.classes-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}

.class-badge {
  font-size: 0.7rem;
  color: #8b949e;
  background: #252526;
  padding: 0.15rem 0.4rem;
  border-radius: 0.25rem;
}

.class-buttons {
  display: flex;
  gap: 0.5rem;
}

.btn-mini {
  padding: 0.25rem 0.5rem;
  font-size: 0.7rem;
  background: linear-gradient(135deg, #1f6feb, #388bfd);
  border: none;
  border-radius: 0.25rem;
  color: white;
  cursor: pointer;
  font-weight: 500;
}

.btn-mini.ghost {
  background: transparent;
  border: 1px solid #484f58;
  color: #8b949e;
}

.classes-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  max-height: 120px;
  overflow-y: auto;
  padding: 0.5rem;
  background: #1c1c1c;
  border-radius: 0.35rem;
}

.class-chip {
  font-size: 0.7rem;
  padding: 0.2rem 0.5rem;
  background: #252526;
  border: 1px solid #333;
  border-radius: 0.25rem;
  color: #8b949e;
  cursor: pointer;
  transition: all 0.15s ease;
}

.class-chip:hover {
  border-color: #484f58;
}

.class-chip.selected {
  background: linear-gradient(135deg, rgba(31, 111, 235, 0.2), rgba(56, 139, 253, 0.2));
  border-color: #1f6feb;
  color: #58a6ff;
}

.btn-faces {
  width: 100%;
  margin-top: 0.75rem;
  padding: 0.5rem;
  background: linear-gradient(135deg, #8b5cf6, #a78bfa);
  border: none;
  border-radius: 0.35rem;
  color: white;
  font-size: 0.8rem;
  cursor: pointer;
  font-weight: 500;
}

/* Alert Form */
.alert-form {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form-input {
  width: 100%;
  background: #252526;
  border: 1px solid #484f58;
  color: #c9d1d9;
  padding: 0.5rem 0.6rem;
  border-radius: 0.35rem;
  font-size: 0.8rem;
}

.form-input.small {
  width: 80px;
}

.threshold-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.threshold-row label {
  font-size: 0.8rem;
  color: #8b949e;
}

.btn-create-alert {
  padding: 0.5rem;
  background: linear-gradient(135deg, #f0883e, #fb8532);
  border: none;
  border-radius: 0.35rem;
  color: white;
  font-size: 0.8rem;
  cursor: pointer;
  font-weight: 500;
}

/* Save Section */
.save-section {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid #333;
}

.btn-save-main {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.75rem;
  background: linear-gradient(135deg, #1f6feb, #388bfd);
  border: none;
  border-radius: 0.5rem;
  color: white;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-save-main:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(31, 111, 235, 0.3);
}

.btn-save-main:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none;
}

.spinner-small {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.save-hint {
  font-size: 0.7rem;
  color: #f0883e;
  text-align: center;
  margin-top: 0.5rem;
}

.checkbox-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.35rem 0.5rem;
  font-size: 0.85rem;
  cursor: pointer;
  border-radius: 0.35rem;
  color: #8b949e;
  transition: all 0.15s ease;
}
.checkbox-item:hover { 
  background-color: #21262d;
  color: #c9d1d9;
}
.checkbox-item input[type="checkbox"] {
  accent-color: #1f6feb;
}

/* Switch */
.switch {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 0.75rem;
  cursor: pointer;
}
.switch input { opacity: 0; width: 0; height: 0; }
.slider {
  position: relative;
  display: inline-block;
  width: 36px;
  height: 20px;
  background-color: #484f58;
  transition: all 0.3s ease;
  border-radius: 20px;
}
.slider:before {
  position: absolute;
  content: "";
  height: 14px;
  width: 14px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  transition: all 0.3s ease;
  border-radius: 50%;
}
input:checked + .slider { 
  background: linear-gradient(135deg, #1f6feb, #388bfd);
}
input:checked + .slider:before { 
  transform: translateX(16px); 
}
.label-text { 
  font-size: 0.85rem;
  color: #c9d1d9;
}

/* Buttons */
.header-actions {
  display: flex;
  gap: 0.5rem;
}
.btn-save { 
  width: 100%; 
  background: linear-gradient(135deg, #1f6feb, #388bfd);
  color: white; 
  border: none; 
  padding: 0.75rem; 
  border-radius: 0.5rem; 
  cursor: pointer; 
  margin-top: 0.75rem;
  font-weight: 500;
  transition: all 0.2s ease;
}
.btn-save:hover { 
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(31, 111, 235, 0.3);
}
.btn-action { 
  width: 100%; 
  background-color: #21262d; 
  color: #c9d1d9; 
  border: 1px solid #30363d; 
  padding: 0.5rem; 
  border-radius: 0.4rem; 
  cursor: pointer; 
  margin-top: 0.5rem;
  transition: all 0.2s ease;
}
.btn-action:hover {
  background-color: #30363d;
}
.btn-start { 
  background: linear-gradient(135deg, #238636, #2ea043);
  color: white; 
  border: none; 
  padding: 0.5rem 1rem; 
  border-radius: 0.5rem; 
  cursor: pointer; 
  display: flex; 
  align-items: center; 
  gap: 0.5rem;
  font-weight: 500;
  font-size: 0.875rem;
  transition: all 0.2s ease;
}
.btn-start:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(35, 134, 54, 0.3);
}
.btn-stop { 
  background: linear-gradient(135deg, #da3633, #f85149);
  color: white; 
  border: none; 
  padding: 0.5rem 1rem; 
  border-radius: 0.5rem; 
  cursor: pointer; 
  display: flex; 
  align-items: center; 
  gap: 0.5rem;
  font-weight: 500;
  font-size: 0.875rem;
  transition: all 0.2s ease;
}
.btn-stop:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(248, 81, 73, 0.3);
}
.btn-secondary {
  background-color: #21262d;
  color: #c9d1d9;
  border: 1px solid #30363d;
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 500;
  font-size: 0.875rem;
  transition: all 0.2s ease;
}
.btn-secondary:hover {
  background-color: #30363d;
  border-color: #8b949e;
}

/* Bottom Panel */
.bottom-panel {
  flex: 1;
  background-color: #161b22;
  border-top: 1px solid #30363d;
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  overflow: hidden;
}
.panel-col {
  padding: 1rem;
  overflow-y: auto;
  border-right: 1px solid #30363d;
}
.panel-col h4 {
  font-size: 0.85rem;
  font-weight: 600;
  color: #c9d1d9;
  margin-bottom: 0.75rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.log-list { list-style: none; padding: 0; margin: 0; }
.log-item {
  padding: 0.6rem 0.75rem;
  border-radius: 0.4rem;
  background: #0d1117;
  margin-bottom: 0.5rem;
  font-size: 0.85rem;
  display: flex;
  gap: 0.75rem;
  border-left: 3px solid transparent;
  transition: all 0.2s ease;
}
.log-item:hover {
  background: #21262d;
}
.log-item .time { 
  color: #8b949e; 
  font-family: 'SF Mono', monospace; 
  font-size: 0.75rem;
}
.log-item .event { 
  color: #58a6ff; 
  font-weight: 500; 
}
.log-item.alert { 
  border-left-color: #f0883e;
}
.log-item.alert .event { 
  color: #f0883e; 
}

/* BEV Panel Styles */
.bev-panel {
  display: flex;
  flex-direction: column;
}
.bev-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}
.bev-canvas {
  background: #1a1a1a;
  border: 1px solid #444;
  border-radius: 4px;
}
.bev-legend {
  display: flex;
  gap: 15px;
  font-size: 0.8rem;
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 5px;
}
.legend-item .dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
}
.legend-item .dot.near { background: #ff4444; }
.legend-item .dot.mid { background: #ffaa44; }
.legend-item .dot.far { background: #44ff44; }
.bev-stats {
  background: #252526;
  padding: 8px 15px;
  border-radius: 4px;
  font-size: 0.85rem;
  display: flex;
  gap: 20px;
}
.bev-stats p { margin: 0; }
.bev-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  text-align: center;
  color: #666;
  font-size: 0.9rem;
  padding: 1.25rem;
}
.bev-disabled {
  opacity: 0.7;
}

/* Face Recognition Panel */
.face-panel {
  min-width: 350px;
  max-width: 450px;
}
.btn-view-faces {
  margin-left: 10px;
  padding: 4px 10px;
  background: #4a90d9;
  border: none;
  border-radius: 4px;
  color: #fff;
  cursor: pointer;
  font-size: 12px;
  transition: background 0.2s;
}
.btn-view-faces:hover {
  background: #5a9fea;
}

/* Modal */
.modal-overlay { 
  position: fixed; 
  top: 0; 
  left: 0; 
  width: 100%; 
  height: 100%; 
  background: rgba(0, 0, 0, 0.8); 
  backdrop-filter: blur(4px);
  display: flex; 
  justify-content: center; 
  align-items: center; 
  z-index: 2000; 
}
.modal-box { 
  background: #161b22; 
  padding: 1.5rem; 
  border-radius: 0.75rem; 
  width: 420px; 
  display: flex; 
  flex-direction: column; 
  gap: 1rem; 
  border: 1px solid #30363d;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.5);
  animation: modalIn 0.2s ease-out;
}
@keyframes modalIn {
  from {
    opacity: 0;
    transform: scale(0.95) translateY(-10px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}
.modal-box h3 {
  font-size: 1.1rem;
  font-weight: 600;
  color: #c9d1d9;
  margin-bottom: 0.5rem;
}
.dark-input {
  background: #0d1117;
  border: 1px solid #30363d;
  padding: 0.75rem 1rem;
  border-radius: 0.5rem;
  color: #c9d1d9;
  font-size: 0.9rem;
  transition: all 0.2s ease;
}
.dark-input:focus {
  outline: none;
  border-color: #1f6feb;
  box-shadow: 0 0 0 3px rgba(31, 111, 235, 0.15);
}
.dark-input::placeholder {
  color: #484f58;
}
.modal-actions { 
  display: flex; 
  justify-content: flex-end; 
  gap: 0.75rem;
  margin-top: 0.5rem;
}
.btn-confirm { 
  background: linear-gradient(135deg, #1f6feb, #a855f7);
  color: white; 
  border: none; 
  padding: 0.6rem 1.25rem; 
  border-radius: 0.5rem; 
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.btn-confirm:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(31, 111, 235, 0.4);
}
.btn-cancel { 
  background: transparent; 
  color: #8b949e; 
  border: 1px solid #30363d; 
  padding: 0.6rem 1.25rem; 
  border-radius: 0.5rem; 
  cursor: pointer;
  transition: all 0.2s ease;
}
.btn-cancel:hover {
  background: #21262d;
  color: #c9d1d9;
}

.empty-state { 
  display: flex; 
  flex-direction: column;
  justify-content: center; 
  align-items: center; 
  height: 100%; 
  color: #484f58;
  gap: 1rem;
}
.empty-state svg {
  opacity: 0.3;
}

/* Profile Modal Styles */
.profile-modal {
  width: 480px;
  max-width: 90vw;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 1rem;
  border-bottom: 1px solid #30363d;
  margin-bottom: 1rem;
}

.modal-header h3 {
  margin: 0;
  font-size: 1.2rem;
}

.close-btn {
  background: transparent;
  border: none;
  color: #8b949e;
  font-size: 1.5rem;
  cursor: pointer;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  transition: all 0.2s ease;
}

.close-btn:hover {
  background: #21262d;
  color: #c9d1d9;
}

.profile-avatar-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1.5rem;
}

.profile-avatar-large {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: linear-gradient(135deg, #1f6feb, #a855f7);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.8rem;
  font-weight: 700;
  color: white;
  box-shadow: 0 4px 20px rgba(31, 111, 235, 0.3);
}

.profile-role-badge {
  background: linear-gradient(135deg, #21262d, #30363d);
  padding: 0.4rem 1rem;
  border-radius: 20px;
  font-size: 0.85rem;
  color: #c9d1d9;
  border: 1px solid #30363d;
}

.profile-form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.form-group label {
  font-size: 0.85rem;
  color: #8b949e;
  font-weight: 500;
}

/* Modal transition animations */
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: all 0.3s ease;
}

.modal-fade-enter-active .modal-box,
.modal-fade-leave-active .modal-box {
  transition: all 0.3s ease;
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}

.modal-fade-enter-from .modal-box,
.modal-fade-leave-to .modal-box {
  opacity: 0;
  transform: scale(0.9) translateY(-20px);
}

/* =============================================== */
/* RESPONSIVE DESIGN */
/* =============================================== */

/* Tablets and smaller desktops */
@media (max-width: 1200px) {
  .video-grid {
    grid-template-columns: 1fr;
    min-height: auto;
  }
  
  .video-box {
    min-height: 40vh;
    aspect-ratio: 16/9;
  }
  
  .control-panel {
    max-height: 400px;
    overflow-y: auto;
  }
  
  .bottom-panels {
    flex-direction: column;
  }
  
  .panel-col {
    width: 100%;
  }
}

/* Tablets */
@media (max-width: 1024px) {
  .sidebar {
    width: 220px;
  }
  
  .header-actions {
    flex-wrap: wrap;
    gap: 0.5rem;
  }
  
  .header-actions button {
    padding: 0.5rem 0.75rem;
    font-size: 0.8rem;
  }
  
  .alerts-panel {
    max-height: 300px;
  }
}

/* Small tablets and large phones */
@media (max-width: 768px) {
  .control-center {
    flex-direction: column;
    height: auto;
    min-height: calc(100vh - 4rem);
  }
  
  .sidebar {
    width: 100%;
    max-height: 200px;
    border-right: none;
    border-bottom: 1px solid #30363d;
  }
  
  .cam-list {
    display: flex;
    flex-wrap: nowrap;
    overflow-x: auto;
    gap: 0.5rem;
    padding: 0.5rem;
  }
  
  .cam-item {
    flex-shrink: 0;
    white-space: nowrap;
    min-width: auto;
  }
  
  .main-content {
    padding: 1rem;
    overflow-y: auto;
  }
  
  .control-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.75rem;
  }
  
  .header-actions {
    width: 100%;
    justify-content: flex-start;
  }
  
  .video-box {
    min-height: 200px;
    aspect-ratio: 16/9;
    width: 100%;
  }
  
  .stream, iframe.stream {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
  }
  
  .control-panel {
    max-height: none;
  }
  
  .modal-box {
    width: calc(100vw - 2rem);
    max-height: 90vh;
    overflow-y: auto;
  }
  
  .profile-modal {
    width: calc(100vw - 2rem);
  }
  
  .multi-select-box {
    max-height: 150px;
  }
  
  .bev-container {
    flex-direction: column;
  }
  
  .bev-canvas {
    width: 100%;
    height: 200px;
  }
  
  .bev-legend {
    flex-wrap: wrap;
  }
}

/* Phones */
@media (max-width: 480px) {
  .control-center {
    margin-top: 3.5rem;
    height: calc(100vh - 3.5rem);
  }
  
  .sidebar-header h3 {
    font-size: 0.85rem;
  }
  
  .sidebar-header {
    padding: 0.75rem;
  }
  
  .btn-icon {
    width: 24px;
    height: 24px;
    font-size: 0.9rem;
  }
  
  .cam-item {
    padding: 0.5rem 0.75rem;
    font-size: 0.85rem;
  }
  
  .control-header h2 {
    font-size: 1rem;
  }
  
  .badge {
    font-size: 0.65rem;
    padding: 0.2rem 0.5rem;
  }
  
  .header-actions button {
    flex: 1;
    justify-content: center;
  }
  
  .panel-section h3 {
    font-size: 0.9rem;
  }
  
  .setting-group label {
    font-size: 0.8rem;
  }
  
  .dark-select {
    font-size: 0.85rem;
    padding: 0.5rem;
  }
  
  .model-note {
    display: block;
    font-size: 0.7rem;
    color: #4a9;
    margin-top: 4px;
  }
  
  .checkbox-item {
    font-size: 0.8rem;
  }
  
  .video-box {
    min-height: 200px;
  }
  
  .placeholder-content {
    font-size: 0.85rem;
  }
  
  .alerts-panel .alert-item {
    padding: 0.6rem;
    font-size: 0.8rem;
  }
  
  .modal-box {
    padding: 1rem;
  }
  
  .modal-box h3 {
    font-size: 1rem;
  }
  
  .dark-input {
    padding: 0.6rem 0.75rem;
    font-size: 0.85rem;
  }
  
  .modal-actions button {
    padding: 0.5rem 1rem;
    font-size: 0.85rem;
  }
  
  .profile-avatar-large {
    width: 60px;
    height: 60px;
    font-size: 1.4rem;
  }
}

/* Extra small phones */
@media (max-width: 360px) {
  .header-actions {
    flex-direction: column;
  }
  
  .header-actions button {
    width: 100%;
  }
  
  .sidebar {
    max-height: 150px;
  }
}

/* ===========================================
   FULLSCREEN HUD STYLES (Gaming/Fortnite Style)
   =========================================== */

.fullscreen-hint {
  position: absolute;
  bottom: 12px;
  right: 12px;
  background: rgba(0, 0, 0, 0.6);
  padding: 6px 12px;
  border-radius: 4px;
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.7);
  pointer-events: none;
  backdrop-filter: blur(4px);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.hud-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 9999;
  background: #000;
  cursor: crosshair;
}

.hud-video {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.hud-close {
  position: absolute;
  top: 20px;
  right: 20px;
  width: 40px;
  height: 40px;
  background: rgba(0, 0, 0, 0.5);
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-radius: 50%;
  color: #fff;
  font-size: 1.2rem;
  cursor: pointer;
  transition: all 0.2s;
  z-index: 10;
}

.hud-close:hover {
  background: rgba(255, 50, 50, 0.7);
  border-color: #ff5555;
  transform: scale(1.1);
}

/* Top Bar */
.hud-top-bar {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 50px;
  background: linear-gradient(180deg, rgba(0,0,0,0.7) 0%, transparent 100%);
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 80px 0 30px;
}

.hud-camera-info {
  display: flex;
  align-items: center;
  gap: 15px;
}

.hud-camera-name {
  font-size: 1.1rem;
  font-weight: 600;
  color: #fff;
  text-shadow: 0 2px 4px rgba(0,0,0,0.5);
}

.hud-status {
  font-size: 0.8rem;
  padding: 4px 10px;
  border-radius: 4px;
  font-weight: 600;
}

.hud-status.live {
  background: rgba(255, 50, 50, 0.3);
  color: #ff5555;
  border: 1px solid rgba(255, 50, 50, 0.5);
  animation: pulse-live 2s infinite;
}

@keyframes pulse-live {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

.hud-time {
  font-size: 1rem;
  color: rgba(255, 255, 255, 0.8);
  font-family: 'Courier New', monospace;
  font-weight: 600;
}

/* Side Panels */
.hud-panel {
  position: absolute;
  top: 80px;
  width: 250px;
  background: linear-gradient(135deg, rgba(0,0,0,0.6) 0%, rgba(0,0,0,0.3) 100%);
  backdrop-filter: blur(10px);
  border-radius: 8px;
  padding: 15px;
  border: 1px solid rgba(100, 200, 255, 0.2);
}

.hud-left {
  left: 20px;
}

.hud-right {
  right: 80px;
  max-height: calc(100vh - 200px);
  overflow-y: auto;
}

.hud-stat-group {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.hud-stat {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px;
  background: rgba(0, 0, 0, 0.3);
  border-radius: 6px;
  border-left: 3px solid #4af;
}

.hud-stat-icon {
  font-size: 1.5rem;
}

.hud-stat-data {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.hud-stat-value {
  font-size: 1.4rem;
  font-weight: 700;
  color: #fff;
  line-height: 1;
}

.hud-stat-label {
  font-size: 0.7rem;
  color: rgba(255, 255, 255, 0.6);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.hud-stat-bar {
  width: 40px;
  height: 6px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 3px;
  overflow: hidden;
}

.hud-stat-fill {
  height: 100%;
  background: linear-gradient(90deg, #4af, #0ff);
  border-radius: 3px;
  transition: width 0.3s ease;
}

.hud-stat-fill.vehicles {
  background: linear-gradient(90deg, #fa4, #ff0);
}

.hud-stat-fill.faces {
  background: linear-gradient(90deg, #f4a, #f0f);
}

/* Events List */
.hud-section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.8rem;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.8);
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.hud-events-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.hud-event {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  background: rgba(0, 0, 0, 0.3);
  border-radius: 4px;
  border-left: 2px solid #4af;
  font-size: 0.8rem;
}

.hud-event.empty {
  color: rgba(255, 255, 255, 0.4);
  font-style: italic;
  border-left-color: rgba(255, 255, 255, 0.2);
}

.hud-event-icon {
  font-size: 1rem;
}

.hud-event-text {
  flex: 1;
  color: #fff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.hud-event-time {
  font-size: 0.7rem;
  color: rgba(255, 255, 255, 0.5);
  font-family: 'Courier New', monospace;
}

/* Bottom Bar */
.hud-bottom-bar {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 60px;
  background: linear-gradient(0deg, rgba(0,0,0,0.7) 0%, transparent 100%);
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 40px;
  padding: 0 30px;
}

.hud-quick-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.hud-qs-label {
  font-size: 0.65rem;
  color: rgba(255, 255, 255, 0.5);
  text-transform: uppercase;
  letter-spacing: 1px;
}

.hud-qs-value {
  font-size: 1.1rem;
  font-weight: 700;
  color: #4af;
  text-shadow: 0 0 10px rgba(68, 170, 255, 0.5);
}

/* Mini Map */
.hud-minimap {
  position: absolute;
  bottom: 80px;
  right: 20px;
  width: 150px;
  height: 150px;
  background: rgba(0, 0, 0, 0.6);
  border: 2px solid rgba(100, 200, 255, 0.3);
  border-radius: 8px;
  overflow: hidden;
}

.hud-minimap canvas {
  width: 100%;
  height: 100%;
}

/* Corner Decorations */
.hud-corner {
  position: absolute;
  width: 50px;
  height: 50px;
  border: 2px solid rgba(100, 200, 255, 0.4);
  pointer-events: none;
}

.hud-corner-tl {
  top: 60px;
  left: 10px;
  border-right: none;
  border-bottom: none;
  border-radius: 8px 0 0 0;
}

.hud-corner-tr {
  top: 60px;
  right: 10px;
  border-left: none;
  border-bottom: none;
  border-radius: 0 8px 0 0;
}

.hud-corner-bl {
  bottom: 70px;
  left: 10px;
  border-right: none;
  border-top: none;
  border-radius: 0 0 0 8px;
}

.hud-corner-br {
  bottom: 70px;
  right: 10px;
  border-left: none;
  border-top: none;
  border-radius: 0 0 8px 0;
}

/* Fade transition */
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from, .fade-leave-to {
  opacity: 0;
}

/* HUD responsive */
@media (max-width: 768px) {
  .hud-panel {
    width: 180px;
    padding: 10px;
  }
  
  .hud-left {
    left: 10px;
  }
  
  .hud-right {
    right: 10px;
  }
  
  .hud-stat-value {
    font-size: 1.1rem;
  }
  
  .hud-bottom-bar {
    gap: 20px;
  }
}
</style>