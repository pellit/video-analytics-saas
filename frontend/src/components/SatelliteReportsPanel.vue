<template>
  <div class="satellite-reports-panel">
    <div class="reports-header">
      <h2>📊 Dashboard de Reportes Satelitales</h2>
      <div class="header-actions">
        <button class="btn-refresh" @click="fetchZones" :disabled="loading">
          🔄 Actualizar
        </button>
      </div>
    </div>

    <!-- Zone Selection -->
    <div class="zone-selector" v-if="zones.length > 0">
      <label>Zona a Monitorear:</label>
      <select v-model="selectedZoneId" @change="onZoneSelect">
        <option value="">Seleccionar zona...</option>
        <option v-for="zone in zones" :key="zone.id" :value="zone.id">
          {{ zone.name }} ({{ zone.location_name || 'Sin ubicación' }})
        </option>
      </select>
    </div>

    <!-- Comparison Panel -->
    <div class="comparison-panel" v-if="selectedZone">
      <div class="panel-header">
        <h3>🔍 Comparación de Imágenes - {{ selectedZone.name }}</h3>
        <span class="zone-coords">
          📍 {{ selectedZone.latitude?.toFixed(4) }}, {{ selectedZone.longitude?.toFixed(4) }}
        </span>
      </div>

      <!-- Image Slots -->
      <div class="images-grid">
        <!-- Previous Image -->
        <div class="image-slot">
          <h4>📸 Imagen Anterior (Baseline)</h4>
          <div class="image-container" 
               :class="{ 'has-image': previousImage }"
               @click="triggerUpload('previous')">
            <img v-if="previousImage" :src="previousImage" alt="Imagen anterior" />
            <div v-else class="upload-placeholder">
              <span>📤</span>
              <p>Click para cargar imagen</p>
              <small>o arrastrar archivo</small>
            </div>
          </div>
          <input type="file" ref="previousInput" @change="e => handleImageUpload(e, 'previous')" accept="image/*" hidden />
          <button v-if="previousImage" class="btn-clear" @click="previousImage = null">✕ Limpiar</button>
        </div>

        <!-- Current Image -->
        <div class="image-slot">
          <h4>📸 Imagen Actual</h4>
          <div class="image-container"
               :class="{ 'has-image': currentImage }"
               @click="triggerUpload('current')">
            <img v-if="currentImage" :src="currentImage" alt="Imagen actual" />
            <div v-else class="upload-placeholder">
              <span>📤</span>
              <p>Click para cargar imagen</p>
              <small>o arrastrar archivo</small>
            </div>
          </div>
          <input type="file" ref="currentInput" @change="e => handleImageUpload(e, 'current')" accept="image/*" hidden />
          <button v-if="currentImage" class="btn-clear" @click="currentImage = null">✕ Limpiar</button>
        </div>

        <!-- Result/Diff Image -->
        <div class="image-slot result-slot" v-if="comparisonResult">
          <h4>🔥 Mapa de Cambios</h4>
          <div class="result-tabs">
            <button 
              v-for="tab in resultTabs" 
              :key="tab.key"
              :class="{ active: activeResultTab === tab.key }"
              @click="activeResultTab = tab.key">
              {{ tab.icon }} {{ tab.label }}
            </button>
          </div>
          <div class="image-container has-image">
            <img v-if="activeResultTab === 'overlay' && comparisonResult.overlay_base64" 
                 :src="'data:image/jpeg;base64,' + comparisonResult.overlay_base64" 
                 alt="Overlay de cambios" />
            <img v-else-if="activeResultTab === 'heatmap' && comparisonResult.heatmap_base64"
                 :src="'data:image/jpeg;base64,' + comparisonResult.heatmap_base64"
                 alt="Heatmap" />
            <img v-else-if="activeResultTab === 'diff' && comparisonResult.diff_image_base64"
                 :src="'data:image/jpeg;base64,' + comparisonResult.diff_image_base64"
                 alt="Diferencia" />
          </div>
        </div>
      </div>

      <!-- Compare Button -->
      <div class="compare-actions">
        <button 
          class="btn-compare" 
          @click="runComparison"
          :disabled="!canCompare || comparing">
          <span v-if="comparing">⏳ Analizando...</span>
          <span v-else>🔬 Comparar Imágenes</span>
        </button>
        
        <label class="vlm-toggle">
          <input type="checkbox" v-model="useVLM" />
          🤖 Usar IA para análisis detallado
        </label>
      </div>
    </div>

    <!-- Results Panel -->
    <div class="results-panel" v-if="comparisonResult">
      <div class="results-header">
        <h3>📈 Resultados del Análisis</h3>
        <span class="timestamp">{{ formatDate(comparisonResult.analysis_timestamp) }}</span>
      </div>

      <!-- Main Metrics -->
      <div class="metrics-grid">
        <div class="metric-card" :class="getSeverityClass(comparisonResult.severity)">
          <div class="metric-value">{{ comparisonResult.overall_change_percent }}%</div>
          <div class="metric-label">Cambio Total</div>
          <div class="metric-badge">{{ getSeverityLabel(comparisonResult.severity) }}</div>
        </div>
        
        <div class="metric-card">
          <div class="metric-value">{{ (comparisonResult.ssim_score * 100).toFixed(1) }}%</div>
          <div class="metric-label">Similitud (SSIM)</div>
        </div>
        
        <div class="metric-card">
          <div class="metric-value">{{ comparisonResult.change_regions?.length || 0 }}</div>
          <div class="metric-label">Regiones Afectadas</div>
        </div>
        
        <div class="metric-card type-card">
          <div class="metric-icon">{{ getChangeTypeIcon(comparisonResult.suggested_change_type) }}</div>
          <div class="metric-label">Tipo Detectado</div>
          <div class="metric-type">{{ getChangeTypeLabel(comparisonResult.suggested_change_type) }}</div>
        </div>
      </div>

      <!-- Recommendations -->
      <div class="recommendations-section" v-if="comparisonResult.recommendations?.length">
        <h4>💡 Recomendaciones</h4>
        <ul class="recommendations-list">
          <li v-for="(rec, idx) in comparisonResult.recommendations" :key="idx">
            {{ rec }}
          </li>
        </ul>
      </div>

      <!-- VLM Analysis -->
      <div class="vlm-analysis-section" v-if="vlmAnalysis">
        <h4>🤖 Análisis de IA (Moondream2)</h4>
        <div class="vlm-content">
          <p>{{ vlmAnalysis.detailed_interpretation }}</p>
        </div>
      </div>

      <!-- Notification Preview -->
      <div class="notification-preview" v-if="notificationData">
        <h4>🔔 Notificación</h4>
        <div class="notification-card" :class="'priority-' + notificationData.priority">
          <div class="notif-icon">
            {{ notificationData.priority === 'high' ? '🚨' : notificationData.priority === 'medium' ? '⚠️' : 'ℹ️' }}
          </div>
          <div class="notif-content">
            <strong>{{ notificationData.summary }}</strong>
            <span class="notif-priority">Prioridad: {{ notificationData.priority.toUpperCase() }}</span>
          </div>
          <button v-if="notificationData.should_notify" class="btn-send-notif" @click="sendNotification">
            📤 Enviar
          </button>
        </div>
      </div>

      <!-- Change Regions Table -->
      <div class="regions-section" v-if="comparisonResult.change_regions?.length">
        <h4>📍 Regiones de Cambio Detectadas</h4>
        <table class="regions-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Posición</th>
              <th>Tamaño</th>
              <th>Área</th>
              <th>% del Total</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(region, idx) in comparisonResult.change_regions.slice(0, 10)" :key="idx">
              <td>{{ idx + 1 }}</td>
              <td>{{ region.x }}, {{ region.y }}</td>
              <td>{{ region.width }} × {{ region.height }}</td>
              <td>{{ region.area.toLocaleString() }} px²</td>
              <td>{{ region.change_percent }}%</td>
            </tr>
          </tbody>
        </table>
        <p v-if="comparisonResult.change_regions.length > 10" class="more-regions">
          ... y {{ comparisonResult.change_regions.length - 10 }} regiones más
        </p>
      </div>

      <!-- Actions -->
      <div class="results-actions">
        <button class="btn-save" @click="saveAnalysis">
          💾 Guardar Análisis
        </button>
        <button class="btn-export" @click="exportReport">
          📄 Exportar PDF
        </button>
        <button class="btn-history" @click="showHistory = true">
          📜 Ver Historial
        </button>
      </div>
    </div>

    <!-- Analysis History Modal -->
    <div class="modal-overlay" v-if="showHistory" @click.self="showHistory = false">
      <div class="history-modal">
        <div class="modal-header">
          <h3>📜 Historial de Análisis</h3>
          <button class="btn-close" @click="showHistory = false">✕</button>
        </div>
        <div class="history-list" v-if="analysisHistory.length">
          <div class="history-item" v-for="item in analysisHistory" :key="item.id">
            <div class="history-date">{{ formatDate(item.created_at) }}</div>
            <div class="history-zone">{{ item.zone_name }}</div>
            <div class="history-change" :class="getSeverityClass(item.severity)">
              {{ item.change_percent }}%
            </div>
            <button class="btn-view" @click="viewHistoryItem(item)">👁️</button>
          </div>
        </div>
        <div class="empty-history" v-else>
          <p>No hay análisis guardados</p>
        </div>
      </div>
    </div>

    <!-- Loading Overlay -->
    <div class="loading-overlay" v-if="comparing">
      <div class="loading-content">
        <div class="spinner"></div>
        <p>Analizando imágenes...</p>
        <small v-if="useVLM">Incluyendo análisis de IA (puede tomar unos segundos)</small>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'

const props = defineProps({
  token: String,
  zones: { type: Array, default: () => [] }
})

const emit = defineEmits(['notification', 'save-analysis'])

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'
const AI_URL = import.meta.env.VITE_STREAM_URL?.replace('/video_feed', '') || 'http://localhost:5000'

// State
const loading = ref(false)
const comparing = ref(false)
const selectedZoneId = ref('')
const selectedZone = ref(null)
const previousImage = ref(null)
const currentImage = ref(null)
const previousImageBase64 = ref(null)
const currentImageBase64 = ref(null)
const comparisonResult = ref(null)
const vlmAnalysis = ref(null)
const notificationData = ref(null)
const useVLM = ref(false)
const showHistory = ref(false)
const analysisHistory = ref([])
const activeResultTab = ref('overlay')

// Refs for file inputs
const previousInput = ref(null)
const currentInput = ref(null)

// Computed
const zones = computed(() => props.zones || [])
const canCompare = computed(() => previousImage.value && currentImage.value && selectedZone.value)

const resultTabs = [
  { key: 'overlay', icon: '🎯', label: 'Overlay' },
  { key: 'heatmap', icon: '🔥', label: 'Heatmap' },
  { key: 'diff', icon: '⬜', label: 'Diferencia' }
]

// Methods
const fetchZones = async () => {
  loading.value = true
  try {
    const response = await fetch(`${API_URL}/satellite/zones`, {
      headers: { 'Authorization': `Bearer ${props.token}` }
    })
    if (response.ok) {
      const data = await response.json()
      // Update parent component
    }
  } catch (error) {
    console.error('Error fetching zones:', error)
  } finally {
    loading.value = false
  }
}

const onZoneSelect = () => {
  selectedZone.value = zones.value.find(z => z.id === selectedZoneId.value) || null
  comparisonResult.value = null
  vlmAnalysis.value = null
  notificationData.value = null
}

const triggerUpload = (type) => {
  if (type === 'previous') {
    previousInput.value?.click()
  } else {
    currentInput.value?.click()
  }
}

const handleImageUpload = (event, type) => {
  const file = event.target.files[0]
  if (!file) return
  
  const reader = new FileReader()
  reader.onload = (e) => {
    const dataUrl = e.target.result
    const base64 = dataUrl.split(',')[1]
    
    if (type === 'previous') {
      previousImage.value = dataUrl
      previousImageBase64.value = base64
    } else {
      currentImage.value = dataUrl
      currentImageBase64.value = base64
    }
  }
  reader.readAsDataURL(file)
}

const runComparison = async () => {
  if (!canCompare.value) return
  
  comparing.value = true
  comparisonResult.value = null
  vlmAnalysis.value = null
  notificationData.value = null
  
  try {
    const endpoint = useVLM.value ? '/comparison/analyze-with-suggestions' : '/comparison/compare'
    
    const payload = {
      image_previous_base64: previousImageBase64.value,
      image_current_base64: currentImageBase64.value,
      zone_name: selectedZone.value?.name || 'Unknown',
      use_vlm: useVLM.value,
      generate_visuals: true
    }
    
    const response = await fetch(`${AI_URL}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    
    const data = await response.json()
    
    if (data.success) {
      if (useVLM.value) {
        comparisonResult.value = data.comparison
        vlmAnalysis.value = data.vlm_analysis
        notificationData.value = data.notification
      } else {
        comparisonResult.value = data
      }
      
      emit('notification', {
        type: 'success',
        message: `Análisis completado: ${data.overall_change_percent || data.comparison?.overall_change_percent}% de cambio`
      })
    } else {
      emit('notification', {
        type: 'error',
        message: data.error || 'Error en el análisis'
      })
    }
  } catch (error) {
    console.error('Comparison error:', error)
    emit('notification', {
      type: 'error',
      message: 'Error conectando con el servicio de análisis'
    })
  } finally {
    comparing.value = false
  }
}

const saveAnalysis = async () => {
  if (!comparisonResult.value || !selectedZone.value) return
  
  try {
    const analysisData = {
      zone_id: selectedZone.value.id,
      zone_name: selectedZone.value.name,
      change_percent: comparisonResult.value.overall_change_percent,
      severity: comparisonResult.value.severity,
      change_type: comparisonResult.value.suggested_change_type,
      recommendations: comparisonResult.value.recommendations,
      vlm_analysis: vlmAnalysis.value?.detailed_interpretation || null,
      heatmap_base64: comparisonResult.value.heatmap_base64,
      overlay_base64: comparisonResult.value.overlay_base64
    }
    
    const response = await fetch(`${API_URL}/satellite/analysis`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${props.token}`
      },
      body: JSON.stringify(analysisData)
    })
    
    if (response.ok) {
      emit('notification', { type: 'success', message: 'Análisis guardado correctamente' })
      fetchAnalysisHistory()
    }
  } catch (error) {
    console.error('Save error:', error)
    emit('notification', { type: 'error', message: 'Error guardando análisis' })
  }
}

const exportReport = () => {
  // TODO: Implement PDF export
  emit('notification', { type: 'info', message: 'Función de exportación próximamente' })
}

const fetchAnalysisHistory = async () => {
  if (!selectedZone.value) return
  
  try {
    const response = await fetch(`${API_URL}/satellite/zones/${selectedZone.value.id}/analysis-history`, {
      headers: { 'Authorization': `Bearer ${props.token}` }
    })
    if (response.ok) {
      analysisHistory.value = await response.json()
    }
  } catch (error) {
    console.error('History fetch error:', error)
  }
}

const viewHistoryItem = (item) => {
  // Load historical analysis
  comparisonResult.value = {
    overall_change_percent: item.change_percent,
    severity: item.severity,
    suggested_change_type: item.change_type,
    recommendations: item.recommendations,
    heatmap_base64: item.heatmap_base64,
    overlay_base64: item.overlay_base64
  }
  vlmAnalysis.value = item.vlm_analysis ? { detailed_interpretation: item.vlm_analysis } : null
  showHistory.value = false
}

const sendNotification = async () => {
  if (!notificationData.value) return
  
  try {
    const response = await fetch(`${API_URL}/notifications/send`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${props.token}`
      },
      body: JSON.stringify({
        title: 'Alerta Satelital',
        message: notificationData.value.summary,
        priority: notificationData.value.priority,
        zone_id: selectedZone.value?.id
      })
    })
    
    if (response.ok) {
      emit('notification', { type: 'success', message: 'Notificación enviada' })
    }
  } catch (error) {
    console.error('Notification error:', error)
  }
}

// Helpers
const formatDate = (dateStr) => {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleString('es-ES', {
    dateStyle: 'short',
    timeStyle: 'short'
  })
}

const getSeverityClass = (severity) => {
  const classes = {
    'minimal': 'severity-minimal',
    'low': 'severity-low',
    'moderate': 'severity-moderate',
    'significant': 'severity-significant',
    'critical': 'severity-critical'
  }
  return classes[severity] || ''
}

const getSeverityLabel = (severity) => {
  const labels = {
    'minimal': 'Mínimo',
    'low': 'Bajo',
    'moderate': 'Moderado',
    'significant': 'Significativo',
    'critical': 'Crítico'
  }
  return labels[severity] || severity
}

const getChangeTypeIcon = (type) => {
  const icons = {
    'construction': '🏗️',
    'vegetation': '🌿',
    'water': '💧',
    'deforestation': '🌲',
    'urban_expansion': '🏙️',
    'agricultural': '🚜',
    'unknown': '❓'
  }
  return icons[type] || '❓'
}

const getChangeTypeLabel = (type) => {
  const labels = {
    'construction': 'Construcción',
    'vegetation': 'Vegetación',
    'water': 'Agua/Inundación',
    'deforestation': 'Deforestación',
    'urban_expansion': 'Expansión Urbana',
    'agricultural': 'Agrícola',
    'unknown': 'No Determinado'
  }
  return labels[type] || type
}

// Watch for zone changes
watch(selectedZoneId, () => {
  if (selectedZoneId.value) {
    fetchAnalysisHistory()
  }
})

onMounted(() => {
  // Initial setup if needed
})
</script>

<style scoped>
.satellite-reports-panel {
  background: linear-gradient(135deg, #0d1117 0%, #161b22 100%);
  border-radius: 1rem;
  padding: 1.5rem;
  color: #e6edf3;
}

.reports-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid #30363d;
}

.reports-header h2 {
  margin: 0;
  font-size: 1.5rem;
}

.btn-refresh {
  background: #238636;
  color: white;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-refresh:hover:not(:disabled) {
  background: #2ea043;
}

.btn-refresh:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Zone Selector */
.zone-selector {
  margin-bottom: 1.5rem;
}

.zone-selector label {
  display: block;
  margin-bottom: 0.5rem;
  color: #8b949e;
}

.zone-selector select {
  width: 100%;
  max-width: 400px;
  padding: 0.75rem;
  background: #21262d;
  border: 1px solid #30363d;
  border-radius: 0.5rem;
  color: #e6edf3;
  font-size: 1rem;
}

/* Comparison Panel */
.comparison-panel {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 0.75rem;
  padding: 1.25rem;
  margin-bottom: 1.5rem;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.panel-header h3 {
  margin: 0;
}

.zone-coords {
  color: #8b949e;
  font-size: 0.9rem;
}

/* Images Grid */
.images-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1rem;
  margin-bottom: 1rem;
}

.image-slot h4 {
  margin: 0 0 0.5rem;
  font-size: 0.95rem;
  color: #8b949e;
}

.image-container {
  aspect-ratio: 1;
  background: #0d1117;
  border: 2px dashed #30363d;
  border-radius: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  overflow: hidden;
  transition: all 0.2s;
}

.image-container:hover {
  border-color: #58a6ff;
}

.image-container.has-image {
  border-style: solid;
  cursor: default;
}

.image-container img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.upload-placeholder {
  text-align: center;
  color: #8b949e;
}

.upload-placeholder span {
  font-size: 2.5rem;
  display: block;
  margin-bottom: 0.5rem;
}

.upload-placeholder small {
  opacity: 0.6;
}

.btn-clear {
  margin-top: 0.5rem;
  background: #da3633;
  color: white;
  border: none;
  padding: 0.25rem 0.75rem;
  border-radius: 0.25rem;
  cursor: pointer;
  font-size: 0.8rem;
}

/* Result Tabs */
.result-tabs {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.result-tabs button {
  background: #21262d;
  border: 1px solid #30363d;
  color: #8b949e;
  padding: 0.375rem 0.75rem;
  border-radius: 0.25rem;
  cursor: pointer;
  font-size: 0.8rem;
}

.result-tabs button.active {
  background: #58a6ff;
  color: white;
  border-color: #58a6ff;
}

/* Compare Actions */
.compare-actions {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}

.btn-compare {
  background: linear-gradient(135deg, #238636, #2ea043);
  color: white;
  border: none;
  padding: 0.75rem 1.5rem;
  border-radius: 0.5rem;
  cursor: pointer;
  font-weight: 600;
  font-size: 1rem;
  transition: all 0.2s;
}

.btn-compare:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(35, 134, 54, 0.4);
}

.btn-compare:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none;
}

.vlm-toggle {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: #8b949e;
  cursor: pointer;
}

.vlm-toggle input {
  width: 18px;
  height: 18px;
}

/* Results Panel */
.results-panel {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 0.75rem;
  padding: 1.25rem;
}

.results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid #30363d;
}

.results-header h3 {
  margin: 0;
}

.timestamp {
  color: #8b949e;
  font-size: 0.85rem;
}

/* Metrics Grid */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.metric-card {
  background: #21262d;
  border: 1px solid #30363d;
  border-radius: 0.5rem;
  padding: 1rem;
  text-align: center;
}

.metric-value {
  font-size: 1.75rem;
  font-weight: 700;
  color: #58a6ff;
}

.metric-label {
  color: #8b949e;
  font-size: 0.85rem;
  margin-top: 0.25rem;
}

.metric-badge {
  margin-top: 0.5rem;
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
}

.metric-icon {
  font-size: 2rem;
}

.metric-type {
  color: #e6edf3;
  font-weight: 500;
  margin-top: 0.25rem;
}

/* Severity Colors */
.severity-minimal .metric-value,
.severity-minimal .metric-badge { color: #8b949e; }
.severity-minimal .metric-badge { background: rgba(139, 148, 158, 0.2); }

.severity-low .metric-value,
.severity-low .metric-badge { color: #3fb950; }
.severity-low .metric-badge { background: rgba(63, 185, 80, 0.2); }

.severity-moderate .metric-value,
.severity-moderate .metric-badge { color: #d29922; }
.severity-moderate .metric-badge { background: rgba(210, 153, 34, 0.2); }

.severity-significant .metric-value,
.severity-significant .metric-badge { color: #f85149; }
.severity-significant .metric-badge { background: rgba(248, 81, 73, 0.2); }

.severity-critical .metric-value,
.severity-critical .metric-badge { color: #ff7b72; }
.severity-critical .metric-badge { background: rgba(255, 123, 114, 0.3); }

/* Recommendations */
.recommendations-section {
  background: rgba(88, 166, 255, 0.1);
  border: 1px solid rgba(88, 166, 255, 0.3);
  border-radius: 0.5rem;
  padding: 1rem;
  margin-bottom: 1rem;
}

.recommendations-section h4 {
  margin: 0 0 0.75rem;
  color: #58a6ff;
}

.recommendations-list {
  margin: 0;
  padding-left: 1.25rem;
}

.recommendations-list li {
  margin-bottom: 0.5rem;
  color: #e6edf3;
}

/* VLM Analysis */
.vlm-analysis-section {
  background: linear-gradient(135deg, rgba(139, 92, 246, 0.1), rgba(168, 85, 247, 0.1));
  border: 1px solid rgba(139, 92, 246, 0.3);
  border-radius: 0.5rem;
  padding: 1rem;
  margin-bottom: 1rem;
}

.vlm-analysis-section h4 {
  margin: 0 0 0.75rem;
  color: #a855f7;
}

.vlm-content {
  color: #e6edf3;
  line-height: 1.6;
}

/* Notification Preview */
.notification-preview {
  margin-bottom: 1rem;
}

.notification-preview h4 {
  margin: 0 0 0.5rem;
}

.notification-card {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  border-radius: 0.5rem;
  background: #21262d;
  border: 1px solid #30363d;
}

.notification-card.priority-high {
  border-color: #f85149;
  background: rgba(248, 81, 73, 0.1);
}

.notification-card.priority-medium {
  border-color: #d29922;
  background: rgba(210, 153, 34, 0.1);
}

.notification-card.priority-low {
  border-color: #8b949e;
}

.notif-icon {
  font-size: 1.5rem;
}

.notif-content {
  flex: 1;
}

.notif-content strong {
  display: block;
}

.notif-priority {
  color: #8b949e;
  font-size: 0.8rem;
}

.btn-send-notif {
  background: #238636;
  color: white;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 0.375rem;
  cursor: pointer;
}

/* Regions Table */
.regions-section {
  margin-bottom: 1rem;
}

.regions-section h4 {
  margin: 0 0 0.75rem;
}

.regions-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}

.regions-table th,
.regions-table td {
  padding: 0.5rem;
  text-align: left;
  border-bottom: 1px solid #30363d;
}

.regions-table th {
  color: #8b949e;
  font-weight: 500;
}

.more-regions {
  color: #8b949e;
  font-size: 0.85rem;
  margin-top: 0.5rem;
}

/* Results Actions */
.results-actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  padding-top: 1rem;
  border-top: 1px solid #30363d;
}

.btn-save,
.btn-export,
.btn-history {
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 0.375rem;
  cursor: pointer;
  font-size: 0.9rem;
  transition: all 0.2s;
}

.btn-save {
  background: #238636;
  color: white;
}

.btn-export {
  background: #1f6feb;
  color: white;
}

.btn-history {
  background: #6e7681;
  color: white;
}

/* Modal */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.history-modal {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 0.75rem;
  width: 90%;
  max-width: 600px;
  max-height: 80vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid #30363d;
}

.modal-header h3 {
  margin: 0;
}

.btn-close {
  background: none;
  border: none;
  color: #8b949e;
  font-size: 1.25rem;
  cursor: pointer;
}

.history-list {
  overflow-y: auto;
  padding: 1rem;
}

.history-item {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem;
  background: #21262d;
  border-radius: 0.5rem;
  margin-bottom: 0.5rem;
}

.history-date {
  color: #8b949e;
  font-size: 0.85rem;
  min-width: 100px;
}

.history-zone {
  flex: 1;
}

.history-change {
  font-weight: 600;
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
}

.btn-view {
  background: #21262d;
  border: 1px solid #30363d;
  color: #e6edf3;
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
  cursor: pointer;
}

.empty-history {
  text-align: center;
  padding: 2rem;
  color: #8b949e;
}

/* Loading Overlay */
.loading-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1001;
}

.loading-content {
  text-align: center;
  color: #e6edf3;
}

.spinner {
  width: 50px;
  height: 50px;
  border: 3px solid #30363d;
  border-top-color: #58a6ff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 1rem;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.loading-content small {
  display: block;
  margin-top: 0.5rem;
  color: #8b949e;
}

/* Responsive */
@media (max-width: 768px) {
  .images-grid {
    grid-template-columns: 1fr;
  }
  
  .metrics-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  
  .compare-actions {
    flex-direction: column;
    align-items: stretch;
  }
  
  .results-actions {
    flex-direction: column;
  }
  
  .results-actions button {
    width: 100%;
  }
}
</style>
