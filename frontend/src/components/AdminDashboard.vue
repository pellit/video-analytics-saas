<script setup>
import { ref, onMounted, computed, onUnmounted } from 'vue'
import NavBar from './NavBar.vue'

const props = defineProps(['token', 'user'])
const emit = defineEmits(['logout', 'navigate'])

const stats = ref(null)
const apiStats = ref(null)
const apiKeys = ref([])
const isLoading = ref(true)
const showApiSection = ref(true)
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

// Worker URL for AI Engine endpoints
const getWorkerUrl = () => {
    if (import.meta.env.VITE_STREAM_URL) {
        return import.meta.env.VITE_STREAM_URL.replace('/video_feed', '')
    }
    return 'http://localhost:5000'
}
const WORKER_URL = getWorkerUrl()

// --- Model Management State ---
const showModelsSection = ref(true)
const modelsInfo = ref(null)
const exportStatus = ref(null)
const selectedModelType = ref('yolo_nas_s')
const selectedInputSize = ref(640)
const isExporting = ref(false)
let exportPollInterval = null

// Load models info
const loadModelsInfo = async () => {
    try {
        const res = await fetch(`${WORKER_URL}/models/export/available`)
        if (res.ok) {
            modelsInfo.value = await res.json()
        }
    } catch (e) {
        console.error('Error loading models info:', e)
    }
}

// Check export status
const checkExportStatus = async () => {
    try {
        const res = await fetch(`${WORKER_URL}/models/export/status`)
        if (res.ok) {
            exportStatus.value = await res.json()
            
            // Stop polling if export completed or errored
            if (exportStatus.value.status === 'completed' || exportStatus.value.status === 'error') {
                stopExportPolling()
                await loadModelsInfo() // Refresh models list
            }
        }
    } catch (e) {
        console.error('Error checking export status:', e)
    }
}

// Start export
const startExport = async (force = false) => {
    isExporting.value = true
    try {
        const endpoint = force ? '/models/export/force' : '/models/export/start'
        const res = await fetch(`${WORKER_URL}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model_type: selectedModelType.value,
                input_size: selectedInputSize.value
            })
        })
        
        const data = await res.json()
        
        if (data.success) {
            // Start polling for status
            startExportPolling()
        } else if (data.warning) {
            // Model already exists, ask for confirmation
            if (confirm(`${data.warning}\n\n¿Desea sobreescribir el modelo existente?`)) {
                await startExport(true)
            }
        } else {
            alert(`Error: ${data.error}`)
        }
    } catch (e) {
        console.error('Error starting export:', e)
        alert(`Error iniciando exportación: ${e.message}`)
    } finally {
        isExporting.value = false
    }
}

// Reload model after export
const reloadModel = async () => {
    try {
        const res = await fetch(`${WORKER_URL}/models/reload`, { method: 'POST' })
        const data = await res.json()
        
        if (data.success) {
            alert(`✅ Modelo recargado: ${data.model}`)
            await loadModelsInfo()
        } else {
            alert(`Error: ${data.error}`)
        }
    } catch (e) {
        alert(`Error recargando modelo: ${e.message}`)
    }
}

const startExportPolling = () => {
    stopExportPolling()
    exportPollInterval = setInterval(checkExportStatus, 2000)
    checkExportStatus() // Immediate first check
}

const stopExportPolling = () => {
    if (exportPollInterval) {
        clearInterval(exportPollInterval)
        exportPollInterval = null
    }
}

onMounted(async () => {
  try {
    // Cargar stats generales y API stats en paralelo
    const [statsRes, apiRes, keysRes] = await Promise.all([
      fetch(`${API_URL}/admin/stats`, {
        headers: { 'Authorization': `Bearer ${props.token}`, 'Accept': 'application/json' }
      }),
      fetch(`${API_URL}/admin/api/overview`, {
        headers: { 'Authorization': `Bearer ${props.token}`, 'Accept': 'application/json' }
      }),
      fetch(`${API_URL}/admin/api/keys`, {
        headers: { 'Authorization': `Bearer ${props.token}`, 'Accept': 'application/json' }
      })
    ])
    
    if (statsRes.ok) stats.value = await statsRes.json()
    if (apiRes.ok) apiStats.value = await apiRes.json()
    if (keysRes.ok) {
      const keysData = await keysRes.json()
      apiKeys.value = keysData.keys || []
    }
    
    // Load models info
    await loadModelsInfo()
  } catch (e) {
    console.error('Error loading stats:', e)
  } finally {
    isLoading.value = false
  }
})

onUnmounted(() => {
    stopExportPolling()
})

const toggleApiKey = async (keyId) => {
  try {
    const res = await fetch(`${API_URL}/admin/api/keys/${keyId}/toggle`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${props.token}`, 'Accept': 'application/json' }
    })
    if (res.ok) {
      const updated = await res.json()
      const idx = apiKeys.value.findIndex(k => k.id === keyId)
      if (idx !== -1) apiKeys.value[idx] = updated.key
    }
  } catch (e) {
    console.error('Error toggling API key:', e)
  }
}

const formatNumber = (num) => {
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M'
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K'
  return num?.toString() || '0'
}

const formatBytes = (mb) => {
  if (mb >= 1024) return (mb / 1024).toFixed(1) + ' GB'
  return mb?.toFixed(1) + ' MB'
}

const navNotifications = computed(() => [])
</script>

<template>
  <div class="admin-layout">
    <!-- NavBar Component -->
    <NavBar 
      :user="user" 
      :notifications="navNotifications"
      :cameras-online="stats?.metrics?.cameras || 0"
      current-view="admin"
      @logout="emit('logout')"
      @navigate="(view) => emit('navigate', view)"
    />

    <main class="admin-content">
      <!-- Loading State -->
      <div v-if="isLoading" class="loading-state">
        <div class="spinner"></div>
        <p>Cargando estadísticas...</p>
      </div>

      <!-- Admin Panel -->
      <div v-else-if="stats" class="admin-panel">
        <header class="panel-header">
          <div class="header-info">
            <h1>🛡️ Panel de Administración</h1>
            <p class="subtitle">Gestión global del sistema</p>
          </div>
        </header>

        <!-- Stats Grid -->
        <div class="stats-grid">
          <div class="stat-card users">
            <div class="stat-icon">👥</div>
            <div class="stat-info">
              <span class="stat-value">{{ stats.metrics.users }}</span>
              <span class="stat-label">Usuarios Registrados</span>
            </div>
          </div>
          <div class="stat-card cameras">
            <div class="stat-icon">📹</div>
            <div class="stat-info">
              <span class="stat-value">{{ stats.metrics.cameras }}</span>
              <span class="stat-label">Cámaras Totales</span>
            </div>
          </div>
          <div class="stat-card alerts">
            <div class="stat-icon">🔔</div>
            <div class="stat-info">
              <span class="stat-value">{{ stats.metrics.alerts || 0 }}</span>
              <span class="stat-label">Alertas Activas</span>
            </div>
          </div>
          <div class="stat-card detections">
            <div class="stat-icon">🎯</div>
            <div class="stat-info">
              <span class="stat-value">{{ stats.metrics.detections || 0 }}</span>
              <span class="stat-label">Detecciones Hoy</span>
            </div>
          </div>
        </div>

        <!-- Recent Users Section -->
        <section class="section">
          <h2>👤 Usuarios Recientes</h2>
          <div class="users-list">
            <div v-for="u in stats.recent_users" :key="u.id" class="user-item">
              <div class="user-avatar">{{ u.name?.charAt(0)?.toUpperCase() || '?' }}</div>
              <div class="user-info">
                <span class="user-name">{{ u.name }}</span>
                <span class="user-email">{{ u.email }}</span>
              </div>
              <span class="user-role" :class="u.role">{{ u.role || 'user' }}</span>
            </div>
            <div v-if="!stats.recent_users?.length" class="empty-state">
              <p>No hay usuarios recientes</p>
            </div>
          </div>
        </section>

        <!-- External API Usage Section -->
        <section class="section api-section">
          <div class="section-header">
            <h2>🔌 API Externa - Uso de Terceros</h2>
            <button class="btn-toggle" @click="showApiSection = !showApiSection">
              {{ showApiSection ? '▼' : '▶' }}
            </button>
          </div>
          
          <div v-if="showApiSection" class="api-content">
            <!-- API Stats Overview -->
            <div class="api-stats-grid" v-if="apiStats">
              <div class="api-stat-card">
                <div class="api-stat-icon">🔑</div>
                <div class="api-stat-info">
                  <span class="api-stat-value">{{ apiStats.total_keys || 0 }}</span>
                  <span class="api-stat-label">API Keys Activas</span>
                </div>
              </div>
              <div class="api-stat-card">
                <div class="api-stat-icon">📊</div>
                <div class="api-stat-info">
                  <span class="api-stat-value">{{ formatNumber(apiStats.total_requests || 0) }}</span>
                  <span class="api-stat-label">Total Requests</span>
                </div>
              </div>
              <div class="api-stat-card">
                <div class="api-stat-icon">📈</div>
                <div class="api-stat-info">
                  <span class="api-stat-value">{{ formatNumber(apiStats.today_requests || 0) }}</span>
                  <span class="api-stat-label">Hoy</span>
                </div>
              </div>
              <div class="api-stat-card">
                <div class="api-stat-icon">🖼️</div>
                <div class="api-stat-info">
                  <span class="api-stat-value">{{ formatNumber(apiStats.today_frames || 0) }}</span>
                  <span class="api-stat-label">Frames Hoy</span>
                </div>
              </div>
            </div>

            <!-- API Keys List -->
            <div class="api-keys-section" v-if="apiKeys.length">
              <h3>🔐 API Keys Registradas</h3>
              <div class="api-keys-list">
                <div v-for="key in apiKeys" :key="key.id" class="api-key-item" :class="{ inactive: !key.is_active }">
                  <div class="key-info">
                    <div class="key-header">
                      <span class="key-name">{{ key.name }}</span>
                      <span class="key-status" :class="key.is_active ? 'active' : 'inactive'">
                        {{ key.is_active ? 'Activa' : 'Inactiva' }}
                      </span>
                    </div>
                    <span class="key-user">👤 {{ key.user?.name || key.user?.email || 'Usuario desconocido' }}</span>
                    <div class="key-meta">
                      <span>📊 {{ formatNumber(key.request_count || 0) }} requests</span>
                      <span>⏱️ Límite: {{ formatNumber(key.rate_limit) }}/día</span>
                    </div>
                  </div>
                  <button 
                    class="btn-toggle-key" 
                    :class="key.is_active ? 'deactivate' : 'activate'"
                    @click="toggleApiKey(key.id)"
                  >
                    {{ key.is_active ? 'Desactivar' : 'Activar' }}
                  </button>
                </div>
              </div>
            </div>

            <!-- Empty State -->
            <div v-else class="empty-api-state">
              <span class="empty-icon">🔌</span>
              <p>No hay API keys registradas</p>
              <p class="empty-hint">Las apps de terceros pueden solicitar acceso a la API para enviar videos a analizar</p>
            </div>
          </div>
        </section>

        <!-- Model Management Section -->
        <section class="section models-section">
          <div class="section-header">
            <h2>🤖 Gestión de Modelos IA</h2>
            <button class="btn-toggle" @click="showModelsSection = !showModelsSection">
              {{ showModelsSection ? '▼' : '▶' }}
            </button>
          </div>

          <div v-if="showModelsSection" class="models-content">
            <!-- Current Model Status -->
            <div class="model-status-card">
              <div class="status-header">
                <span class="status-icon">📦</span>
                <span class="status-title">Modelos ONNX Instalados</span>
              </div>
              
              <div v-if="modelsInfo?.installed && Object.keys(modelsInfo.installed).length > 0" class="installed-models">
                <div v-for="(info, name) in modelsInfo.installed" :key="name" class="model-item installed">
                  <div class="model-icon">✅</div>
                  <div class="model-details">
                    <span class="model-name">{{ name }}.onnx</span>
                    <span class="model-size">{{ formatBytes(info.size_mb) }}</span>
                    <span v-if="info.validated" class="model-validated">Validado ✓</span>
                  </div>
                  <button class="btn-reload" @click="reloadModel" title="Cargar este modelo">
                    🔄 Cargar
                  </button>
                </div>
              </div>
              
              <div v-else class="no-models">
                <span class="warning-icon">⚠️</span>
                <p>No hay modelos ONNX instalados</p>
                <p class="hint">Exporte un modelo YOLO-NAS para máxima velocidad en CPU</p>
              </div>
            </div>

            <!-- Export New Model -->
            <div class="export-section">
              <h3>🚀 Exportar Modelo YOLO-NAS a ONNX</h3>
              <p class="export-description">
                ONNX es 2-3x más rápido que PyTorch en CPU. Recomendado para producción.
              </p>

              <div class="export-form">
                <div class="form-group">
                  <label>Modelo:</label>
                  <select v-model="selectedModelType" :disabled="isExporting">
                    <option value="yolo_nas_s">YOLO-NAS Small (~12M params) - Recomendado CPU</option>
                    <option value="yolo_nas_m">YOLO-NAS Medium (~32M params) - Balanceado</option>
                    <option value="yolo_nas_l">YOLO-NAS Large (~44M params) - Más preciso</option>
                  </select>
                </div>

                <div class="form-group">
                  <label>Tamaño de entrada:</label>
                  <select v-model="selectedInputSize" :disabled="isExporting">
                    <option :value="320">320x320 - Más rápido</option>
                    <option :value="416">416x416 - Balanceado</option>
                    <option :value="512">512x512 - Mejor detalle</option>
                    <option :value="640">640x640 - Máxima precisión</option>
                  </select>
                </div>

                <button 
                  class="btn-export" 
                  @click="startExport(false)"
                  :disabled="isExporting || (exportStatus?.status === 'exporting')"
                >
                  {{ isExporting ? '⏳ Iniciando...' : '🚀 Exportar Modelo' }}
                </button>
              </div>

              <!-- Export Progress -->
              <div v-if="exportStatus && ['starting', 'importing', 'downloading', 'preparing', 'exporting', 'verifying'].includes(exportStatus.status)" class="export-progress">
                <div class="progress-header">
                  <span class="progress-icon">⏳</span>
                  <span class="progress-status">{{ exportStatus.status }}</span>
                </div>
                <div class="progress-bar-container">
                  <div class="progress-bar" :style="{ width: exportStatus.progress + '%' }"></div>
                </div>
                <span class="progress-percent">{{ exportStatus.progress }}%</span>
              </div>

              <!-- Export Complete -->
              <div v-if="exportStatus?.status === 'completed'" class="export-complete">
                <span class="complete-icon">✅</span>
                <span class="complete-text">Exportación completada</span>
                <div v-if="exportStatus.model_info" class="model-result">
                  <span>Archivo: {{ exportStatus.model_info.size_mb }} MB</span>
                  <span v-if="exportStatus.model_info.validated">Validación: OK</span>
                </div>
                <button class="btn-reload-after" @click="reloadModel">
                  🔄 Cargar modelo ahora
                </button>
              </div>

              <!-- Export Error -->
              <div v-if="exportStatus?.status === 'error'" class="export-error">
                <span class="error-icon">❌</span>
                <span class="error-text">{{ exportStatus.error }}</span>
                <button class="btn-retry-export" @click="startExport(true)">
                  🔄 Reintentar
                </button>
              </div>
            </div>

            <!-- Available Models Info -->
            <div v-if="modelsInfo?.available" class="available-models">
              <h4>📋 Modelos Disponibles</h4>
              <div class="models-grid">
                <div v-for="(info, name) in modelsInfo.available" :key="name" class="model-info-card">
                  <span class="model-name">{{ info.name }}</span>
                  <span class="model-desc">{{ info.description }}</span>
                  <span class="model-rec">📌 {{ info.recommended_for }}</span>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>

      <!-- Error State -->
      <div v-else class="error-state">
        <span class="error-icon">⚠️</span>
        <p>No se pudieron cargar las estadísticas</p>
        <button @click="$router.go(0)" class="btn-retry">Reintentar</button>
      </div>
    </main>
  </div>
</template>

<style scoped>
.admin-layout {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: #0d1117;
}

.admin-content {
  flex: 1;
  padding: 2rem;
  margin-top: 4rem;
  overflow-y: auto;
}

/* Loading State */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 50vh;
  color: #8b949e;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid #30363d;
  border-top-color: #a855f7;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 1rem;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Panel Header */
.panel-header {
  margin-bottom: 2rem;
}

.panel-header h1 {
  font-size: 1.75rem;
  font-weight: 700;
  color: #e6edf3;
  margin: 0;
}

.panel-header .subtitle {
  color: #8b949e;
  margin: 0.25rem 0 0;
  font-size: 0.95rem;
}

/* Stats Grid */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 1.25rem;
  margin-bottom: 2rem;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1.25rem;
  background: #161b22;
  border-radius: 0.75rem;
  border: 1px solid #30363d;
  transition: all 0.2s ease;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
}

.stat-icon {
  font-size: 2rem;
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 0.75rem;
}

.stat-card.users .stat-icon {
  background: linear-gradient(135deg, rgba(168, 85, 247, 0.2), rgba(139, 92, 246, 0.1));
}

.stat-card.cameras .stat-icon {
  background: linear-gradient(135deg, rgba(31, 111, 235, 0.2), rgba(59, 130, 246, 0.1));
}

.stat-card.alerts .stat-icon {
  background: linear-gradient(135deg, rgba(248, 81, 73, 0.2), rgba(239, 68, 68, 0.1));
}

.stat-card.detections .stat-icon {
  background: linear-gradient(135deg, rgba(35, 134, 54, 0.2), rgba(34, 197, 94, 0.1));
}

.stat-info {
  display: flex;
  flex-direction: column;
}

.stat-value {
  font-size: 1.75rem;
  font-weight: 700;
  color: #e6edf3;
  line-height: 1;
}

.stat-label {
  font-size: 0.85rem;
  color: #8b949e;
  margin-top: 0.25rem;
}

/* Section */
.section {
  background: #161b22;
  border-radius: 0.75rem;
  border: 1px solid #30363d;
  padding: 1.25rem;
  margin-bottom: 1.5rem;
}

.section h2 {
  font-size: 1.1rem;
  font-weight: 600;
  color: #e6edf3;
  margin: 0 0 1rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid #30363d;
}

/* Users List */
.users-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.user-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem;
  background: #21262d;
  border-radius: 0.5rem;
  transition: background 0.15s ease;
}

.user-item:hover {
  background: #30363d;
}

.user-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, #1f6feb, #a855f7);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  color: white;
  font-size: 1rem;
}

.user-info {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.user-name {
  font-weight: 500;
  color: #e6edf3;
}

.user-email {
  font-size: 0.85rem;
  color: #8b949e;
}

.user-role {
  padding: 0.25rem 0.75rem;
  border-radius: 2rem;
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: capitalize;
  background: #21262d;
  color: #8b949e;
  border: 1px solid #30363d;
}

.user-role.superadmin {
  background: linear-gradient(135deg, rgba(168, 85, 247, 0.2), rgba(139, 92, 246, 0.1));
  color: #a78bfa;
  border-color: rgba(168, 85, 247, 0.3);
}

.user-role.admin {
  background: linear-gradient(135deg, rgba(31, 111, 235, 0.2), rgba(59, 130, 246, 0.1));
  color: #60a5fa;
  border-color: rgba(31, 111, 235, 0.3);
}

/* Empty State */
.empty-state {
  text-align: center;
  padding: 2rem;
  color: #8b949e;
}

/* Error State */
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 50vh;
  color: #8b949e;
}

.error-icon {
  font-size: 3rem;
  margin-bottom: 1rem;
}

.btn-retry {
  margin-top: 1rem;
  padding: 0.5rem 1.5rem;
  background: linear-gradient(135deg, #1f6feb, #a855f7);
  color: white;
  border: none;
  border-radius: 0.5rem;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s ease;
}

.btn-retry:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(31, 111, 235, 0.3);
}

/* Responsive */
@media (max-width: 768px) {
  .admin-content {
    padding: 1rem;
  }
  
  .panel-header h1 {
    font-size: 1.4rem;
  }
  
  .stats-grid {
    grid-template-columns: 1fr;
  }
  
  .stat-card {
    padding: 1rem;
  }
  
  .stat-icon {
    width: 48px;
    height: 48px;
    font-size: 1.5rem;
  }
  
  .stat-value {
    font-size: 1.5rem;
  }
  
  .user-item {
    flex-wrap: wrap;
  }
  
  .user-role {
    margin-left: auto;
  }
}

@media (max-width: 480px) {
  .admin-content {
    margin-top: 3.5rem;
    padding: 0.75rem;
  }
  
  .panel-header h1 {
    font-size: 1.2rem;
  }
  
  .section {
    padding: 1rem;
  }
  
  .section h2 {
    font-size: 1rem;
  }
}

/* API Section Styles */
.api-section {
  margin-top: 1.5rem;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid #30363d;
  margin-bottom: 1rem;
}

.section-header h2 {
  margin: 0;
  padding: 0;
  border: none;
}

.btn-toggle {
  background: transparent;
  border: none;
  color: #8b949e;
  cursor: pointer;
  padding: 0.25rem 0.5rem;
  font-size: 0.85rem;
  transition: color 0.15s;
}

.btn-toggle:hover {
  color: #e6edf3;
}

.api-stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.api-stat-card {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
  background: #21262d;
  border-radius: 0.5rem;
  border: 1px solid #30363d;
}

.api-stat-icon {
  font-size: 1.5rem;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, rgba(14, 165, 233, 0.2), rgba(6, 182, 212, 0.1));
  border-radius: 0.5rem;
}

.api-stat-info {
  display: flex;
  flex-direction: column;
}

.api-stat-value {
  font-size: 1.25rem;
  font-weight: 700;
  color: #e6edf3;
  line-height: 1;
}

.api-stat-label {
  font-size: 0.75rem;
  color: #8b949e;
  margin-top: 0.25rem;
}

.api-keys-section h3 {
  font-size: 1rem;
  font-weight: 600;
  color: #e6edf3;
  margin: 0 0 0.75rem;
}

.api-keys-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.api-key-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem;
  background: #21262d;
  border-radius: 0.5rem;
  border: 1px solid #30363d;
  transition: all 0.15s ease;
}

.api-key-item:hover {
  background: #30363d;
}

.api-key-item.inactive {
  opacity: 0.6;
}

.key-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.key-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.key-name {
  font-weight: 600;
  color: #e6edf3;
}

.key-status {
  padding: 0.15rem 0.5rem;
  border-radius: 2rem;
  font-size: 0.7rem;
  font-weight: 500;
}

.key-status.active {
  background: rgba(34, 197, 94, 0.2);
  color: #4ade80;
  border: 1px solid rgba(34, 197, 94, 0.3);
}

.key-status.inactive {
  background: rgba(239, 68, 68, 0.2);
  color: #f87171;
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.key-user {
  font-size: 0.85rem;
  color: #8b949e;
}

.key-meta {
  display: flex;
  gap: 1rem;
  font-size: 0.75rem;
  color: #6e7681;
}

.btn-toggle-key {
  padding: 0.4rem 0.75rem;
  border-radius: 0.375rem;
  font-size: 0.75rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  border: none;
}

.btn-toggle-key.activate {
  background: rgba(34, 197, 94, 0.2);
  color: #4ade80;
}

.btn-toggle-key.activate:hover {
  background: rgba(34, 197, 94, 0.3);
}

.btn-toggle-key.deactivate {
  background: rgba(239, 68, 68, 0.2);
  color: #f87171;
}

.btn-toggle-key.deactivate:hover {
  background: rgba(239, 68, 68, 0.3);
}

.empty-api-state {
  text-align: center;
  padding: 2rem;
  color: #8b949e;
}

.empty-icon {
  font-size: 2.5rem;
  display: block;
  margin-bottom: 0.75rem;
}

.empty-hint {
  font-size: 0.85rem;
  color: #6e7681;
  margin-top: 0.5rem;
}

/* Responsive for API Section */
@media (max-width: 768px) {
  .api-stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  
  .api-key-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.75rem;
  }
  
  .btn-toggle-key {
    width: 100%;
  }
  
  .key-meta {
    flex-wrap: wrap;
    gap: 0.5rem;
  }
}

@media (max-width: 480px) {
  .api-stats-grid {
    grid-template-columns: 1fr;
  }
  
  .api-stat-card {
    padding: 0.75rem;
  }
}

/* --- Models Section Styles --- */
.models-section {
  margin-top: 2rem;
}

.models-content {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.model-status-card {
  background: linear-gradient(135deg, #161b22 0%, #21262d 100%);
  border: 1px solid #30363d;
  border-radius: 0.75rem;
  padding: 1.25rem;
}

.status-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.status-icon {
  font-size: 1.25rem;
}

.status-title {
  font-weight: 600;
  color: #e6edf3;
}

.installed-models {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.model-item {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem 1rem;
  background: rgba(35, 134, 54, 0.1);
  border: 1px solid #238636;
  border-radius: 0.5rem;
}

.model-icon {
  font-size: 1.25rem;
}

.model-details {
  flex-grow: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1rem;
  align-items: center;
}

.model-name {
  font-weight: 600;
  color: #58a6ff;
}

.model-size {
  color: #8b949e;
  font-size: 0.875rem;
}

.model-validated {
  color: #3fb950;
  font-size: 0.8rem;
  background: rgba(63, 185, 80, 0.1);
  padding: 0.125rem 0.5rem;
  border-radius: 0.25rem;
}

.btn-reload {
  background: #238636;
  color: white;
  border: none;
  padding: 0.5rem 0.75rem;
  border-radius: 0.375rem;
  cursor: pointer;
  font-size: 0.8rem;
  transition: all 0.2s;
}

.btn-reload:hover {
  background: #2ea043;
}

.no-models {
  text-align: center;
  padding: 1.5rem;
  color: #8b949e;
}

.warning-icon {
  font-size: 2rem;
  display: block;
  margin-bottom: 0.5rem;
}

.no-models .hint {
  font-size: 0.85rem;
  opacity: 0.7;
  margin-top: 0.25rem;
}

.export-section {
  background: linear-gradient(135deg, #161b22 0%, #1c2128 100%);
  border: 1px solid #30363d;
  border-radius: 0.75rem;
  padding: 1.25rem;
}

.export-section h3 {
  color: #e6edf3;
  margin-bottom: 0.5rem;
}

.export-description {
  color: #8b949e;
  font-size: 0.9rem;
  margin-bottom: 1rem;
}

.export-form {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  align-items: flex-end;
}

.form-group {
  flex: 1;
  min-width: 200px;
}

.form-group label {
  display: block;
  color: #8b949e;
  font-size: 0.85rem;
  margin-bottom: 0.375rem;
}

.form-group select {
  width: 100%;
  background: #0d1117;
  color: #e6edf3;
  border: 1px solid #30363d;
  border-radius: 0.375rem;
  padding: 0.625rem 0.75rem;
  font-size: 0.9rem;
}

.form-group select:focus {
  border-color: #58a6ff;
  outline: none;
}

.btn-export {
  background: linear-gradient(135deg, #238636, #2ea043);
  color: white;
  border: none;
  padding: 0.75rem 1.5rem;
  border-radius: 0.5rem;
  cursor: pointer;
  font-weight: 500;
  font-size: 0.95rem;
  transition: all 0.2s;
  white-space: nowrap;
}

.btn-export:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(35, 134, 54, 0.3);
}

.btn-export:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.export-progress {
  margin-top: 1rem;
  padding: 1rem;
  background: rgba(88, 166, 255, 0.1);
  border: 1px solid #58a6ff;
  border-radius: 0.5rem;
}

.progress-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.progress-icon {
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.progress-status {
  color: #58a6ff;
  font-weight: 500;
  text-transform: capitalize;
}

.progress-bar-container {
  background: #21262d;
  border-radius: 0.25rem;
  height: 8px;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: linear-gradient(90deg, #58a6ff, #79c0ff);
  border-radius: 0.25rem;
  transition: width 0.3s ease;
}

.progress-percent {
  display: block;
  text-align: right;
  color: #8b949e;
  font-size: 0.8rem;
  margin-top: 0.25rem;
}

.export-complete {
  margin-top: 1rem;
  padding: 1rem;
  background: rgba(63, 185, 80, 0.1);
  border: 1px solid #3fb950;
  border-radius: 0.5rem;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}

.complete-icon {
  font-size: 1.5rem;
}

.complete-text {
  color: #3fb950;
  font-weight: 600;
}

.model-result {
  flex-basis: 100%;
  display: flex;
  gap: 1rem;
  color: #8b949e;
  font-size: 0.85rem;
}

.btn-reload-after {
  margin-left: auto;
  background: #238636;
  color: white;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 0.375rem;
  cursor: pointer;
  font-size: 0.9rem;
  transition: all 0.2s;
}

.btn-reload-after:hover {
  background: #2ea043;
}

.export-error {
  margin-top: 1rem;
  padding: 1rem;
  background: rgba(248, 81, 73, 0.1);
  border: 1px solid #f85149;
  border-radius: 0.5rem;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}

.export-error .error-icon {
  font-size: 1.5rem;
}

.export-error .error-text {
  flex: 1;
  color: #f85149;
}

.btn-retry-export {
  background: #da3633;
  color: white;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 0.375rem;
  cursor: pointer;
  font-size: 0.9rem;
  transition: all 0.2s;
}

.btn-retry-export:hover {
  background: #f85149;
}

.available-models {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 0.75rem;
  padding: 1rem;
}

.available-models h4 {
  color: #e6edf3;
  margin-bottom: 0.75rem;
}

.models-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 1rem;
}

.model-info-card {
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 0.5rem;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.model-info-card .model-name {
  font-weight: 600;
  color: #58a6ff;
}

.model-info-card .model-desc {
  color: #8b949e;
  font-size: 0.85rem;
}

.model-info-card .model-rec {
  color: #7ee787;
  font-size: 0.8rem;
  margin-top: 0.25rem;
}
</style>