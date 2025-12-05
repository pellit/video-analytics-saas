<template>
  <div class="face-pip-container" :class="{ 'inside-video': position === 'inside' }" v-if="faces.length > 0 || showEmpty">
    <div class="pip-header">
      <span class="pip-title">👤 Rostros</span>
      <span class="pip-count">{{ faces.length }}</span>
    </div>
    
    <div class="faces-stack" :class="{ 'horizontal': position === 'inside' }">
      <TransitionGroup name="face-slide">
        <div 
          v-for="(face, index) in faces.slice(0, maxVisible)" 
          :key="face.id || index"
          class="face-card"
          :class="{ 'known': face.name, 'unknown': !face.name, 'new': face.isNew }"
          @click="selectFace(face)"
        >
          <!-- Face Image -->
          <div class="face-image-container">
            <img 
              v-if="face.image_url || face.image_base64" 
              :src="face.image_url || `data:image/jpeg;base64,${face.image_base64}`"
              :alt="face.name || 'Unknown'"
              class="face-image"
            />
            <div v-else class="face-placeholder">
              <span>👤</span>
            </div>
            
            <!-- Confidence indicator -->
            <div class="confidence-ring" :style="{ '--confidence': face.confidence }">
              <span class="confidence-value">{{ Math.round(face.confidence * 100) }}%</span>
            </div>
          </div>
          
          <!-- Face Info -->
          <div class="face-info">
            <h4 class="face-name" :class="{ 'unrecognized': !face.name }">
              {{ face.name || 'Desconocido' }}
            </h4>
            <div class="face-meta">
              <span class="detection-time">{{ formatTime(face.detected_at) }}</span>
              <span v-if="face.match_score" class="match-score">
                Match: {{ Math.round(face.match_score * 100) }}%
              </span>
            </div>
            
            <!-- Action buttons -->
            <div class="face-actions">
              <button 
                v-if="!face.name" 
                class="btn-identify"
                @click.stop="openIdentifyModal(face)"
                title="Identificar rostro"
              >
                ✏️ Nombrar
              </button>
              <button 
                class="btn-history"
                @click.stop="viewHistory(face)"
                title="Ver historial"
              >
                📋
              </button>
            </div>
          </div>
        </div>
      </TransitionGroup>
      
      <!-- Show more indicator -->
      <div v-if="faces.length > maxVisible" class="more-faces" @click="showAll = !showAll">
        <span>+{{ faces.length - maxVisible }} más</span>
      </div>
    </div>
    
    <!-- Empty state -->
    <div v-if="faces.length === 0 && showEmpty" class="empty-state">
      <span class="empty-icon">👁️</span>
      <span class="empty-text">Buscando rostros...</span>
    </div>
    
    <!-- Identify Modal -->
    <Teleport to="body">
      <div v-if="identifyModal.show" class="modal-overlay" @click.self="closeIdentifyModal">
        <div class="identify-modal">
          <div class="modal-header">
            <h3>👤 Identificar Rostro</h3>
            <button class="btn-close" @click="closeIdentifyModal">✕</button>
          </div>
          
          <div class="modal-body">
            <!-- Face preview -->
            <div class="face-preview-large">
              <img 
                v-if="identifyModal.face?.image_url || identifyModal.face?.image_base64"
                :src="identifyModal.face?.image_url || `data:image/jpeg;base64,${identifyModal.face?.image_base64}`"
                alt="Rostro a identificar"
              />
              <div v-else class="face-placeholder-large">👤</div>
            </div>
            
            <div class="form-group">
              <label for="face-name">Nombre de la persona</label>
              <input 
                id="face-name"
                v-model="identifyModal.name"
                type="text"
                placeholder="Ej: Juan Pérez"
                autofocus
                @keyup.enter="saveFaceIdentity"
              />
            </div>
            
            <div class="form-group">
              <label for="face-role">Rol (opcional)</label>
              <select id="face-role" v-model="identifyModal.role">
                <option value="">Sin rol específico</option>
                <option value="employee">Empleado</option>
                <option value="visitor">Visitante</option>
                <option value="vip">VIP</option>
                <option value="restricted">Restringido</option>
                <option value="family">Familiar</option>
              </select>
            </div>
            
            <div class="form-group">
              <label for="face-notes">Notas (opcional)</label>
              <textarea 
                id="face-notes"
                v-model="identifyModal.notes"
                placeholder="Notas adicionales..."
                rows="2"
              ></textarea>
            </div>
          </div>
          
          <div class="modal-footer">
            <button class="btn-secondary" @click="closeIdentifyModal">Cancelar</button>
            <button 
              class="btn-primary" 
              @click="saveFaceIdentity"
              :disabled="!identifyModal.name.trim() || identifyModal.saving"
            >
              {{ identifyModal.saving ? 'Guardando...' : '💾 Guardar Identidad' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'

const props = defineProps({
  cameraId: {
    type: [Number, String],
    required: true
  },
  token: {
    type: String,
    required: true
  },
  maxVisible: {
    type: Number,
    default: 5
  },
  showEmpty: {
    type: Boolean,
    default: false
  },
  position: {
    type: String,
    default: 'fixed' // 'fixed' or 'inside'
  }
})

const emit = defineEmits(['face-selected', 'face-identified', 'notification'])

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'
const AI_URL = import.meta.env.VITE_STREAM_URL?.replace('/video_feed', '') || 'http://localhost:5000'

// State
const faces = ref([])
const showAll = ref(false)
const eventSource = ref(null)

// Identify modal state
const identifyModal = ref({
  show: false,
  face: null,
  name: '',
  role: '',
  notes: '',
  saving: false
})

// Format time helper
const formatTime = (timestamp) => {
  if (!timestamp) return 'Ahora'
  const date = new Date(timestamp)
  const now = new Date()
  const diff = (now - date) / 1000
  
  if (diff < 10) return 'Ahora'
  if (diff < 60) return `${Math.floor(diff)}s`
  if (diff < 3600) return `${Math.floor(diff / 60)}m`
  return date.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })
}

// SSE Connection for real-time face updates
const connectSSE = () => {
  if (eventSource.value) {
    eventSource.value.close()
  }
  
  try {
    const url = `${AI_URL}/events/faces?camera_id=${props.cameraId}`
    eventSource.value = new EventSource(url)
    
    eventSource.value.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        handleFaceEvent(data)
      } catch (e) {
        console.error('Error parsing face event:', e)
      }
    }
    
    eventSource.value.onerror = (error) => {
      console.error('SSE error:', error)
      // Reconnect after delay
      setTimeout(() => connectSSE(), 5000)
    }
  } catch (e) {
    console.error('Error connecting SSE:', e)
  }
}

// Handle incoming face detection event
const handleFaceEvent = (data) => {
  const newFace = {
    id: data.id || Date.now() + Math.random(),
    image_base64: data.face_image_base64,
    image_url: data.face_image_url,
    confidence: data.confidence || data.score || 0.9,
    detected_at: data.detected_at || new Date().toISOString(),
    name: data.name || null,
    match_score: data.match_score,
    embedding_id: data.embedding_id,
    bbox: data.bbox,
    isNew: true
  }
  
  // Add to beginning of list
  faces.value.unshift(newFace)
  
  // Remove isNew flag after animation
  setTimeout(() => {
    const face = faces.value.find(f => f.id === newFace.id)
    if (face) face.isNew = false
  }, 1000)
  
  // Limit faces in memory
  if (faces.value.length > 20) {
    faces.value = faces.value.slice(0, 20)
  }
}

// Fetch recent faces from API
const fetchRecentFaces = async () => {
  try {
    const response = await fetch(
      `${API_URL}/cameras/${props.cameraId}/face-detections?limit=10`,
      {
        headers: {
          'Authorization': `Bearer ${props.token}`,
          'Accept': 'application/json'
        }
      }
    )
    
    if (response.ok) {
      const data = await response.json()
      faces.value = (data.detections || data || []).map(f => ({
        id: f.id,
        image_url: f.face_image_url || f.face_image_path,
        image_base64: f.face_image_base64,
        confidence: f.confidence,
        detected_at: f.detected_at || f.created_at,
        name: f.known_face?.name || f.matched_name,
        match_score: f.match_score,
        embedding_id: f.id,
        bbox: f.bbox
      }))
    }
  } catch (e) {
    console.error('Error fetching faces:', e)
  }
}

// Open identify modal
const openIdentifyModal = (face) => {
  identifyModal.value = {
    show: true,
    face: face,
    name: '',
    role: '',
    notes: '',
    saving: false
  }
}

const closeIdentifyModal = () => {
  identifyModal.value.show = false
}

// Save face identity (create known face with embedding)
const saveFaceIdentity = async () => {
  if (!identifyModal.value.name.trim() || identifyModal.value.saving) return
  
  identifyModal.value.saving = true
  
  try {
    const response = await fetch(`${API_URL}/face-recognition/known-faces`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${props.token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        name: identifyModal.value.name.trim(),
        role: identifyModal.value.role || null,
        notes: identifyModal.value.notes || null,
        face_detection_id: identifyModal.value.face.embedding_id,
        // If we have the embedding directly, send it
        embedding: identifyModal.value.face.embedding
      })
    })
    
    if (response.ok) {
      const result = await response.json()
      
      // Update face in list
      const faceIndex = faces.value.findIndex(f => f.id === identifyModal.value.face.id)
      if (faceIndex !== -1) {
        faces.value[faceIndex].name = identifyModal.value.name
      }
      
      emit('face-identified', {
        face: identifyModal.value.face,
        identity: result
      })
      
      emit('notification', {
        type: 'success',
        message: `Rostro identificado como "${identifyModal.value.name}"`
      })
      
      closeIdentifyModal()
    } else {
      const error = await response.json()
      emit('notification', {
        type: 'error',
        message: error.message || 'Error al guardar identidad'
      })
    }
  } catch (e) {
    console.error('Error saving identity:', e)
    emit('notification', {
      type: 'error',
      message: 'Error de conexión al guardar'
    })
  } finally {
    identifyModal.value.saving = false
  }
}

// Select face (emit event)
const selectFace = (face) => {
  emit('face-selected', face)
}

// View face history
const viewHistory = (face) => {
  // TODO: Navigate to face history view
  console.log('View history for face:', face)
}

// Watch for camera changes
watch(() => props.cameraId, (newId) => {
  faces.value = []
  fetchRecentFaces()
  connectSSE()
})

onMounted(() => {
  fetchRecentFaces()
  connectSSE()
})

onUnmounted(() => {
  if (eventSource.value) {
    eventSource.value.close()
  }
})
</script>

<style scoped>
.face-pip-container {
  position: fixed;
  right: 20px;
  top: 100px;
  width: 280px;
  max-height: calc(100vh - 140px);
  background: linear-gradient(135deg, rgba(20, 20, 30, 0.95), rgba(30, 30, 45, 0.95));
  backdrop-filter: blur(20px);
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  overflow: hidden;
  z-index: 1000;
  display: flex;
  flex-direction: column;
}

/* Inside video positioning */
.face-pip-container.inside-video {
  position: absolute;
  right: 10px;
  top: 10px;
  width: auto;
  max-width: 320px;
  max-height: 180px;
  background: linear-gradient(135deg, rgba(10, 10, 20, 0.85), rgba(20, 20, 35, 0.85));
  border-radius: 12px;
  z-index: 100;
}

.face-pip-container.inside-video .pip-header {
  padding: 8px 12px;
}

.face-pip-container.inside-video .pip-title {
  font-size: 12px;
}

.face-pip-container.inside-video .faces-stack {
  padding: 8px;
  gap: 6px;
}

.face-pip-container.inside-video .faces-stack.horizontal {
  flex-direction: row;
  overflow-x: auto;
  overflow-y: hidden;
}

.face-pip-container.inside-video .face-card {
  flex-direction: column;
  min-width: 70px;
  max-width: 80px;
  padding: 6px;
  gap: 4px;
}

.face-pip-container.inside-video .face-image-container {
  width: 60px;
  height: 60px;
}

.face-pip-container.inside-video .face-image {
  width: 60px;
  height: 60px;
}

.face-pip-container.inside-video .face-info {
  text-align: center;
}

.face-pip-container.inside-video .face-name {
  font-size: 10px;
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 70px;
}

.face-pip-container.inside-video .face-meta,
.face-pip-container.inside-video .face-actions {
  display: none;
}

.face-pip-container.inside-video .confidence-ring {
  width: 16px;
  height: 16px;
  bottom: 2px;
  right: 2px;
}

.face-pip-container.inside-video .confidence-value {
  font-size: 7px;
}

.pip-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: linear-gradient(135deg, rgba(100, 100, 220, 0.3), rgba(150, 100, 200, 0.3));
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.pip-title {
  font-weight: 600;
  color: #fff;
  font-size: 14px;
}

.pip-count {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: white;
  font-size: 12px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 12px;
  min-width: 24px;
  text-align: center;
}

.faces-stack {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.face-card {
  display: flex;
  gap: 12px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.3s ease;
  border: 1px solid transparent;
}

.face-card:hover {
  background: rgba(255, 255, 255, 0.1);
  transform: translateX(-5px);
  border-color: rgba(99, 102, 241, 0.3);
}

.face-card.known {
  border-left: 3px solid #22c55e;
}

.face-card.unknown {
  border-left: 3px solid #f59e0b;
}

.face-card.new {
  animation: slideIn 0.4s ease-out;
  background: rgba(99, 102, 241, 0.2);
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateX(50px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

.face-image-container {
  position: relative;
  width: 60px;
  height: 60px;
  flex-shrink: 0;
}

.face-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 10px;
  border: 2px solid rgba(255, 255, 255, 0.2);
}

.face-placeholder {
  width: 100%;
  height: 100%;
  background: linear-gradient(135deg, rgba(100, 100, 120, 0.5), rgba(80, 80, 100, 0.5));
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
}

.confidence-ring {
  position: absolute;
  bottom: -4px;
  right: -4px;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: conic-gradient(
    #22c55e calc(var(--confidence, 0.9) * 100%),
    rgba(255, 255, 255, 0.2) calc(var(--confidence, 0.9) * 100%)
  );
  display: flex;
  align-items: center;
  justify-content: center;
}

.confidence-value {
  width: 22px;
  height: 22px;
  background: #1a1a2e;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 8px;
  color: #fff;
  font-weight: 600;
}

.face-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.face-name {
  font-size: 14px;
  font-weight: 600;
  color: #fff;
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.face-name.unrecognized {
  color: #f59e0b;
  font-style: italic;
}

.face-meta {
  display: flex;
  gap: 8px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.6);
}

.match-score {
  color: #22c55e;
}

.face-actions {
  display: flex;
  gap: 6px;
  margin-top: 4px;
}

.btn-identify, .btn-history {
  padding: 4px 8px;
  font-size: 11px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-identify {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: white;
}

.btn-identify:hover {
  transform: scale(1.05);
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.4);
}

.btn-history {
  background: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.8);
}

.btn-history:hover {
  background: rgba(255, 255, 255, 0.2);
}

.more-faces {
  text-align: center;
  padding: 8px;
  color: rgba(255, 255, 255, 0.6);
  font-size: 12px;
  cursor: pointer;
  transition: color 0.2s;
}

.more-faces:hover {
  color: #fff;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px;
  gap: 8px;
}

.empty-icon {
  font-size: 32px;
  opacity: 0.5;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 0.8; }
}

.empty-text {
  color: rgba(255, 255, 255, 0.5);
  font-size: 12px;
}

/* Transition animations */
.face-slide-enter-active {
  transition: all 0.4s ease-out;
}

.face-slide-leave-active {
  transition: all 0.3s ease-in;
}

.face-slide-enter-from {
  opacity: 0;
  transform: translateX(50px);
}

.face-slide-leave-to {
  opacity: 0;
  transform: translateX(-50px);
}

.face-slide-move {
  transition: transform 0.3s ease;
}

/* Modal styles */
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
  z-index: 2000;
  backdrop-filter: blur(4px);
}

.identify-modal {
  background: linear-gradient(135deg, #1a1a2e, #252540);
  border-radius: 16px;
  width: 90%;
  max-width: 400px;
  max-height: 90vh;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.2), rgba(139, 92, 246, 0.2));
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.modal-header h3 {
  margin: 0;
  color: #fff;
  font-size: 18px;
}

.btn-close {
  background: none;
  border: none;
  color: rgba(255, 255, 255, 0.7);
  font-size: 20px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  transition: all 0.2s;
}

.btn-close:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}

.modal-body {
  padding: 20px;
}

.face-preview-large {
  width: 150px;
  height: 150px;
  margin: 0 auto 20px;
  border-radius: 16px;
  overflow: hidden;
  border: 3px solid rgba(99, 102, 241, 0.5);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
}

.face-preview-large img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.face-placeholder-large {
  width: 100%;
  height: 100%;
  background: linear-gradient(135deg, rgba(100, 100, 120, 0.5), rgba(80, 80, 100, 0.5));
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 48px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  color: rgba(255, 255, 255, 0.8);
  font-size: 13px;
  font-weight: 500;
}

.form-group input,
.form-group select,
.form-group textarea {
  width: 100%;
  padding: 10px 14px;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  color: #fff;
  font-size: 14px;
  transition: all 0.2s;
}

.form-group input:focus,
.form-group select:focus,
.form-group textarea:focus {
  outline: none;
  border-color: #6366f1;
  background: rgba(255, 255, 255, 0.15);
}

.form-group input::placeholder,
.form-group textarea::placeholder {
  color: rgba(255, 255, 255, 0.4);
}

.form-group select option {
  background: #1a1a2e;
  color: #fff;
}

.modal-footer {
  display: flex;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  justify-content: flex-end;
}

.btn-secondary, .btn-primary {
  padding: 10px 20px;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-secondary {
  background: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.8);
}

.btn-secondary:hover {
  background: rgba(255, 255, 255, 0.2);
}

.btn-primary {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Scrollbar */
.faces-stack::-webkit-scrollbar {
  width: 6px;
}

.faces-stack::-webkit-scrollbar-track {
  background: transparent;
}

.faces-stack::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.2);
  border-radius: 3px;
}

.faces-stack::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.3);
}
</style>
