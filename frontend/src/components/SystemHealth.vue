<script setup>
/**
 * SystemHealth.vue
 * ================
 * Panel de monitoreo de salud del sistema para Admin Dashboard.
 * Muestra estado de todos los servicios de la arquitectura.
 */

import { ref, onMounted, onUnmounted, computed } from 'vue'

const props = defineProps({
  workerUrl: { type: String, default: '' },
  apiUrl: { type: String, default: '' },
  mediamtxUrl: { type: String, default: '' }
})

const emit = defineEmits(['service-click'])

// Estado de servicios
const services = ref({
  api: { status: 'checking', latency: 0, details: {} },
  worker: { status: 'checking', latency: 0, details: {} },
  mediamtx: { status: 'checking', latency: 0, details: {} },
  redis: { status: 'checking', latency: 0, details: {} },
  database: { status: 'checking', latency: 0, details: {} }
})

const streams = ref([])
const systemMetrics = ref({
  totalCameras: 0,
  activeCameras: 0,
  totalDetections: 0,
  avgFps: 0,
  memoryUsage: 0,
  cpuUsage: 0
})

const lastUpdate = ref(null)
const isAutoRefresh = ref(true)
let refreshInterval = null

// URLs base
const getWorkerUrl = () => {
  if (props.workerUrl) return props.workerUrl
  const streamUrl = import.meta.env.VITE_STREAM_URL || ''
  // Use /worker prefix for nginx proxy when using relative paths
  if (streamUrl === '/video_feed') return '/worker'
  if (streamUrl) return streamUrl.replace('/video_feed', '')
  return 'http://localhost:5000'
}
const getApiUrl = () => props.apiUrl || import.meta.env.VITE_API_URL || 'http://localhost:8000/api'
const getMediamtxUrl = () => props.mediamtxUrl || 'http://localhost:9997'

// Computed
const overallStatus = computed(() => {
  const statuses = Object.values(services.value).map(s => s.status)
  if (statuses.every(s => s === 'online')) return 'healthy'
  if (statuses.some(s => s === 'offline')) return 'degraded'
  if (statuses.every(s => s === 'offline')) return 'offline'
  return 'checking'
})

const statusIcon = computed(() => ({
  healthy: '✅',
  degraded: '⚠️',
  offline: '❌',
  checking: '🔄'
}[overallStatus.value]))

const onlineCount = computed(() => 
  Object.values(services.value).filter(s => s.status === 'online').length
)

// Check all services
async function checkAllServices() {
  await Promise.all([
    checkApi(),
    checkWorker(),
    checkMediaMTX(),
    checkRedis(),
    checkDatabase()
  ])
  lastUpdate.value = new Date()
}

// Check Laravel API
async function checkApi() {
  const start = Date.now()
  try {
    const res = await fetch(`${getApiUrl()}/health`, { 
      method: 'GET',
      timeout: 5000 
    })
    const data = await res.json()
    services.value.api = {
      status: res.ok ? 'online' : 'offline',
      latency: Date.now() - start,
      details: data
    }
  } catch (e) {
    services.value.api = {
      status: 'offline',
      latency: 0,
      details: { error: e.message }
    }
  }
}

// Check AI Worker
async function checkWorker() {
  const start = Date.now()
  try {
    const res = await fetch(`${getWorkerUrl()}/health`)
    const data = await res.json()
    services.value.worker = {
      status: res.ok ? 'online' : 'offline',
      latency: Date.now() - start,
      details: data
    }
    
    // Actualizar streams activos
    if (data.active_streams) {
      streams.value = data.active_streams.map(id => ({
        id,
        status: 'active'
      }))
      systemMetrics.value.activeCameras = data.active_streams.length
    }
    
    // Obtener info del streamer MediaMTX
    try {
      const streamerRes = await fetch(`${getWorkerUrl()}/mediamtx/status`)
      const streamerData = await streamerRes.json()
      services.value.worker.details.mediamtx_streamer = streamerData
    } catch {}
    
  } catch (e) {
    services.value.worker = {
      status: 'offline',
      latency: 0,
      details: { error: e.message }
    }
  }
}

// Check MediaMTX
async function checkMediaMTX() {
  const start = Date.now()
  try {
    const res = await fetch(`${getMediamtxUrl()}/v3/paths/list`)
    const data = await res.json()
    
    const activeStreams = data.items?.filter(p => p.ready) || []
    
    services.value.mediamtx = {
      status: res.ok ? 'online' : 'offline',
      latency: Date.now() - start,
      details: {
        totalPaths: data.items?.length || 0,
        activeStreams: activeStreams.length,
        streams: activeStreams.map(p => ({
          name: p.name,
          ready: p.ready,
          readers: p.readers?.length || 0
        }))
      }
    }
  } catch (e) {
    services.value.mediamtx = {
      status: 'offline',
      latency: 0,
      details: { error: e.message, hint: 'MediaMTX may not be running' }
    }
  }
}

// Check Redis (via Worker)
async function checkRedis() {
  const start = Date.now()
  try {
    const res = await fetch(`${getWorkerUrl()}/redis/ping`)
    const data = await res.json()
    services.value.redis = {
      status: data.status === 'ok' ? 'online' : 'offline',
      latency: Date.now() - start,
      details: data
    }
  } catch (e) {
    // Fallback: si Worker responde, asumimos Redis ok
    if (services.value.worker.status === 'online') {
      services.value.redis = {
        status: 'online',
        latency: 0,
        details: { inferred: true }
      }
    } else {
      services.value.redis = {
        status: 'unknown',
        latency: 0,
        details: { error: 'Cannot verify without worker' }
      }
    }
  }
}

// Check Database (via API)
async function checkDatabase() {
  // Si API responde, la DB funciona
  if (services.value.api.status === 'online') {
    services.value.database = {
      status: 'online',
      latency: services.value.api.latency,
      details: { inferred: 'Via API health' }
    }
  } else {
    services.value.database = {
      status: 'unknown',
      latency: 0,
      details: { error: 'Cannot verify without API' }
    }
  }
}

// Toggle auto refresh
function toggleAutoRefresh() {
  isAutoRefresh.value = !isAutoRefresh.value
  if (isAutoRefresh.value) {
    startAutoRefresh()
  } else {
    stopAutoRefresh()
  }
}

function startAutoRefresh() {
  stopAutoRefresh()
  refreshInterval = setInterval(checkAllServices, 10000)
}

function stopAutoRefresh() {
  if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
}

// Service click handler
function onServiceClick(serviceName) {
  emit('service-click', {
    name: serviceName,
    data: services.value[serviceName]
  })
}

// Lifecycle
onMounted(() => {
  checkAllServices()
  if (isAutoRefresh.value) {
    startAutoRefresh()
  }
})

onUnmounted(() => {
  stopAutoRefresh()
})

// Expose for parent
defineExpose({
  refresh: checkAllServices,
  services,
  streams,
  overallStatus
})
</script>

<template>
  <div class="system-health">
    <!-- Header -->
    <div class="health-header">
      <div class="header-left">
        <span class="status-icon">{{ statusIcon }}</span>
        <div class="header-text">
          <h3>Estado del Sistema</h3>
          <span class="status-label" :class="overallStatus">
            {{ overallStatus === 'healthy' ? 'Todos los servicios operativos' :
               overallStatus === 'degraded' ? 'Algunos servicios con problemas' :
               overallStatus === 'offline' ? 'Sistema no disponible' : 'Verificando...' }}
          </span>
        </div>
      </div>
      <div class="header-right">
        <span class="online-count">{{ onlineCount }}/{{ Object.keys(services).length }} online</span>
        <button class="btn-refresh" @click="checkAllServices" title="Actualizar ahora">
          🔄
        </button>
        <button 
          class="btn-auto" 
          :class="{ active: isAutoRefresh }"
          @click="toggleAutoRefresh"
          :title="isAutoRefresh ? 'Desactivar auto-refresh' : 'Activar auto-refresh'"
        >
          {{ isAutoRefresh ? '⏸️' : '▶️' }}
        </button>
      </div>
    </div>

    <!-- Services Grid -->
    <div class="services-grid">
      <!-- API Service -->
      <div 
        class="service-card" 
        :class="services.api.status"
        @click="onServiceClick('api')"
      >
        <div class="service-icon">🔌</div>
        <div class="service-info">
          <span class="service-name">Laravel API</span>
          <span class="service-status">{{ services.api.status }}</span>
        </div>
        <div class="service-metrics">
          <span v-if="services.api.latency" class="latency">{{ services.api.latency }}ms</span>
        </div>
      </div>

      <!-- Worker Service -->
      <div 
        class="service-card" 
        :class="services.worker.status"
        @click="onServiceClick('worker')"
      >
        <div class="service-icon">🤖</div>
        <div class="service-info">
          <span class="service-name">AI Worker</span>
          <span class="service-status">{{ services.worker.status }}</span>
        </div>
        <div class="service-metrics">
          <span v-if="services.worker.latency" class="latency">{{ services.worker.latency }}ms</span>
          <span v-if="services.worker.details?.active_streams" class="streams">
            {{ services.worker.details.active_streams.length }} streams
          </span>
        </div>
      </div>

      <!-- MediaMTX Service -->
      <div 
        class="service-card" 
        :class="services.mediamtx.status"
        @click="onServiceClick('mediamtx')"
      >
        <div class="service-icon">📡</div>
        <div class="service-info">
          <span class="service-name">MediaMTX</span>
          <span class="service-status">{{ services.mediamtx.status }}</span>
        </div>
        <div class="service-metrics">
          <span v-if="services.mediamtx.latency" class="latency">{{ services.mediamtx.latency }}ms</span>
          <span v-if="services.mediamtx.details?.activeStreams >= 0" class="streams">
            {{ services.mediamtx.details.activeStreams }} activos
          </span>
        </div>
      </div>

      <!-- Redis Service -->
      <div 
        class="service-card" 
        :class="services.redis.status"
        @click="onServiceClick('redis')"
      >
        <div class="service-icon">⚡</div>
        <div class="service-info">
          <span class="service-name">Redis</span>
          <span class="service-status">{{ services.redis.status }}</span>
        </div>
        <div class="service-metrics">
          <span v-if="services.redis.details?.inferred" class="inferred">inferido</span>
        </div>
      </div>

      <!-- Database Service -->
      <div 
        class="service-card" 
        :class="services.database.status"
        @click="onServiceClick('database')"
      >
        <div class="service-icon">🗄️</div>
        <div class="service-info">
          <span class="service-name">MySQL</span>
          <span class="service-status">{{ services.database.status }}</span>
        </div>
      </div>
    </div>

    <!-- MediaMTX Streams Detail -->
    <div v-if="services.mediamtx.status === 'online' && services.mediamtx.details?.streams?.length" class="streams-section">
      <h4>📺 Streams Activos en MediaMTX</h4>
      <div class="streams-list">
        <div 
          v-for="stream in services.mediamtx.details.streams" 
          :key="stream.name"
          class="stream-item"
        >
          <span class="stream-name">{{ stream.name }}</span>
          <span class="stream-status" :class="{ ready: stream.ready }">
            {{ stream.ready ? '🟢' : '🔴' }}
          </span>
          <span class="stream-readers">👁️ {{ stream.readers }} viewers</span>
        </div>
      </div>
    </div>

    <!-- Architecture Diagram -->
    <div class="architecture-diagram">
      <h4>🏗️ Arquitectura del Sistema</h4>
      <div class="diagram">
        <div class="diagram-row">
          <div class="diagram-node frontend">
            <span class="node-icon">🖥️</span>
            <span class="node-name">Frontend</span>
          </div>
        </div>
        <div class="diagram-arrow">↓ HTTP/WS</div>
        <div class="diagram-row middle">
          <div class="diagram-node" :class="services.api.status">
            <span class="node-icon">🔌</span>
            <span class="node-name">API</span>
          </div>
          <div class="diagram-node" :class="services.worker.status">
            <span class="node-icon">🤖</span>
            <span class="node-name">Worker</span>
          </div>
          <div class="diagram-node" :class="services.mediamtx.status">
            <span class="node-icon">📡</span>
            <span class="node-name">MediaMTX</span>
          </div>
        </div>
        <div class="diagram-arrow">↓ TCP/Redis</div>
        <div class="diagram-row">
          <div class="diagram-node" :class="services.database.status">
            <span class="node-icon">🗄️</span>
            <span class="node-name">MySQL</span>
          </div>
          <div class="diagram-node" :class="services.redis.status">
            <span class="node-icon">⚡</span>
            <span class="node-name">Redis</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Last Update -->
    <div class="last-update" v-if="lastUpdate">
      Última actualización: {{ lastUpdate.toLocaleTimeString() }}
    </div>
  </div>
</template>

<style scoped>
.system-health {
  background: linear-gradient(135deg, #161b22 0%, #0d1117 100%);
  border: 1px solid #30363d;
  border-radius: 12px;
  padding: 1.5rem;
}

.health-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid #30363d;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.status-icon {
  font-size: 2rem;
}

.header-text h3 {
  margin: 0;
  color: #e6edf3;
  font-size: 1.1rem;
}

.status-label {
  font-size: 0.85rem;
}

.status-label.healthy { color: #3fb950; }
.status-label.degraded { color: #d29922; }
.status-label.offline { color: #f85149; }
.status-label.checking { color: #8b949e; }

.header-right {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.online-count {
  color: #8b949e;
  font-size: 0.85rem;
}

.btn-refresh,
.btn-auto {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255,255,255,0.05);
  border: 1px solid #30363d;
  border-radius: 6px;
  cursor: pointer;
  font-size: 1rem;
  transition: all 0.2s;
}

.btn-refresh:hover,
.btn-auto:hover {
  background: rgba(255,255,255,0.1);
}

.btn-auto.active {
  background: rgba(34, 197, 94, 0.2);
  border-color: #3fb950;
}

/* Services Grid */
.services-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.service-card {
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  cursor: pointer;
  transition: all 0.2s;
}

.service-card:hover {
  transform: translateY(-2px);
  border-color: #58a6ff;
}

.service-card.online {
  border-left: 3px solid #3fb950;
}

.service-card.offline {
  border-left: 3px solid #f85149;
}

.service-card.unknown,
.service-card.checking {
  border-left: 3px solid #8b949e;
}

.service-icon {
  font-size: 1.5rem;
}

.service-name {
  font-weight: 600;
  color: #e6edf3;
}

.service-status {
  font-size: 0.75rem;
  text-transform: uppercase;
}

.service-card.online .service-status { color: #3fb950; }
.service-card.offline .service-status { color: #f85149; }
.service-card.unknown .service-status,
.service-card.checking .service-status { color: #8b949e; }

.service-metrics {
  display: flex;
  gap: 0.5rem;
  font-size: 0.75rem;
  color: #8b949e;
}

.latency {
  background: rgba(88, 166, 255, 0.2);
  color: #58a6ff;
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
}

.streams {
  background: rgba(168, 85, 247, 0.2);
  color: #a855f7;
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
}

.inferred {
  font-style: italic;
  color: #6e7681;
}

/* Streams Section */
.streams-section {
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 1rem;
  margin-bottom: 1.5rem;
}

.streams-section h4 {
  margin: 0 0 0.75rem;
  color: #e6edf3;
  font-size: 0.95rem;
}

.streams-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.stream-item {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.5rem 0.75rem;
  background: rgba(255,255,255,0.02);
  border-radius: 4px;
}

.stream-name {
  flex: 1;
  color: #58a6ff;
  font-family: monospace;
}

.stream-status.ready {
  color: #3fb950;
}

.stream-readers {
  color: #8b949e;
  font-size: 0.8rem;
}

/* Architecture Diagram */
.architecture-diagram {
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 1rem;
  margin-bottom: 1rem;
}

.architecture-diagram h4 {
  margin: 0 0 1rem;
  color: #e6edf3;
  font-size: 0.95rem;
}

.diagram {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
}

.diagram-row {
  display: flex;
  gap: 1rem;
}

.diagram-row.middle {
  gap: 2rem;
}

.diagram-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0.5rem 1rem;
  background: rgba(255,255,255,0.05);
  border: 1px solid #30363d;
  border-radius: 6px;
  min-width: 80px;
}

.diagram-node.online {
  border-color: #3fb950;
  background: rgba(63, 185, 80, 0.1);
}

.diagram-node.offline {
  border-color: #f85149;
  background: rgba(248, 81, 73, 0.1);
}

.diagram-node.frontend {
  border-color: #58a6ff;
  background: rgba(88, 166, 255, 0.1);
}

.node-icon {
  font-size: 1.25rem;
}

.node-name {
  font-size: 0.7rem;
  color: #8b949e;
  margin-top: 0.25rem;
}

.diagram-arrow {
  color: #6e7681;
  font-size: 0.75rem;
}

/* Last Update */
.last-update {
  text-align: center;
  font-size: 0.75rem;
  color: #6e7681;
}

/* Responsive */
@media (max-width: 768px) {
  .services-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  
  .diagram-row.middle {
    flex-wrap: wrap;
    justify-content: center;
  }
}
</style>
