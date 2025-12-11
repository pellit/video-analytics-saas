<template>
  <div class="octopus-container">
    <!-- Navbar Superior -->
    <nav class="octopus-nav">
      <div class="nav-left">
        <div class="logo">
          <span class="logo-icon">🐙</span>
          <span class="logo-text">Octopus<span class="highlight">AI</span></span>
        </div>
        <div class="search-box">
          <input 
            type="text" 
            v-model="searchQuery" 
            placeholder="Buscar cámaras, alertas..."
            @keyup.enter="handleSearch"
          />
          <span class="search-icon">🔍</span>
        </div>
      </div>
      
      <div class="nav-center">
        <div class="system-status">
          <div class="status-item" :class="{ 'status-ok': systemHealth.cpu < 80 }">
            <span class="status-label">CPU</span>
            <span class="status-value">{{ systemHealth.cpu }}%</span>
          </div>
          <div class="status-item" :class="{ 'status-ok': systemHealth.ram < 80 }">
            <span class="status-label">RAM</span>
            <span class="status-value">{{ systemHealth.ram }}%</span>
          </div>
          <div class="status-item status-ok">
            <span class="status-label">Cámaras</span>
            <span class="status-value">{{ activeCameras }}/{{ totalCameras }}</span>
          </div>
        </div>
      </div>
      
      <div class="nav-right">
        <!-- Subscription Banner Mini -->
        <div class="plan-badge" :class="planClass" @click="showPricing = true">
          <span class="plan-icon">{{ planIcon }}</span>
          <span class="plan-name">{{ user?.plan?.display_name || 'Free' }}</span>
          <span v-if="!user?.is_superadmin && needsUpgrade" class="upgrade-hint">⬆️</span>
        </div>
        
        <div class="user-menu" @click="showUserMenu = !showUserMenu">
          <div class="avatar">{{ userInitials }}</div>
          <span class="user-name">{{ user?.name }}</span>
          <span class="dropdown-arrow">▼</span>
          
          <div v-if="showUserMenu" class="dropdown-menu">
            <a @click="$emit('navigate', 'dashboard')">📊 Dashboard</a>
            <a v-if="user?.role === 'superadmin'" @click="$emit('navigate', 'admin')">⚙️ Admin</a>
            <a @click="showPricing = true">💳 Planes</a>
            <a @click="showUsage = true">📈 Mi Uso</a>
            <div class="divider"></div>
            <a @click="$emit('logout')" class="logout">🚪 Cerrar Sesión</a>
          </div>
        </div>
      </div>
    </nav>

    <!-- Main Content: The Brain -->
    <main class="brain-core" @click="closeMenus">
      <!-- Video Principal -->
      <div class="video-container">
        <SmartPlayer 
          v-if="selectedCamera"
          :camera-id="selectedCamera.id"
          :camera="selectedCamera"
          :token="token"
          mode="webrtc"
          @detection="handleDetection"
        />
        <div v-else class="no-camera-selected">
          <div class="empty-state">
            <span class="empty-icon">📹</span>
            <h3>Selecciona una cámara</h3>
            <p>Arrastra una cámara desde el panel izquierdo o haz clic en una miniatura</p>
          </div>
        </div>
        
        <!-- Overlay de detecciones -->
        <div v-if="showDetectionOverlay && currentDetections.length" class="detection-overlay">
          <div 
            v-for="det in currentDetections" 
            :key="det.id"
            class="detection-box"
            :class="det.class"
            :style="getDetectionStyle(det)"
          >
            <span class="det-label">{{ det.class }} {{ (det.confidence * 100).toFixed(0) }}%</span>
          </div>
        </div>
      </div>
      
      <!-- Alert Toast -->
      <Transition name="slide">
        <div v-if="latestAlert" class="alert-toast" :class="latestAlert.severity">
          <span class="alert-icon">{{ getAlertIcon(latestAlert) }}</span>
          <div class="alert-content">
            <strong>{{ latestAlert.title }}</strong>
            <p>{{ latestAlert.message }}</p>
          </div>
          <button @click="latestAlert = null" class="close-btn">×</button>
        </div>
      </Transition>
    </main>

    <!-- Tentacle 1: Vision Panel (Cameras) - Top Left -->
    <aside class="tentacle vision-panel">
      <div class="glass-card">
        <div class="panel-header">
          <h3>👁️ Cámaras</h3>
          <button 
            v-if="canAddCamera" 
            @click="showAddCamera = true" 
            class="add-btn"
            title="Agregar cámara"
          >+</button>
        </div>
        
        <div class="cam-grid">
          <div 
            v-for="cam in cameras" 
            :key="cam.id"
            class="cam-thumb"
            :class="{ 
              'selected': selectedCamera?.id === cam.id,
              'has-alert': cam.hasAlert,
              'inactive': cam.status !== 'active'
            }"
            @click="selectCamera(cam)"
            draggable="true"
            @dragstart="onDragStart($event, cam)"
          >
            <div class="cam-preview">
              <img v-if="cam.thumbnail" :src="cam.thumbnail" :alt="cam.name" />
              <div v-else class="cam-placeholder">📹</div>
              <span v-if="cam.hasAlert" class="pulse-red"></span>
              <span class="cam-status" :class="cam.status">●</span>
            </div>
            <span class="cam-name">{{ cam.name }}</span>
          </div>
        </div>
        
        <!-- Límite de cámaras -->
        <div v-if="!user?.is_superadmin" class="limit-indicator">
          <div class="limit-bar">
            <div 
              class="limit-fill" 
              :style="{ width: cameraUsagePercent + '%' }"
              :class="{ 'limit-warning': cameraUsagePercent > 80 }"
            ></div>
          </div>
          <span class="limit-text">{{ cameras.length }}/{{ cameraLimit }} cámaras</span>
        </div>
      </div>
    </aside>

    <!-- Tentacle 2: Audio Panel - Top Right -->
    <aside class="tentacle audio-panel">
      <div class="glass-card">
        <div class="panel-header">
          <h3>👂 Transcripción</h3>
          <button @click="toggleAudio" class="toggle-btn" :class="{ active: audioEnabled }">
            {{ audioEnabled ? '🔊' : '🔇' }}
          </button>
        </div>
        
        <div class="transcript-stream" ref="transcriptRef">
          <p 
            v-for="(line, i) in transcripts" 
            :key="i"
            :class="{ 'danger': line.isAlert, 'highlight': line.isKeyword }"
            @click="jumpToTime(line.timestamp)"
          >
            <small class="time">{{ formatTime(line.timestamp) }}</small>
            <span class="text">{{ line.text }}</span>
          </p>
          <p v-if="!transcripts.length" class="empty">
            <em>Esperando transcripción de audio...</em>
          </p>
        </div>
        
        <!-- Audio Waveform -->
        <div class="waveform" v-if="audioEnabled">
          <div 
            v-for="n in 20" 
            :key="n" 
            class="bar" 
            :style="{ height: getWaveHeight(n) + '%' }"
          ></div>
        </div>
      </div>
    </aside>

    <!-- Tentacle 3: Context Panel (Map/CAD) - Bottom Left -->
    <aside class="tentacle context-panel">
      <div class="glass-card">
        <div class="panel-header">
          <h3>🗺️ Contexto</h3>
          <div class="context-tabs">
            <button 
              :class="{ active: contextMode === 'map' }" 
              @click="contextMode = 'map'"
              :disabled="!canUseSatellite"
            >Mapa</button>
            <button 
              :class="{ active: contextMode === 'cad' }" 
              @click="contextMode = 'cad'"
              :disabled="!canUseCad"
            >CAD</button>
          </div>
        </div>
        
        <div class="context-content">
          <!-- Mini Map -->
          <div v-if="contextMode === 'map'" class="mini-map">
            <div v-if="canUseSatellite" class="map-placeholder">
              <SatellitePanel 
                v-if="selectedCamera?.location"
                :camera="selectedCamera"
                :token="token"
                mini
              />
              <div v-else class="empty">
                <span>🛰️</span>
                <p>Configura ubicación</p>
              </div>
            </div>
            <div v-else class="feature-locked">
              <span class="lock-icon">🔒</span>
              <p>Satélite requiere Plan Business</p>
              <button @click="showPricing = true" class="upgrade-btn">Actualizar</button>
            </div>
          </div>
          
          <!-- CAD Overlay -->
          <div v-else class="cad-view">
            <div v-if="canUseCad" class="cad-placeholder">
              <BlueprintPanel 
                v-if="selectedCamera?.blueprint"
                :camera="selectedCamera"
                :token="token"
                mini
              />
              <div v-else class="empty">
                <span>🏗️</span>
                <p>Sube un plano CAD</p>
              </div>
            </div>
            <div v-else class="feature-locked">
              <span class="lock-icon">🔒</span>
              <p>CAD requiere Plan Business</p>
              <button @click="showPricing = true" class="upgrade-btn">Actualizar</button>
            </div>
          </div>
        </div>
        
        <!-- Overlay Toggle -->
        <div class="overlay-controls" v-if="contextMode === 'cad' && canUseCad">
          <label class="toggle-label">
            <input type="checkbox" v-model="showCadOverlay" />
            <span>Superponer en video</span>
          </label>
        </div>
      </div>
    </aside>

    <!-- Tentacle 4: Data Panel (Metrics) - Bottom Right -->
    <aside class="tentacle data-panel">
      <div class="glass-card">
        <div class="panel-header">
          <h3>🧠 Métricas</h3>
          <select v-model="metricsTimeframe" class="timeframe-select">
            <option value="1h">1 hora</option>
            <option value="24h">24 horas</option>
            <option value="7d">7 días</option>
          </select>
        </div>
        
        <!-- Sparkline Charts -->
        <div class="metrics-grid">
          <div class="metric-card">
            <span class="metric-label">Personas</span>
            <span class="metric-value">{{ metrics.personCount }}</span>
            <div class="sparkline">
              <svg viewBox="0 0 100 30">
                <polyline 
                  :points="getSparklinePoints(metrics.personHistory)"
                  fill="none"
                  stroke="#3b82f6"
                  stroke-width="2"
                />
              </svg>
            </div>
          </div>
          
          <div class="metric-card">
            <span class="metric-label">Vehículos</span>
            <span class="metric-value">{{ metrics.vehicleCount }}</span>
            <div class="sparkline">
              <svg viewBox="0 0 100 30">
                <polyline 
                  :points="getSparklinePoints(metrics.vehicleHistory)"
                  fill="none"
                  stroke="#10b981"
                  stroke-width="2"
                />
              </svg>
            </div>
          </div>
          
          <div class="metric-card alert-metric" v-if="metrics.alertCount > 0">
            <span class="metric-label">⚠️ Alertas</span>
            <span class="metric-value danger">{{ metrics.alertCount }}</span>
          </div>
        </div>
        
        <!-- Recent Alerts List -->
        <div class="recent-alerts">
          <h4>Alertas Recientes</h4>
          <div class="alert-list">
            <div 
              v-for="alert in recentAlerts.slice(0, 5)" 
              :key="alert.id"
              class="alert-item"
              :class="alert.severity"
              @click="focusAlert(alert)"
            >
              <span class="alert-time">{{ formatTime(alert.created_at) }}</span>
              <span class="alert-type">{{ alert.type }}</span>
              <span class="alert-camera">{{ alert.camera_name }}</span>
            </div>
            <p v-if="!recentAlerts.length" class="empty">
              Sin alertas recientes
            </p>
          </div>
        </div>
      </div>
    </aside>

    <!-- Modals -->
    <Teleport to="body">
      <!-- Pricing Modal -->
      <Transition name="fade">
        <div v-if="showPricing" class="modal-overlay" @click.self="showPricing = false">
          <PricingPlans 
            :current-plan="user?.plan?.name"
            :is-superadmin="user?.is_superadmin"
            :token="token"
            @close="showPricing = false"
            @plan-selected="handlePlanSelected"
          />
        </div>
      </Transition>
      
      <!-- Usage Modal -->
      <Transition name="fade">
        <div v-if="showUsage" class="modal-overlay" @click.self="showUsage = false">
          <UsageStats 
            :token="token"
            :user="user"
            @close="showUsage = false"
          />
        </div>
      </Transition>
      
      <!-- Add Camera Modal -->
      <Transition name="fade">
        <div v-if="showAddCamera" class="modal-overlay" @click.self="showAddCamera = false">
          <AddCameraModal 
            :token="token"
            @close="showAddCamera = false"
            @camera-added="handleCameraAdded"
          />
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import SmartPlayer from './SmartPlayer.vue'
import SatellitePanel from './SatellitePanel.vue'
import BlueprintPanel from './BlueprintPanel.vue'
import PricingPlans from './billing/PricingPlans.vue'
import UsageStats from './billing/UsageStats.vue'
import AddCameraModal from './AddCameraModal.vue'

const props = defineProps({
  token: String,
  user: Object
})

const emit = defineEmits(['logout', 'navigate'])

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'
const STREAM_URL = import.meta.env.VITE_STREAM_URL || 'http://localhost:5000/video_feed'

// Helper to get Worker base URL (for SSE events) - works in both dev and prod
const getWorkerBaseUrl = () => {
  if (import.meta.env.VITE_WORKER_URL) return import.meta.env.VITE_WORKER_URL
  // In production (non-localhost), use the Traefik route
  if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
    return `${window.location.origin}/worker`
  }
  // In dev, use STREAM_URL with /video_feed stripped
  return STREAM_URL.replace('/video_feed', '')
}
const WORKER_BASE_URL = getWorkerBaseUrl()

// ============================================================================
// STATE
// ============================================================================

// Cameras
const cameras = ref([])
const selectedCamera = ref(null)
const totalCameras = computed(() => cameras.value.length)
const activeCameras = computed(() => cameras.value.filter(c => c.status === 'active').length)

// UI State
const searchQuery = ref('')
const showUserMenu = ref(false)
const showPricing = ref(false)
const showUsage = ref(false)
const showAddCamera = ref(false)
const showDetectionOverlay = ref(true)
const showCadOverlay = ref(false)

// Panels
const contextMode = ref('map')
const audioEnabled = ref(false)
const metricsTimeframe = ref('1h')

// Data
const transcripts = ref([])
const currentDetections = ref([])
const recentAlerts = ref([])
const latestAlert = ref(null)
const metrics = ref({
  personCount: 0,
  vehicleCount: 0,
  alertCount: 0,
  personHistory: [],
  vehicleHistory: []
})

// System
const systemHealth = ref({ cpu: 0, ram: 0 })

// SSE Connection
let eventSource = null

// ============================================================================
// COMPUTED
// ============================================================================

const userInitials = computed(() => {
  if (!props.user?.name) return '?'
  return props.user.name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
})

const planClass = computed(() => {
  const plan = props.user?.plan?.name || 'free'
  return `plan-${plan}`
})

const planIcon = computed(() => {
  const plan = props.user?.plan?.name || 'free'
  const icons = { free: '🆓', pro: '⭐', business: '🚀', enterprise: '👑' }
  return icons[plan] || '🆓'
})

const needsUpgrade = computed(() => {
  if (props.user?.is_superadmin) return false
  const limits = props.user?.limits
  if (!limits) return false
  return limits.cameras?.remaining <= 0 || limits.analysis_hours?.used_today >= limits.analysis_hours?.limit
})

const cameraLimit = computed(() => {
  return props.user?.limits?.cameras?.limit || 1
})

const cameraUsagePercent = computed(() => {
  const limit = cameraLimit.value
  if (limit === '∞' || limit === 0) return 0
  return Math.min(100, (cameras.value.length / limit) * 100)
})

const canAddCamera = computed(() => {
  if (props.user?.is_superadmin) return true
  return props.user?.limits?.cameras?.remaining > 0
})

const canUseSatellite = computed(() => {
  if (props.user?.is_superadmin) return true
  return props.user?.limits?.features?.satellite
})

const canUseCad = computed(() => {
  if (props.user?.is_superadmin) return true
  return props.user?.limits?.features?.cad
})

// ============================================================================
// METHODS
// ============================================================================

const fetchCameras = async () => {
  try {
    const res = await fetch(`${API_URL}/cameras`, {
      headers: { 'Authorization': `Bearer ${props.token}` }
    })
    if (res.ok) {
      cameras.value = await res.json()
      if (cameras.value.length && !selectedCamera.value) {
        selectedCamera.value = cameras.value[0]
      }
    }
  } catch (e) {
    console.error('Error fetching cameras:', e)
  }
}

const fetchAlerts = async () => {
  try {
    const res = await fetch(`${API_URL}/alerts/recent?limit=10`, {
      headers: { 'Authorization': `Bearer ${props.token}` }
    })
    if (res.ok) {
      recentAlerts.value = await res.json()
    }
  } catch (e) {
    console.error('Error fetching alerts:', e)
  }
}

const selectCamera = (cam) => {
  selectedCamera.value = cam
}

const handleSearch = () => {
  // TODO: Implement search
  console.log('Search:', searchQuery.value)
}

const closeMenus = () => {
  showUserMenu.value = false
}

const toggleAudio = () => {
  audioEnabled.value = !audioEnabled.value
}

const handleDetection = (detection) => {
  currentDetections.value = detection.detections || []
  
  // Update metrics
  const persons = currentDetections.value.filter(d => d.class === 'person').length
  const vehicles = currentDetections.value.filter(d => ['car', 'truck', 'bus', 'motorcycle'].includes(d.class)).length
  
  metrics.value.personCount = persons
  metrics.value.vehicleCount = vehicles
  metrics.value.personHistory.push(persons)
  metrics.value.vehicleHistory.push(vehicles)
  
  // Keep only last 20 points
  if (metrics.value.personHistory.length > 20) metrics.value.personHistory.shift()
  if (metrics.value.vehicleHistory.length > 20) metrics.value.vehicleHistory.shift()
}

const handlePlanSelected = async (plan) => {
  showPricing.value = false
  // Refresh user data
  emit('navigate', 'dashboard')
}

const handleCameraAdded = (camera) => {
  cameras.value.push(camera)
  showAddCamera.value = false
  selectCamera(camera)
}

const getDetectionStyle = (det) => {
  return {
    left: `${det.x * 100}%`,
    top: `${det.y * 100}%`,
    width: `${det.w * 100}%`,
    height: `${det.h * 100}%`
  }
}

const getAlertIcon = (alert) => {
  const icons = {
    high: '🚨',
    medium: '⚠️',
    low: '📢'
  }
  return icons[alert.severity] || '📢'
}

const formatTime = (timestamp) => {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' })
}

const jumpToTime = (timestamp) => {
  // TODO: Implement time seeking in video
  console.log('Jump to:', timestamp)
}

const focusAlert = (alert) => {
  // Find camera and select it
  const cam = cameras.value.find(c => c.id === alert.camera_id)
  if (cam) selectCamera(cam)
}

const getWaveHeight = (n) => {
  if (!audioEnabled.value) return 5
  return Math.random() * 80 + 10
}

const getSparklinePoints = (data) => {
  if (!data || !data.length) return '0,30 100,30'
  const max = Math.max(...data, 1)
  return data.map((v, i) => {
    const x = (i / (data.length - 1)) * 100
    const y = 30 - (v / max) * 25
    return `${x},${y}`
  }).join(' ')
}

const onDragStart = (event, cam) => {
  event.dataTransfer.setData('camera', JSON.stringify(cam))
}

// ============================================================================
// SSE CONNECTION (via AI Worker)
// ============================================================================

const connectSSE = () => {
  if (eventSource) eventSource.close()
  
  // Use AI Worker SSE endpoint instead of backend PHP
  const url = `${WORKER_BASE_URL}/stream/events`
  console.log('🐙 Connecting SSE to:', url)
  eventSource = new EventSource(url)
  
  eventSource.addEventListener('connected', (e) => {
    console.log('🐙 SSE Connected:', e.data)
  })
  
  eventSource.addEventListener('detections', (e) => {
    try {
      const data = JSON.parse(e.data)
      if (data.camera_id === selectedCamera.value?.id) {
        handleDetection({ detections: data.detections || [] })
      }
    } catch (err) {
      console.error('SSE detections parse error:', err)
    }
  })
  
  eventSource.addEventListener('alerts', (e) => {
    try {
      const data = JSON.parse(e.data)
      recentAlerts.value.unshift(data)
      if (recentAlerts.value.length > 20) recentAlerts.value.pop()
      
      latestAlert.value = data
      setTimeout(() => {
        if (latestAlert.value?.id === data.id) latestAlert.value = null
      }, 5000)
      
      metrics.value.alertCount++
    } catch (err) {
      console.error('SSE alert parse error:', err)
    }
  })

  eventSource.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data)
      
      if (data.type === 'detection' && data.camera_id === selectedCamera.value?.id) {
        handleDetection(data)
      }
      
      if (data.type === 'alert') {
        recentAlerts.value.unshift(data)
        if (recentAlerts.value.length > 20) recentAlerts.value.pop()
        
        latestAlert.value = data
        setTimeout(() => {
          if (latestAlert.value?.id === data.id) latestAlert.value = null
        }, 5000)
        
        metrics.value.alertCount++
      }
      
      if (data.type === 'transcript') {
        transcripts.value.push(data)
        if (transcripts.value.length > 50) transcripts.value.shift()
      }
      
    } catch (err) {
      console.error('SSE parse error:', err)
    }
  }
  
  eventSource.onerror = () => {
    console.warn('SSE connection lost, reconnecting...')
    setTimeout(connectSSE, 3000)
  }
}

// ============================================================================
// LIFECYCLE
// ============================================================================

onMounted(async () => {
  await Promise.all([
    fetchCameras(),
    fetchAlerts()
  ])
  connectSSE()
})

onUnmounted(() => {
  if (eventSource) eventSource.close()
})
</script>

<style scoped>
/* ============================================================================
   OCTOPUS LAYOUT - GLASSMORPHISM DESIGN
   ============================================================================ */

.octopus-container {
  display: grid;
  height: 100vh;
  width: 100vw;
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%);
  grid-template-columns: 280px 1fr 280px;
  grid-template-rows: 60px 1fr 1fr;
  gap: 16px;
  padding: 16px;
  position: relative;
  overflow: hidden;
}

/* Background animated gradient */
.octopus-container::before {
  content: '';
  position: absolute;
  top: -50%;
  left: -50%;
  width: 200%;
  height: 200%;
  background: radial-gradient(circle at 30% 30%, rgba(59, 130, 246, 0.1) 0%, transparent 50%),
              radial-gradient(circle at 70% 70%, rgba(16, 185, 129, 0.1) 0%, transparent 50%);
  animation: bgPulse 20s ease infinite;
  pointer-events: none;
  z-index: 0;
}

@keyframes bgPulse {
  0%, 100% { transform: translate(0, 0); }
  50% { transform: translate(-5%, -5%); }
}

/* ============================================================================
   NAVBAR
   ============================================================================ */

.octopus-nav {
  grid-column: 1 / -1;
  grid-row: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  background: rgba(30, 41, 59, 0.8);
  backdrop-filter: blur(12px);
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  z-index: 100;
}

.nav-left, .nav-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.logo {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 1.25rem;
  font-weight: 700;
}

.logo-icon {
  font-size: 1.5rem;
}

.logo-text .highlight {
  color: #3b82f6;
}

.search-box {
  position: relative;
}

.search-box input {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  padding: 8px 36px 8px 12px;
  color: white;
  width: 200px;
  transition: all 0.3s;
}

.search-box input:focus {
  outline: none;
  border-color: #3b82f6;
  width: 280px;
}

.search-icon {
  position: absolute;
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
  opacity: 0.5;
}

.system-status {
  display: flex;
  gap: 20px;
}

.status-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  font-size: 0.75rem;
  opacity: 0.7;
}

.status-item.status-ok {
  opacity: 1;
}

.status-value {
  font-weight: 600;
  font-size: 0.875rem;
}

.plan-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 20px;
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s;
}

.plan-free { background: rgba(100, 116, 139, 0.3); }
.plan-pro { background: rgba(59, 130, 246, 0.3); border: 1px solid #3b82f6; }
.plan-business { background: rgba(16, 185, 129, 0.3); border: 1px solid #10b981; }
.plan-enterprise { background: rgba(168, 85, 247, 0.3); border: 1px solid #a855f7; }

.plan-badge:hover {
  transform: scale(1.05);
}

.upgrade-hint {
  animation: bounce 1s infinite;
}

@keyframes bounce {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-3px); }
}

.user-menu {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 6px 10px;
  border-radius: 8px;
  position: relative;
}

.user-menu:hover {
  background: rgba(255, 255, 255, 0.1);
}

.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: linear-gradient(135deg, #3b82f6, #8b5cf6);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.75rem;
  font-weight: 600;
}

.dropdown-arrow {
  font-size: 0.6rem;
  opacity: 0.5;
}

.dropdown-menu {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 8px;
  background: rgba(30, 41, 59, 0.95);
  backdrop-filter: blur(12px);
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  padding: 8px;
  min-width: 180px;
  z-index: 1000;
}

.dropdown-menu a {
  display: block;
  padding: 10px 12px;
  border-radius: 6px;
  color: white;
  text-decoration: none;
  cursor: pointer;
  transition: background 0.2s;
}

.dropdown-menu a:hover {
  background: rgba(255, 255, 255, 0.1);
}

.dropdown-menu .divider {
  height: 1px;
  background: rgba(255, 255, 255, 0.1);
  margin: 8px 0;
}

.dropdown-menu .logout:hover {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
}

/* ============================================================================
   BRAIN CORE (Main Video)
   ============================================================================ */

.brain-core {
  grid-column: 2;
  grid-row: 2 / 4;
  z-index: 1;
  border-radius: 20px;
  overflow: hidden;
  box-shadow: 0 0 60px rgba(0, 0, 0, 0.5);
  position: relative;
  background: #000;
}

.video-container {
  width: 100%;
  height: 100%;
  position: relative;
}

.no-camera-selected {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1e293b, #0f172a);
}

.empty-state {
  text-align: center;
  color: rgba(255, 255, 255, 0.5);
}

.empty-icon {
  font-size: 4rem;
  display: block;
  margin-bottom: 16px;
}

.detection-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.detection-box {
  position: absolute;
  border: 2px solid #3b82f6;
  border-radius: 4px;
}

.detection-box.person { border-color: #10b981; }
.detection-box.car { border-color: #f59e0b; }
.detection-box.weapon { border-color: #ef4444; animation: pulse-border 0.5s infinite; }

@keyframes pulse-border {
  0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7); }
  50% { box-shadow: 0 0 0 10px rgba(239, 68, 68, 0); }
}

.det-label {
  position: absolute;
  top: -20px;
  left: 0;
  background: rgba(0, 0, 0, 0.7);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.7rem;
  white-space: nowrap;
}

.alert-toast {
  position: absolute;
  top: 20px;
  right: 20px;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  background: rgba(30, 41, 59, 0.95);
  backdrop-filter: blur(12px);
  border-radius: 12px;
  border-left: 4px solid;
  max-width: 400px;
  z-index: 100;
}

.alert-toast.high { border-color: #ef4444; }
.alert-toast.medium { border-color: #f59e0b; }
.alert-toast.low { border-color: #3b82f6; }

.alert-icon {
  font-size: 1.5rem;
}

.alert-content strong {
  display: block;
  margin-bottom: 4px;
}

.alert-content p {
  margin: 0;
  font-size: 0.875rem;
  opacity: 0.8;
}

.close-btn {
  background: none;
  border: none;
  color: white;
  font-size: 1.25rem;
  cursor: pointer;
  opacity: 0.5;
}

.close-btn:hover {
  opacity: 1;
}

/* ============================================================================
   TENTACLES (Glass Panels)
   ============================================================================ */

.tentacle {
  z-index: 10;
}

.glass-card {
  background: rgba(30, 41, 59, 0.7);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 16px;
  padding: 16px;
  height: 100%;
  color: white;
  transition: all 0.3s ease;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.glass-card:hover {
  background: rgba(30, 41, 59, 0.85);
  border-color: rgba(255, 255, 255, 0.2);
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  flex-shrink: 0;
}

.panel-header h3 {
  margin: 0;
  font-size: 0.9rem;
  font-weight: 600;
}

.add-btn, .toggle-btn {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: rgba(255, 255, 255, 0.1);
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.add-btn:hover, .toggle-btn:hover {
  background: rgba(59, 130, 246, 0.3);
  border-color: #3b82f6;
}

.toggle-btn.active {
  background: rgba(16, 185, 129, 0.3);
  border-color: #10b981;
}

/* Vision Panel */
.vision-panel {
  grid-column: 1;
  grid-row: 2;
}

.cam-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  flex: 1;
  overflow-y: auto;
}

.cam-thumb {
  background: rgba(0, 0, 0, 0.3);
  border-radius: 8px;
  padding: 6px;
  cursor: pointer;
  transition: all 0.2s;
  border: 2px solid transparent;
}

.cam-thumb:hover {
  background: rgba(59, 130, 246, 0.2);
}

.cam-thumb.selected {
  border-color: #3b82f6;
  background: rgba(59, 130, 246, 0.2);
}

.cam-thumb.has-alert {
  border-color: #ef4444;
  animation: pulse-glow 1s infinite;
}

@keyframes pulse-glow {
  0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.5); }
  50% { box-shadow: 0 0 10px 5px rgba(239, 68, 68, 0.3); }
}

.cam-thumb.inactive {
  opacity: 0.5;
}

.cam-preview {
  position: relative;
  aspect-ratio: 16/9;
  background: #1e293b;
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 4px;
}

.cam-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.cam-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5rem;
}

.pulse-red {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 8px;
  height: 8px;
  background: #ef4444;
  border-radius: 50%;
  animation: pulse 1s infinite;
}

@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.5); opacity: 0.5; }
}

.cam-status {
  position: absolute;
  bottom: 4px;
  left: 4px;
  font-size: 0.5rem;
}

.cam-status.active { color: #10b981; }
.cam-status.inactive { color: #64748b; }
.cam-status.error { color: #ef4444; }

.cam-name {
  font-size: 0.7rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
}

.limit-indicator {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.limit-bar {
  height: 4px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 2px;
  overflow: hidden;
}

.limit-fill {
  height: 100%;
  background: #3b82f6;
  transition: width 0.3s;
}

.limit-fill.limit-warning {
  background: #f59e0b;
}

.limit-text {
  font-size: 0.7rem;
  opacity: 0.6;
  margin-top: 4px;
  display: block;
}

/* Audio Panel */
.audio-panel {
  grid-column: 3;
  grid-row: 2;
}

.transcript-stream {
  flex: 1;
  overflow-y: auto;
  font-size: 0.8rem;
}

.transcript-stream p {
  margin: 4px 0;
  padding: 4px 8px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.2s;
}

.transcript-stream p:hover {
  background: rgba(255, 255, 255, 0.1);
}

.transcript-stream p.danger {
  background: rgba(239, 68, 68, 0.2);
  border-left: 2px solid #ef4444;
}

.transcript-stream p.highlight {
  background: rgba(59, 130, 246, 0.2);
}

.transcript-stream .time {
  opacity: 0.5;
  margin-right: 8px;
}

.transcript-stream .empty {
  opacity: 0.5;
  text-align: center;
  padding: 20px;
}

.waveform {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  height: 40px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.waveform .bar {
  width: 3px;
  background: #3b82f6;
  border-radius: 2px;
  transition: height 0.1s;
}

/* Context Panel */
.context-panel {
  grid-column: 1;
  grid-row: 3;
}

.context-tabs {
  display: flex;
  gap: 4px;
}

.context-tabs button {
  padding: 4px 10px;
  border-radius: 4px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: transparent;
  color: white;
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
}

.context-tabs button:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1);
}

.context-tabs button.active {
  background: rgba(59, 130, 246, 0.3);
  border-color: #3b82f6;
}

.context-tabs button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.context-content {
  flex: 1;
  margin-top: 12px;
  border-radius: 8px;
  overflow: hidden;
  background: rgba(0, 0, 0, 0.2);
}

.mini-map, .cad-view {
  height: 100%;
}

.feature-locked {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 20px;
}

.lock-icon {
  font-size: 2rem;
  margin-bottom: 8px;
}

.feature-locked p {
  font-size: 0.8rem;
  opacity: 0.7;
  margin-bottom: 12px;
}

.upgrade-btn {
  padding: 8px 16px;
  background: linear-gradient(135deg, #3b82f6, #8b5cf6);
  border: none;
  border-radius: 6px;
  color: white;
  font-size: 0.8rem;
  cursor: pointer;
  transition: transform 0.2s;
}

.upgrade-btn:hover {
  transform: scale(1.05);
}

.overlay-controls {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.75rem;
  cursor: pointer;
}

.toggle-label input {
  accent-color: #3b82f6;
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  opacity: 0.5;
  text-align: center;
}

.empty span {
  font-size: 2rem;
  margin-bottom: 8px;
}

/* Data Panel */
.data-panel {
  grid-column: 3;
  grid-row: 3;
}

.timeframe-select {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 4px;
  padding: 4px 8px;
  color: white;
  font-size: 0.75rem;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  margin-bottom: 12px;
}

.metric-card {
  background: rgba(0, 0, 0, 0.2);
  border-radius: 8px;
  padding: 10px;
}

.metric-label {
  font-size: 0.7rem;
  opacity: 0.7;
  display: block;
}

.metric-value {
  font-size: 1.25rem;
  font-weight: 700;
}

.metric-value.danger {
  color: #ef4444;
}

.sparkline {
  height: 30px;
  margin-top: 4px;
}

.sparkline svg {
  width: 100%;
  height: 100%;
}

.alert-metric {
  grid-column: span 2;
  background: rgba(239, 68, 68, 0.2);
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.recent-alerts h4 {
  font-size: 0.8rem;
  margin: 0 0 8px 0;
  opacity: 0.7;
}

.alert-list {
  flex: 1;
  overflow-y: auto;
}

.alert-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  cursor: pointer;
  transition: background 0.2s;
  border-left: 2px solid transparent;
}

.alert-item:hover {
  background: rgba(255, 255, 255, 0.1);
}

.alert-item.high { border-color: #ef4444; }
.alert-item.medium { border-color: #f59e0b; }
.alert-item.low { border-color: #3b82f6; }

.alert-time {
  opacity: 0.5;
}

.alert-type {
  flex: 1;
}

.alert-camera {
  opacity: 0.5;
}

/* ============================================================================
   MODALS
   ============================================================================ */

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

/* ============================================================================
   TRANSITIONS
   ============================================================================ */

.fade-enter-active, .fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from, .fade-leave-to {
  opacity: 0;
}

.slide-enter-active, .slide-leave-active {
  transition: all 0.3s ease;
}

.slide-enter-from {
  transform: translateX(100%);
  opacity: 0;
}

.slide-leave-to {
  transform: translateX(100%);
  opacity: 0;
}

/* ============================================================================
   RESPONSIVE
   ============================================================================ */

@media (max-width: 1200px) {
  .octopus-container {
    grid-template-columns: 240px 1fr 240px;
  }
}

@media (max-width: 900px) {
  .octopus-container {
    grid-template-columns: 1fr;
    grid-template-rows: 60px auto 300px;
  }
  
  .brain-core {
    grid-column: 1;
    grid-row: 2;
  }
  
  .tentacle {
    display: none;
  }
  
  .vision-panel {
    display: block;
    grid-column: 1;
    grid-row: 3;
  }
}
</style>
