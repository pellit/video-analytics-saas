<script setup>
import { ref, computed, onMounted, watch } from 'vue'

const props = defineProps({
  token: String,
  cameraId: Number,
  enabled: Boolean
})

const emit = defineEmits(['close'])

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

// State
const loading = ref(false)
const activeTab = ref('detections') // 'detections' | 'known'
const knownFaces = ref([])
const recentDetections = ref([])
const showOnlyUnidentified = ref(true)

// Modal state for labeling
const showLabelModal = ref(false)
const selectedDetection = ref(null)
const newFaceName = ref('')
const newFaceLabel = ref('')
const assignToExisting = ref(false)
const selectedKnownFaceId = ref(null)

// Fetch known faces
const fetchKnownFaces = async () => {
  try {
    const res = await fetch(`${API_URL}/faces`, {
      headers: { 'Authorization': `Bearer ${props.token}`, 'Accept': 'application/json' }
    })
    if (res.ok) {
      knownFaces.value = await res.json()
    }
  } catch (e) {
    console.error('Error fetching known faces:', e)
  }
}

// Fetch recent detections
const fetchDetections = async () => {
  loading.value = true
  try {
    let url = `${API_URL}/face-detections?limit=30`
    if (props.cameraId) {
      url += `&camera_id=${props.cameraId}`
    }
    if (showOnlyUnidentified.value) {
      url += `&identified=false`
    }
    
    const res = await fetch(url, {
      headers: { 'Authorization': `Bearer ${props.token}`, 'Accept': 'application/json' }
    })
    if (res.ok) {
      recentDetections.value = await res.json()
    }
  } catch (e) {
    console.error('Error fetching detections:', e)
  } finally {
    loading.value = false
  }
}

// Open label modal for a detection
const openLabelModal = (detection) => {
  selectedDetection.value = detection
  newFaceName.value = ''
  newFaceLabel.value = ''
  assignToExisting.value = false
  selectedKnownFaceId.value = null
  showLabelModal.value = true
}

// Create new face from detection
const createNewFace = async () => {
  if (!newFaceName.value.trim()) {
    alert('Por favor ingresa un nombre')
    return
  }

  try {
    const res = await fetch(`${API_URL}/face-detections/${selectedDetection.value.id}/create-face`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${props.token}`,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify({
        name: newFaceName.value.trim(),
        label: newFaceLabel.value.trim() || null
      })
    })

    if (res.ok) {
      alert('Cara registrada correctamente')
      showLabelModal.value = false
      fetchKnownFaces()
      fetchDetections()
    } else {
      const data = await res.json()
      alert(data.message || 'Error al registrar cara')
    }
  } catch (e) {
    console.error('Error creating face:', e)
    alert('Error de red')
  }
}

// Assign detection to existing face
const assignToFace = async () => {
  if (!selectedKnownFaceId.value) {
    alert('Por favor selecciona una cara conocida')
    return
  }

  try {
    const res = await fetch(`${API_URL}/face-detections/${selectedDetection.value.id}/assign`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${props.token}`,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify({
        known_face_id: selectedKnownFaceId.value
      })
    })

    if (res.ok) {
      alert('Detección asignada correctamente')
      showLabelModal.value = false
      fetchDetections()
    } else {
      const data = await res.json()
      alert(data.message || 'Error al asignar')
    }
  } catch (e) {
    console.error('Error assigning face:', e)
    alert('Error de red')
  }
}

// Delete known face
const deleteKnownFace = async (face) => {
  if (!confirm(`¿Eliminar "${face.name}"? Las detecciones asociadas quedarán sin identificar.`)) {
    return
  }

  try {
    const res = await fetch(`${API_URL}/faces/${face.id}`, {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${props.token}`,
        'Accept': 'application/json'
      }
    })

    if (res.ok) {
      fetchKnownFaces()
      fetchDetections()
    } else {
      const data = await res.json()
      alert(data.message || 'Error al eliminar')
    }
  } catch (e) {
    console.error('Error deleting face:', e)
    alert('Error de red')
  }
}

// Edit known face name
const editFaceName = async (face) => {
  const newName = prompt('Nuevo nombre:', face.name)
  if (!newName || newName === face.name) return

  try {
    const res = await fetch(`${API_URL}/faces/${face.id}`, {
      method: 'PATCH',
      headers: {
        'Authorization': `Bearer ${props.token}`,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify({ name: newName })
    })

    if (res.ok) {
      fetchKnownFaces()
    } else {
      alert('Error al actualizar')
    }
  } catch (e) {
    alert('Error de red')
  }
}

// Format date
const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString()
}

// Initialize
onMounted(() => {
  fetchKnownFaces()
  fetchDetections()
})

// Watch for filter changes
watch(showOnlyUnidentified, () => {
  fetchDetections()
})

// Refresh periodically if enabled
let refreshInterval = null
watch(() => props.enabled, (enabled) => {
  if (enabled) {
    refreshInterval = setInterval(() => {
      fetchDetections()
    }, 5000)
  } else if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
}, { immediate: true })
</script>

<template>
  <div class="face-panel">
    <div class="panel-header">
      <h3>👤 Reconocimiento Facial</h3>
      <button @click="emit('close')" class="btn-close">×</button>
    </div>

    <!-- Tabs -->
    <div class="tabs">
      <button 
        :class="['tab', { active: activeTab === 'detections' }]"
        @click="activeTab = 'detections'"
      >
        📸 Detecciones ({{ recentDetections.length }})
      </button>
      <button 
        :class="['tab', { active: activeTab === 'known' }]"
        @click="activeTab = 'known'"
      >
        🏷️ Caras Conocidas ({{ knownFaces.length }})
      </button>
    </div>

    <!-- Detections Tab -->
    <div v-if="activeTab === 'detections'" class="tab-content">
      <div class="filter-bar">
        <label class="checkbox-filter">
          <input type="checkbox" v-model="showOnlyUnidentified">
          Solo sin identificar
        </label>
        <button @click="fetchDetections" class="btn-refresh" :disabled="loading">
          {{ loading ? '⏳' : '🔄' }} Actualizar
        </button>
      </div>

      <div v-if="recentDetections.length === 0" class="empty-state">
        <p>{{ loading ? 'Cargando...' : 'No hay detecciones faciales recientes' }}</p>
      </div>

      <div class="faces-grid">
        <div 
          v-for="det in recentDetections" 
          :key="det.id"
          class="face-card"
          :class="{ identified: det.identified }"
        >
          <div class="face-image">
            <img 
              v-if="det.face_image_url" 
              :src="det.face_image_url" 
              alt="Face"
            />
            <div v-else class="no-image">👤</div>
          </div>
          <div class="face-info">
            <div class="face-name" v-if="det.identified && det.known_face">
              ✅ {{ det.known_face.name }}
            </div>
            <div class="face-name unknown" v-else>
              ❓ Sin identificar
            </div>
            <div class="face-meta">
              <span>📷 Conf: {{ (det.confidence * 100).toFixed(0) }}%</span>
              <span v-if="det.similarity_score">🎯 Sim: {{ (det.similarity_score * 100).toFixed(0) }}%</span>
            </div>
            <div class="face-time">{{ formatDate(det.created_at) }}</div>
          </div>
          <button 
            v-if="!det.identified"
            @click="openLabelModal(det)"
            class="btn-label"
          >
            🏷️ Etiquetar
          </button>
        </div>
      </div>
    </div>

    <!-- Known Faces Tab -->
    <div v-if="activeTab === 'known'" class="tab-content">
      <div v-if="knownFaces.length === 0" class="empty-state">
        <p>No hay caras registradas. Etiqueta detecciones para agregar.</p>
      </div>

      <div class="known-faces-list">
        <div 
          v-for="face in knownFaces" 
          :key="face.id"
          class="known-face-card"
        >
          <div class="face-image">
            <img 
              v-if="face.face_image_url" 
              :src="face.face_image_url" 
              alt="Face"
            />
            <div v-else class="no-image">👤</div>
          </div>
          <div class="face-details">
            <div class="face-name">{{ face.name }}</div>
            <div class="face-label" v-if="face.label">{{ face.label }}</div>
            <div class="face-stats">
              <span>🔢 {{ face.detection_count }} detecciones</span>
              <span v-if="face.last_seen_at">👁️ Visto: {{ formatDate(face.last_seen_at) }}</span>
            </div>
          </div>
          <div class="face-actions">
            <button @click="editFaceName(face)" class="btn-small">✏️</button>
            <button @click="deleteKnownFace(face)" class="btn-small btn-danger">🗑️</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Label Modal -->
    <div v-if="showLabelModal" class="modal-overlay" @click.self="showLabelModal = false">
      <div class="modal-content">
        <h4>🏷️ Etiquetar Cara</h4>
        
        <div class="modal-preview" v-if="selectedDetection?.face_image_url">
          <img :src="selectedDetection.face_image_url" alt="Face to label">
        </div>

        <div class="modal-options">
          <label class="radio-option">
            <input type="radio" v-model="assignToExisting" :value="false">
            Crear nueva persona
          </label>
          <label class="radio-option" v-if="knownFaces.length > 0">
            <input type="radio" v-model="assignToExisting" :value="true">
            Asignar a persona existente
          </label>
        </div>

        <!-- New face form -->
        <div v-if="!assignToExisting" class="modal-form">
          <input 
            v-model="newFaceName" 
            placeholder="Nombre (ej: Juan Pérez)"
            class="dark-input"
          />
          <input 
            v-model="newFaceLabel" 
            placeholder="Etiqueta opcional (ej: Empleado, Visitante)"
            class="dark-input"
          />
          <button @click="createNewFace" class="btn-primary">
            ✅ Crear y Asignar
          </button>
        </div>

        <!-- Existing face selector -->
        <div v-else class="modal-form">
          <select v-model="selectedKnownFaceId" class="dark-select">
            <option :value="null">-- Selecciona una persona --</option>
            <option v-for="face in knownFaces" :key="face.id" :value="face.id">
              {{ face.name }} {{ face.label ? `(${face.label})` : '' }}
            </option>
          </select>
          <button @click="assignToFace" class="btn-primary" :disabled="!selectedKnownFaceId">
            ✅ Asignar
          </button>
        </div>

        <button @click="showLabelModal = false" class="btn-cancel">
          Cancelar
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.face-panel {
  background: #1e1e1e;
  border-radius: 8px;
  padding: 16px;
  max-height: 500px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.panel-header h3 {
  margin: 0;
  color: #fff;
  font-size: 16px;
}

.btn-close {
  background: none;
  border: none;
  color: #888;
  font-size: 20px;
  cursor: pointer;
}

.btn-close:hover {
  color: #fff;
}

.tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.tab {
  flex: 1;
  padding: 8px 12px;
  background: #2a2a2a;
  border: none;
  border-radius: 4px;
  color: #aaa;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.tab:hover {
  background: #333;
}

.tab.active {
  background: #4a90d9;
  color: #fff;
}

.tab-content {
  flex: 1;
  overflow-y: auto;
}

.filter-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding: 8px;
  background: #252525;
  border-radius: 4px;
}

.checkbox-filter {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #ccc;
  font-size: 13px;
  cursor: pointer;
}

.btn-refresh {
  padding: 4px 10px;
  background: #333;
  border: 1px solid #444;
  border-radius: 4px;
  color: #ccc;
  cursor: pointer;
  font-size: 12px;
}

.btn-refresh:hover:not(:disabled) {
  background: #444;
}

.btn-refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.empty-state {
  text-align: center;
  color: #666;
  padding: 30px;
}

.faces-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 12px;
}

.face-card {
  background: #252525;
  border-radius: 6px;
  padding: 10px;
  text-align: center;
  transition: all 0.2s;
}

.face-card:hover {
  background: #2d2d2d;
}

.face-card.identified {
  border: 1px solid #4a90d9;
}

.face-image {
  width: 80px;
  height: 80px;
  margin: 0 auto 8px;
  border-radius: 50%;
  overflow: hidden;
  background: #333;
  display: flex;
  align-items: center;
  justify-content: center;
}

.face-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.no-image {
  font-size: 32px;
  color: #555;
}

.face-info {
  margin-bottom: 8px;
}

.face-name {
  font-weight: 600;
  color: #fff;
  font-size: 13px;
  margin-bottom: 4px;
}

.face-name.unknown {
  color: #f0ad4e;
}

.face-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 11px;
  color: #888;
}

.face-time {
  font-size: 10px;
  color: #666;
  margin-top: 4px;
}

.btn-label {
  width: 100%;
  padding: 6px;
  background: #4a90d9;
  border: none;
  border-radius: 4px;
  color: #fff;
  cursor: pointer;
  font-size: 12px;
}

.btn-label:hover {
  background: #5a9fea;
}

/* Known faces list */
.known-faces-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.known-face-card {
  display: flex;
  align-items: center;
  gap: 12px;
  background: #252525;
  border-radius: 6px;
  padding: 10px;
}

.known-face-card .face-image {
  width: 50px;
  height: 50px;
  flex-shrink: 0;
  margin: 0;
}

.face-details {
  flex: 1;
}

.face-details .face-name {
  font-size: 14px;
  margin-bottom: 2px;
}

.face-label {
  font-size: 11px;
  color: #4a90d9;
  margin-bottom: 4px;
}

.face-stats {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: #888;
}

.face-actions {
  display: flex;
  gap: 4px;
}

.btn-small {
  padding: 4px 8px;
  background: #333;
  border: 1px solid #444;
  border-radius: 4px;
  color: #ccc;
  cursor: pointer;
  font-size: 12px;
}

.btn-small:hover {
  background: #444;
}

.btn-small.btn-danger:hover {
  background: #d9534f;
  border-color: #d43f3a;
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

.modal-content {
  background: #2a2a2a;
  border-radius: 8px;
  padding: 20px;
  width: 90%;
  max-width: 360px;
}

.modal-content h4 {
  margin: 0 0 16px;
  color: #fff;
}

.modal-preview {
  text-align: center;
  margin-bottom: 16px;
}

.modal-preview img {
  width: 100px;
  height: 100px;
  border-radius: 50%;
  object-fit: cover;
  border: 2px solid #4a90d9;
}

.modal-options {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.radio-option {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #ccc;
  font-size: 13px;
  cursor: pointer;
}

.modal-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.dark-input, .dark-select {
  padding: 10px;
  background: #1e1e1e;
  border: 1px solid #444;
  border-radius: 4px;
  color: #fff;
  font-size: 14px;
}

.dark-input:focus, .dark-select:focus {
  outline: none;
  border-color: #4a90d9;
}

.btn-primary {
  padding: 10px;
  background: #4a90d9;
  border: none;
  border-radius: 4px;
  color: #fff;
  cursor: pointer;
  font-weight: 600;
}

.btn-primary:hover:not(:disabled) {
  background: #5a9fea;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-cancel {
  padding: 10px;
  background: transparent;
  border: 1px solid #444;
  border-radius: 4px;
  color: #888;
  cursor: pointer;
  margin-top: 8px;
  width: 100%;
}

.btn-cancel:hover {
  background: #333;
  color: #ccc;
}
</style>
