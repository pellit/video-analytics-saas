<script setup>
/**
 * SmartPlayer.vue
 * ===============
 * Componente de video inteligente que:
 * - Reproduce video desde MediaMTX (WebRTC/HLS)
 * - Superpone canvas para dibujar detecciones
 * - Recibe coordenadas via WebSocket/SSE
 * - Fallback a MJPEG si MediaMTX no está disponible
 */

import { ref, onMounted, onUnmounted, watch, computed } from 'vue'

const props = defineProps({
  cameraId: { type: [String, Number], required: true },
  // URLs de streaming
  mediamtxWebrtcUrl: { type: String, default: '' },
  mediamtxHlsUrl: { type: String, default: '' },
  mjpegFallbackUrl: { type: String, default: '' },
  // Configuración
  autoplay: { type: Boolean, default: true },
  muted: { type: Boolean, default: true },
  showOverlay: { type: Boolean, default: true },
  showControls: { type: Boolean, default: true },
  // WebSocket para detecciones
  wsUrl: { type: String, default: '' },
  sseEndpoint: { type: String, default: '/stream/events/{camera_id}' }
})

const emit = defineEmits(['error', 'connected', 'detection', 'streamChange'])

// Refs
const containerRef = ref(null)
const videoRef = ref(null)
const canvasRef = ref(null)

// State
const isLoading = ref(true)
const isPlaying = ref(false)
const currentMode = ref('detecting') // 'webrtc', 'hls', 'mjpeg', 'detecting'
const errorMessage = ref('')
const detections = ref([])
const lastDetectionTime = ref(0)
const streamStats = ref({
  fps: 0,
  latency: 0,
  resolution: '',
  protocol: ''
})

// WebSocket/SSE connection
let eventSource = null
let reconnectTimer = null
let animationFrameId = null

// Detection colors by class
const classColors = {
  person: '#00FF00',
  car: '#FF6600',
  truck: '#FF9900',
  bus: '#FFCC00',
  motorcycle: '#FF3300',
  bicycle: '#66FF00',
  dog: '#FF00FF',
  cat: '#FF66FF',
  face: '#00FFFF',
  default: '#FFFFFF'
}

// Computed
const streamUrl = computed(() => {
  const baseWebrtc = props.mediamtxWebrtcUrl || import.meta.env.VITE_MEDIAMTX_WEBRTC_URL || 'http://localhost:8889'
  const baseHls = props.mediamtxHlsUrl || import.meta.env.VITE_MEDIAMTX_HLS_URL || 'http://localhost:8888'
  const baseMjpeg = props.mjpegFallbackUrl || import.meta.env.VITE_STREAM_URL || 'http://localhost:5000/video_feed'
  
  return {
    webrtc: `${baseWebrtc}/live/camera_${props.cameraId}/`,
    hls: `${baseHls}/live/camera_${props.cameraId}/index.m3u8`,
    mjpeg: `${baseMjpeg}?camera_id=${props.cameraId}`
  }
})

// Initialize player
onMounted(async () => {
  await detectBestProtocol()
  startDetectionStream()
  startRenderLoop()
})

onUnmounted(() => {
  cleanup()
})

// Watch camera changes
watch(() => props.cameraId, async () => {
  cleanup()
  await detectBestProtocol()
  startDetectionStream()
  startRenderLoop()
})

/**
 * Detecta el mejor protocolo disponible
 */
async function detectBestProtocol() {
  isLoading.value = true
  errorMessage.value = ''
  currentMode.value = 'detecting'
  
  const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent)
  const isIOS = /iPhone|iPad|iPod/i.test(navigator.userAgent)
  
  // Orden de preferencia según dispositivo
  const protocols = isMobile 
    ? ['hls', 'mjpeg']  // Móviles: HLS primero
    : ['webrtc', 'hls', 'mjpeg']  // Desktop: WebRTC primero
  
  for (const protocol of protocols) {
    try {
      console.log(`🔍 Trying ${protocol}...`)
      const success = await tryProtocol(protocol)
      if (success) {
        currentMode.value = protocol
        streamStats.value.protocol = protocol.toUpperCase()
        isLoading.value = false
        emit('connected', { protocol, cameraId: props.cameraId })
        return
      }
    } catch (e) {
      console.warn(`⚠️ ${protocol} failed:`, e.message)
    }
  }
  
  // Ningún protocolo funcionó
  isLoading.value = false
  errorMessage.value = 'No se pudo conectar al stream de video'
  emit('error', { message: errorMessage.value })
}

/**
 * Intenta conectar con un protocolo específico
 */
async function tryProtocol(protocol) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      reject(new Error('Connection timeout'))
    }, 5000)
    
    const video = videoRef.value
    if (!video) {
      clearTimeout(timeout)
      reject(new Error('Video element not found'))
      return
    }
    
    const onSuccess = () => {
      clearTimeout(timeout)
      video.removeEventListener('loadeddata', onSuccess)
      video.removeEventListener('error', onError)
      resolve(true)
    }
    
    const onError = (e) => {
      clearTimeout(timeout)
      video.removeEventListener('loadeddata', onSuccess)
      video.removeEventListener('error', onError)
      reject(new Error(e.message || 'Failed to load'))
    }
    
    video.addEventListener('loadeddata', onSuccess)
    video.addEventListener('error', onError)
    
    switch (protocol) {
      case 'webrtc':
        initWebRTC()
        break
      case 'hls':
        initHLS()
        break
      case 'mjpeg':
        // MJPEG usa <img>, no <video>
        clearTimeout(timeout)
        resolve(true)
        break
    }
  })
}

/**
 * Inicializa WebRTC (MediaMTX)
 */
async function initWebRTC() {
  const video = videoRef.value
  
  // MediaMTX expone WebRTC via WHEP
  const whepUrl = streamUrl.value.webrtc
  
  const pc = new RTCPeerConnection({
    iceServers: []  // MediaMTX no necesita STUN/TURN local
  })
  
  pc.ontrack = (event) => {
    video.srcObject = event.streams[0]
    if (props.autoplay) video.play()
  }
  
  pc.oniceconnectionstatechange = () => {
    if (pc.iceConnectionState === 'failed') {
      emit('error', { message: 'WebRTC connection failed' })
    }
  }
  
  // Crear oferta
  pc.addTransceiver('video', { direction: 'recvonly' })
  pc.addTransceiver('audio', { direction: 'recvonly' })
  
  const offer = await pc.createOffer()
  await pc.setLocalDescription(offer)
  
  // Enviar a MediaMTX WHEP endpoint
  const response = await fetch(whepUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/sdp' },
    body: offer.sdp
  })
  
  if (!response.ok) throw new Error('WHEP request failed')
  
  const answerSdp = await response.text()
  await pc.setRemoteDescription({ type: 'answer', sdp: answerSdp })
}

/**
 * Inicializa HLS
 */
async function initHLS() {
  const video = videoRef.value
  const hlsUrl = streamUrl.value.hls
  
  // iOS Safari soporta HLS nativo
  if (video.canPlayType('application/vnd.apple.mpegurl')) {
    video.src = hlsUrl
    if (props.autoplay) video.play()
    return
  }
  
  // Otros navegadores: usar hls.js
  const Hls = (await import('hls.js')).default
  
  if (!Hls.isSupported()) {
    throw new Error('HLS not supported')
  }
  
  const hls = new Hls({
    lowLatencyMode: true,
    liveSyncDuration: 1,
    liveMaxLatencyDuration: 5,
    liveDurationInfinity: true
  })
  
  hls.loadSource(hlsUrl)
  hls.attachMedia(video)
  
  hls.on(Hls.Events.MANIFEST_PARSED, () => {
    if (props.autoplay) video.play()
  })
  
  hls.on(Hls.Events.ERROR, (event, data) => {
    if (data.fatal) throw new Error(data.details)
  })
}

/**
 * Inicia conexión para recibir detecciones
 */
function startDetectionStream() {
  if (props.cameraId === null || props.cameraId === undefined || props.cameraId === '') {
    return
  }
  if (eventSource) {
    try { eventSource.close() } catch (e) {}
    eventSource = null
  }
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }

  const resolveWorkerBase = () => {
    if (props.wsUrl) return props.wsUrl.replace(/\/$/, '')
    if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
      return `${window.location.origin}/worker`
    }
    const streamUrl = import.meta.env.VITE_STREAM_URL || 'http://localhost:5000/video_feed'
    return streamUrl.replace('/video_feed', '')
  }

  const buildSseUrl = () => {
    const legacy = (props.wsUrl || '').trim()
    if (legacy && legacy.includes('/stream/') && !props.sseEndpoint) {
      return legacy.includes('{camera_id}')
        ? legacy.replace('{camera_id}', props.cameraId)
        : `${legacy.replace(/\/$/, '')}/${props.cameraId}`
    }

    let endpoint = (props.sseEndpoint || '/stream/events/{camera_id}').trim()
    if (endpoint.includes('{camera_id}')) {
      endpoint = endpoint.replace('{camera_id}', props.cameraId)
    } else if (!endpoint.endsWith(`/${props.cameraId}`)) {
      endpoint = `${endpoint.replace(/\/$/, '')}/${props.cameraId}`
    }

    if (endpoint.startsWith('http')) {
      return endpoint
    }

    const base = resolveWorkerBase().replace(/\/$/, '')
    return `${base}${endpoint.startsWith('/') ? '' : '/'}${endpoint}`
  }

  const sseUrl = buildSseUrl()
  console.log('[SmartPlayer] Connecting SSE:', sseUrl)
  
  eventSource = new EventSource(sseUrl)
  
  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (Array.isArray(data?.detections)) {
        detections.value = normalizeDetections(data.detections)
        lastDetectionTime.value = Date.now()
        emit('detection', data)
      }
    } catch (e) {
      console.warn('Error parsing detection:', e)
    }
  }
  
  eventSource.onerror = () => {
    console.warn('SSE connection lost, reconnecting...')
    if (eventSource) {
      try { eventSource.close() } catch (e) {}
      eventSource = null
    }
    reconnectTimer = setTimeout(startDetectionStream, 3000)
  }
}

function normalizeDetections(rawDetections = []) {
  return rawDetections
    .map(det => {
      const bbox = det.bbox || {}
      const width = Number(bbox.w ?? bbox.width ?? det.w ?? det.width ?? 0) || 0
      const height = Number(bbox.h ?? bbox.height ?? det.h ?? det.height ?? 0) || 0
      const centerX = bbox.cx ?? bbox.center?.x ?? det.center?.x ?? det.cx
      const centerY = bbox.cy ?? bbox.center?.y ?? det.center?.y ?? det.cy
      let x = Number(centerX)
      let y = Number(centerY)
      const hasCenter = Number.isFinite(x) && Number.isFinite(y)
      if (!hasCenter) {
        x = Number(bbox.x ?? det.x ?? 0) || 0
        y = Number(bbox.y ?? det.y ?? 0) || 0
        if (width || height) {
          x = x + width / 2
          y = y + height / 2
        }
      }
      return {
        class: det.class || det.label || 'object',
        conf: Number(det.confidence ?? det.conf ?? det.score ?? 0) || 0,
        x,
        y,
        w: width,
        h: height,
        track_id: det.track_id ?? det.trackId ?? det.id
      }
    })
    .filter(det => Number.isFinite(det.x) && Number.isFinite(det.y))
}

/**
 * Loop de renderizado para dibujar detecciones
 */
function startRenderLoop() {
  const render = () => {
    if (props.showOverlay) {
      drawDetections()
    }
    animationFrameId = requestAnimationFrame(render)
  }
  render()
}

/**
 * Dibuja las detecciones en el canvas
 */
function drawDetections() {
  const canvas = canvasRef.value
  const video = videoRef.value
  const container = containerRef.value
  
  if (!canvas || !container) return
  
  // Ajustar canvas al tamaño del contenedor
  const rect = container.getBoundingClientRect()
  canvas.width = rect.width
  canvas.height = rect.height
  
  const ctx = canvas.getContext('2d')
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  
  // Limpiar detecciones antiguas (>500ms)
  if (Date.now() - lastDetectionTime.value > 500) {
    detections.value = []
    return
  }
  
  // Dibujar cada detección
  detections.value.forEach(det => {
    const color = classColors[det.class] || classColors.default
    
    // Convertir coordenadas normalizadas (0-1) a píxeles
    // Las coordenadas vienen como centro (x, y) y tamaño (w, h)
    const x = (det.x - det.w / 2) * canvas.width
    const y = (det.y - det.h / 2) * canvas.height
    const w = det.w * canvas.width
    const h = det.h * canvas.height
    
    // Dibujar caja
    ctx.strokeStyle = color
    ctx.lineWidth = 2
    ctx.strokeRect(x, y, w, h)
    
    // Dibujar esquinas estilo tech
    const cornerLen = Math.min(w, h) * 0.15
    ctx.lineWidth = 3
    
    // Esquina superior izquierda
    ctx.beginPath()
    ctx.moveTo(x, y + cornerLen)
    ctx.lineTo(x, y)
    ctx.lineTo(x + cornerLen, y)
    ctx.stroke()
    
    // Esquina superior derecha
    ctx.beginPath()
    ctx.moveTo(x + w - cornerLen, y)
    ctx.lineTo(x + w, y)
    ctx.lineTo(x + w, y + cornerLen)
    ctx.stroke()
    
    // Esquina inferior izquierda
    ctx.beginPath()
    ctx.moveTo(x, y + h - cornerLen)
    ctx.lineTo(x, y + h)
    ctx.lineTo(x + cornerLen, y + h)
    ctx.stroke()
    
    // Esquina inferior derecha
    ctx.beginPath()
    ctx.moveTo(x + w - cornerLen, y + h)
    ctx.lineTo(x + w, y + h)
    ctx.lineTo(x + w, y + h - cornerLen)
    ctx.stroke()
    
    // Etiqueta
    const label = `${det.class} ${(det.conf * 100).toFixed(0)}%`
    ctx.font = '12px Inter, sans-serif'
    const textWidth = ctx.measureText(label).width
    
    // Fondo de etiqueta
    ctx.fillStyle = color
    ctx.fillRect(x, y - 20, textWidth + 10, 18)
    
    // Texto
    ctx.fillStyle = '#000'
    ctx.fillText(label, x + 5, y - 6)
    
    // Track ID si existe
    if (det.track_id) {
      ctx.fillStyle = 'rgba(255,255,255,0.8)'
      ctx.fillText(`ID: ${det.track_id}`, x + 5, y + h + 14)
    }
  })
}

/**
 * Limpieza
 */
function cleanup() {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  if (animationFrameId) {
    cancelAnimationFrame(animationFrameId)
    animationFrameId = null
  }
}

/**
 * Controles
 */
function togglePlay() {
  const video = videoRef.value
  if (!video) return
  
  if (video.paused) {
    video.play()
    isPlaying.value = true
  } else {
    video.pause()
    isPlaying.value = false
  }
}

function toggleFullscreen() {
  const container = containerRef.value
  if (!container) return
  
  if (document.fullscreenElement) {
    document.exitFullscreen()
  } else {
    container.requestFullscreen()
  }
}

function takeSnapshot() {
  const video = videoRef.value
  const canvas = canvasRef.value
  if (!video || !canvas) return
  
  // Crear canvas temporal con video + overlay
  const tempCanvas = document.createElement('canvas')
  tempCanvas.width = video.videoWidth || canvas.width
  tempCanvas.height = video.videoHeight || canvas.height
  const ctx = tempCanvas.getContext('2d')
  
  // Dibujar video
  ctx.drawImage(video, 0, 0)
  
  // Dibujar overlay
  ctx.drawImage(canvas, 0, 0, tempCanvas.width, tempCanvas.height)
  
  // Descargar
  const link = document.createElement('a')
  link.download = `camera_${props.cameraId}_${Date.now()}.png`
  link.href = tempCanvas.toDataURL('image/png')
  link.click()
}

// Expose for parent
defineExpose({
  togglePlay,
  toggleFullscreen,
  takeSnapshot,
  currentMode,
  streamStats
})
</script>

<template>
  <div ref="containerRef" class="smart-player">
    <!-- Loading -->
    <div v-if="isLoading" class="loading-overlay">
      <div class="spinner"></div>
      <span>Conectando a cámara {{ cameraId }}...</span>
      <span class="mode-text">Detectando mejor protocolo...</span>
    </div>
    
    <!-- Error -->
    <div v-else-if="errorMessage" class="error-overlay">
      <span class="error-icon">⚠️</span>
      <span>{{ errorMessage }}</span>
      <button @click="detectBestProtocol">Reintentar</button>
    </div>
    
    <!-- Video Layer -->
    <template v-else>
      <!-- MJPEG Fallback (usa img) -->
      <img 
        v-if="currentMode === 'mjpeg'"
        :src="streamUrl.mjpeg"
        class="video-layer"
        alt="Camera stream"
      />
      
      <!-- WebRTC/HLS (usa video) -->
      <video
        v-else
        ref="videoRef"
        class="video-layer"
        :autoplay="autoplay"
        :muted="muted"
        playsinline
        @playing="isPlaying = true"
        @pause="isPlaying = false"
      />
    </template>
    
    <!-- Canvas Overlay -->
    <canvas 
      ref="canvasRef" 
      class="overlay-layer"
      :class="{ hidden: !showOverlay }"
    />
    
    <!-- Controls -->
    <div v-if="showControls && !isLoading && !errorMessage" class="controls">
      <button @click="togglePlay" class="ctrl-btn" :title="isPlaying ? 'Pausar' : 'Reproducir'">
        {{ isPlaying ? '⏸️' : '▶️' }}
      </button>
      <button @click="takeSnapshot" class="ctrl-btn" title="Capturar">
        📷
      </button>
      <button @click="toggleFullscreen" class="ctrl-btn" title="Pantalla completa">
        🔲
      </button>
      
      <div class="stream-info">
        <span class="protocol-badge" :class="currentMode">
          {{ currentMode.toUpperCase() }}
        </span>
        <span v-if="detections.length" class="detection-count">
          🎯 {{ detections.length }}
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.smart-player {
  position: relative;
  width: 100%;
  height: 100%;
  background: #0d1117;
  border-radius: 8px;
  overflow: hidden;
}

.video-layer {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.overlay-layer {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.overlay-layer.hidden {
  display: none;
}

.loading-overlay,
.error-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  background: rgba(13, 17, 23, 0.95);
  color: #e6edf3;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid #30363d;
  border-top-color: #a855f7;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.mode-text {
  font-size: 0.85rem;
  color: #8b949e;
}

.error-icon {
  font-size: 2rem;
}

.error-overlay button {
  padding: 0.5rem 1rem;
  background: #238636;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.controls {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem;
  background: linear-gradient(transparent, rgba(0,0,0,0.8));
}

.ctrl-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255,255,255,0.1);
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 1.1rem;
  transition: background 0.2s;
}

.ctrl-btn:hover {
  background: rgba(255,255,255,0.2);
}

.stream-info {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.protocol-badge {
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 600;
}

.protocol-badge.webrtc {
  background: rgba(34, 197, 94, 0.2);
  color: #22c55e;
}

.protocol-badge.hls {
  background: rgba(59, 130, 246, 0.2);
  color: #3b82f6;
}

.protocol-badge.mjpeg {
  background: rgba(245, 158, 11, 0.2);
  color: #f59e0b;
}

.detection-count {
  color: #a855f7;
  font-size: 0.85rem;
  font-weight: 500;
}
</style>
