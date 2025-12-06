<template>
  <div class="blueprint-panel">
    <!-- Header -->
    <div class="panel-header">
      <h2>📐 Planos & Arquitectura</h2>
      <p class="subtitle">Análisis inteligente de planos CAD con IA</p>
    </div>

    <!-- Upload Section -->
    <div class="upload-section" v-if="!selectedProject">
      <div 
        class="upload-dropzone"
        :class="{ 'drag-over': isDragging }"
        @dragover.prevent="isDragging = true"
        @dragleave.prevent="isDragging = false"
        @drop.prevent="handleDrop"
        @click="triggerFileInput"
      >
        <input 
          ref="fileInput"
          type="file" 
          accept=".dxf,.dwg,.pdf"
          @change="handleFileSelect"
          hidden
        />
        <div class="dropzone-content">
          <span class="upload-icon">📁</span>
          <p class="upload-text">Arrastra un archivo CAD aquí</p>
          <p class="upload-hint">o haz clic para seleccionar</p>
          <p class="upload-formats">Formatos: DXF, DWG, PDF</p>
        </div>
      </div>

      <!-- Upload Form (shown after file selected) -->
      <div class="upload-form" v-if="uploadFile">
        <div class="selected-file">
          <span class="file-icon">📄</span>
          <div class="file-info">
            <span class="file-name">{{ uploadFile.name }}</span>
            <span class="file-size">{{ formatFileSize(uploadFile.size) }}</span>
          </div>
          <button class="btn-remove" @click="clearFile">✕</button>
        </div>

        <div class="form-group">
          <label>Nombre del proyecto *</label>
          <input 
            v-model="uploadForm.name" 
            type="text" 
            placeholder="Ej: Plano Casa Moderna"
            required
          />
        </div>

        <div class="form-group">
          <label>Descripción</label>
          <textarea 
            v-model="uploadForm.description" 
            placeholder="Descripción opcional del proyecto..."
            rows="2"
          ></textarea>
        </div>

        <div class="form-group">
          <label>Tipo de proyecto</label>
          <select v-model="uploadForm.project_type">
            <option v-for="(label, key) in projectTypes" :key="key" :value="key">
              {{ label }}
            </option>
          </select>
        </div>

        <div class="form-actions">
          <button class="btn-cancel" @click="clearFile">Cancelar</button>
          <button 
            class="btn-upload" 
            @click="uploadProject"
            :disabled="!uploadForm.name || uploading"
          >
            {{ uploading ? 'Subiendo...' : '🚀 Analizar Plano' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Projects List -->
    <div class="projects-section" v-if="!selectedProject">
      <div class="section-header">
        <h3>Mis Proyectos</h3>
        <div class="filter-controls">
          <select v-model="filterStatus" @change="loadProjects">
            <option value="">Todos</option>
            <option value="completed">Completados</option>
            <option value="processing">En proceso</option>
            <option value="error">Con errores</option>
          </select>
        </div>
      </div>

      <div class="projects-grid" v-if="projects.length > 0">
        <div 
          v-for="project in projects" 
          :key="project.id"
          class="project-card"
          :class="{ 'processing': project.status !== 'completed' && project.status !== 'error' }"
          @click="selectProject(project)"
        >
          <div class="project-thumbnail">
            <img 
              v-if="project.render_thumbnail_path" 
              :src="getImageUrl(project.render_thumbnail_path)" 
              :alt="project.name"
            />
            <div v-else class="thumbnail-placeholder">
              <span v-if="project.status === 'error'">❌</span>
              <span v-else-if="project.status === 'completed'">📐</span>
              <span v-else class="spinner">⏳</span>
            </div>
          </div>
          <div class="project-info">
            <h4>{{ project.name }}</h4>
            <span class="project-type">{{ getProjectTypeLabel(project.project_type) }}</span>
            <div class="project-status" :class="project.status">
              <span class="status-badge">{{ getStatusLabel(project.status) }}</span>
              <span v-if="project.progress < 100 && project.status !== 'error'" class="progress-text">
                {{ project.progress }}%
              </span>
            </div>
            <span class="project-date">{{ formatDate(project.created_at) }}</span>
          </div>
          
          <!-- Progress bar for processing projects -->
          <div v-if="project.status !== 'completed' && project.status !== 'error'" class="progress-bar">
            <div class="progress-fill" :style="{ width: project.progress + '%' }"></div>
          </div>
        </div>
      </div>

      <div class="empty-state" v-else>
        <span class="empty-icon">📐</span>
        <p>No hay proyectos aún</p>
        <p class="empty-hint">Sube tu primer plano CAD para comenzar</p>
      </div>

      <!-- Pagination -->
      <div class="pagination" v-if="pagination.last_page > 1">
        <button 
          @click="loadProjects(pagination.current_page - 1)"
          :disabled="pagination.current_page === 1"
        >
          ← Anterior
        </button>
        <span>Página {{ pagination.current_page }} de {{ pagination.last_page }}</span>
        <button 
          @click="loadProjects(pagination.current_page + 1)"
          :disabled="pagination.current_page === pagination.last_page"
        >
          Siguiente →
        </button>
      </div>
    </div>

    <!-- Project Detail View -->
    <div class="project-detail" v-if="selectedProject">
      <div class="detail-header">
        <button class="btn-back" @click="selectedProject = null">← Volver</button>
        <h3>{{ selectedProject.name }}</h3>
        <div class="detail-actions">
          <button 
            class="btn-reanalyze" 
            @click="reanalyzeProject"
            :disabled="selectedProject.status === 'analyzing' || selectedProject.status === 'rendering'"
          >
            🔄 Re-analizar
          </button>
          <button class="btn-delete" @click="confirmDelete">🗑️ Eliminar</button>
        </div>
      </div>

      <!-- Processing State -->
      <div class="processing-state" v-if="selectedProject.status !== 'completed' && selectedProject.status !== 'error'">
        <div class="processing-animation">
          <span class="spinner-large">⚙️</span>
        </div>
        <h4>{{ selectedProject.current_step || 'Procesando...' }}</h4>
        <div class="progress-bar large">
          <div class="progress-fill" :style="{ width: selectedProject.progress + '%' }"></div>
        </div>
        <p class="progress-percent">{{ selectedProject.progress }}% completado</p>
      </div>

      <!-- Error State -->
      <div class="error-state" v-else-if="selectedProject.status === 'error'">
        <span class="error-icon">❌</span>
        <h4>Error en el procesamiento</h4>
        <p class="error-message">{{ selectedProject.error_message }}</p>
        <button class="btn-retry" @click="reanalyzeProject">🔄 Reintentar</button>
      </div>

      <!-- Completed State - Full Analysis View -->
      <div class="analysis-view" v-else>
        <div class="analysis-layout">
          <!-- Left: Rendered Image -->
          <div class="image-panel">
            <div class="image-container">
              <img 
                :src="getImageUrl(selectedProject.render_image_path)" 
                :alt="selectedProject.name"
                @click="showFullImage = true"
              />
              <button class="btn-fullscreen" @click="showFullImage = true">🔍 Ver completo</button>
            </div>
            
            <!-- Metadata -->
            <div class="metadata-section" v-if="selectedProject.metadata">
              <h5>📊 Información del archivo</h5>
              <div class="metadata-grid">
                <div class="meta-item">
                  <span class="meta-label">Unidades</span>
                  <span class="meta-value">{{ selectedProject.metadata.units || 'N/A' }}</span>
                </div>
                <div class="meta-item">
                  <span class="meta-label">Entidades</span>
                  <span class="meta-value">{{ selectedProject.metadata.entity_count || 0 }}</span>
                </div>
                <div class="meta-item">
                  <span class="meta-label">Capas</span>
                  <span class="meta-value">{{ (selectedProject.metadata.layers || []).length }}</span>
                </div>
                <div class="meta-item">
                  <span class="meta-label">Bloques</span>
                  <span class="meta-value">{{ (selectedProject.metadata.block_names || []).length }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Right: Analysis Tabs -->
          <div class="analysis-panel">
            <div class="analysis-tabs">
              <button 
                v-for="tab in analysisTabs" 
                :key="tab.key"
                :class="{ active: activeTab === tab.key }"
                @click="activeTab = tab.key"
              >
                {{ tab.icon }} {{ tab.label }}
              </button>
            </div>

            <div class="tab-content">
              <!-- General Analysis -->
              <div v-if="activeTab === 'general'" class="analysis-content">
                <h4>🏠 Descripción General</h4>
                <div class="ai-response" v-if="selectedProject.analysis_general">
                  <p>{{ selectedProject.analysis_general.response }}</p>
                </div>
                <p class="no-data" v-else>Sin análisis disponible</p>
              </div>

              <!-- Rooms Analysis -->
              <div v-if="activeTab === 'rooms'" class="analysis-content">
                <h4>🚪 Espacios y Habitaciones</h4>
                <div class="ai-response" v-if="selectedProject.analysis_rooms">
                  <p>{{ selectedProject.analysis_rooms.response }}</p>
                </div>
                <p class="no-data" v-else>Sin análisis disponible</p>
              </div>

              <!-- Safety Analysis -->
              <div v-if="activeTab === 'safety'" class="analysis-content">
                <h4>🔥 Seguridad y Evacuación</h4>
                <div class="ai-response" v-if="selectedProject.analysis_safety">
                  <p>{{ selectedProject.analysis_safety.response }}</p>
                </div>
                <p class="no-data" v-else>Sin análisis disponible</p>
              </div>

              <!-- Structural Analysis -->
              <div v-if="activeTab === 'structural'" class="analysis-content">
                <h4>🏗️ Elementos Estructurales</h4>
                <div class="ai-response" v-if="selectedProject.analysis_structural">
                  <p>{{ selectedProject.analysis_structural.response }}</p>
                </div>
                <p class="no-data" v-else>Sin análisis disponible</p>
              </div>

              <!-- Dimensions Analysis -->
              <div v-if="activeTab === 'dimensions'" class="analysis-content">
                <h4>📏 Dimensiones Estimadas</h4>
                <div class="ai-response" v-if="selectedProject.analysis_dimensions">
                  <p>{{ selectedProject.analysis_dimensions.response }}</p>
                </div>
                <p class="no-data" v-else>Sin análisis disponible</p>
              </div>

              <!-- Materials Analysis -->
              <div v-if="activeTab === 'materials'" class="analysis-content">
                <h4>🧱 Materiales Sugeridos</h4>
                <div class="ai-response" v-if="selectedProject.analysis_materials">
                  <p>{{ selectedProject.analysis_materials.response }}</p>
                </div>
                <p class="no-data" v-else>Sin análisis disponible</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Fullscreen Image Modal -->
    <div class="modal-overlay" v-if="showFullImage" @click="showFullImage = false">
      <div class="modal-content" @click.stop>
        <button class="modal-close" @click="showFullImage = false">✕</button>
        <img 
          :src="getImageUrl(selectedProject?.render_image_path)" 
          :alt="selectedProject?.name"
        />
      </div>
    </div>

    <!-- Delete Confirmation Modal -->
    <div class="modal-overlay" v-if="showDeleteConfirm" @click="showDeleteConfirm = false">
      <div class="modal-dialog" @click.stop>
        <h4>¿Eliminar proyecto?</h4>
        <p>Esta acción no se puede deshacer. Se eliminarán el archivo y todos los análisis.</p>
        <div class="modal-actions">
          <button class="btn-cancel" @click="showDeleteConfirm = false">Cancelar</button>
          <button class="btn-delete" @click="deleteProject">Eliminar</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, computed } from 'vue'

const props = defineProps({
  apiUrl: {
    type: String,
    required: true
  },
  storageUrl: {
    type: String,
    default: ''
  }
})

// State
const projects = ref([])
const selectedProject = ref(null)
const uploadFile = ref(null)
const uploading = ref(false)
const isDragging = ref(false)
const filterStatus = ref('')
const showFullImage = ref(false)
const showDeleteConfirm = ref(false)
const activeTab = ref('general')
const fileInput = ref(null)

const pagination = reactive({
  total: 0,
  per_page: 12,
  current_page: 1,
  last_page: 1
})

const uploadForm = reactive({
  name: '',
  description: '',
  project_type: 'architecture'
})

// Project types
const projectTypes = {
  architecture: '🏠 Arquitectura',
  engineering: '⚙️ Ingeniería Civil',
  electrical: '⚡ Instalaciones Eléctricas',
  plumbing: '🚿 Instalaciones Sanitarias',
  structural: '🏗️ Estructural',
  hvac: '❄️ Climatización (HVAC)',
  landscape: '🌳 Paisajismo',
  interior: '🛋️ Diseño Interior',
  urban: '🏙️ Urbanismo',
  other: '📄 Otro'
}

const statusLabels = {
  pending: '⏳ Pendiente',
  rendering: '🖼️ Renderizando',
  analyzing: '🤖 Analizando',
  completed: '✅ Completado',
  error: '❌ Error'
}

// Analysis tabs
const analysisTabs = [
  { key: 'general', icon: '🏠', label: 'General' },
  { key: 'rooms', icon: '🚪', label: 'Espacios' },
  { key: 'safety', icon: '🔥', label: 'Seguridad' },
  { key: 'structural', icon: '🏗️', label: 'Estructura' },
  { key: 'dimensions', icon: '📏', label: 'Dimensiones' },
  { key: 'materials', icon: '🧱', label: 'Materiales' }
]

// Polling interval for processing projects
let pollInterval = null

// API helper
async function api(method, endpoint, data = null) {
  const token = localStorage.getItem('token')
  const options = {
    method,
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
      'Accept': 'application/json'
    }
  }
  
  if (data && method !== 'GET') {
    if (data instanceof FormData) {
      delete options.headers['Content-Type']
      options.body = data
    } else {
      options.body = JSON.stringify(data)
    }
  }
  
  const response = await fetch(`${props.apiUrl}${endpoint}`, options)
  return response.json()
}

// Load projects
async function loadProjects(page = 1) {
  try {
    let url = `/cad/projects?page=${page}&per_page=${pagination.per_page}`
    if (filterStatus.value) {
      url += `&status=${filterStatus.value}`
    }
    
    const data = await api('GET', url)
    
    if (data.success) {
      projects.value = data.projects
      Object.assign(pagination, data.pagination)
    }
  } catch (error) {
    console.error('Error loading projects:', error)
  }
}

// File handling
function triggerFileInput() {
  fileInput.value?.click()
}

function handleFileSelect(event) {
  const file = event.target.files?.[0]
  if (file) {
    setUploadFile(file)
  }
}

function handleDrop(event) {
  isDragging.value = false
  const file = event.dataTransfer.files?.[0]
  if (file) {
    setUploadFile(file)
  }
}

function setUploadFile(file) {
  const ext = file.name.split('.').pop().toLowerCase()
  if (!['dxf', 'dwg', 'pdf'].includes(ext)) {
    alert('Formato no soportado. Use archivos DXF, DWG o PDF.')
    return
  }
  uploadFile.value = file
  uploadForm.name = file.name.replace(/\.[^/.]+$/, '') // Remove extension
}

function clearFile() {
  uploadFile.value = null
  uploadForm.name = ''
  uploadForm.description = ''
  uploadForm.project_type = 'architecture'
  if (fileInput.value) {
    fileInput.value.value = ''
  }
}

// Upload project
async function uploadProject() {
  if (!uploadFile.value || !uploadForm.name) return
  
  uploading.value = true
  
  try {
    const formData = new FormData()
    formData.append('file', uploadFile.value)
    formData.append('name', uploadForm.name)
    formData.append('description', uploadForm.description)
    formData.append('project_type', uploadForm.project_type)
    
    const token = localStorage.getItem('token')
    const response = await fetch(`${props.apiUrl}/cad/projects`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Accept': 'application/json'
      },
      body: formData
    })
    
    const data = await response.json()
    
    if (data.success) {
      clearFile()
      await loadProjects()
      // Auto-select the new project
      selectProject(data.project)
    } else {
      alert(data.message || 'Error al subir el archivo')
    }
  } catch (error) {
    console.error('Error uploading:', error)
    alert('Error al subir el archivo')
  } finally {
    uploading.value = false
  }
}

// Select project
function selectProject(project) {
  selectedProject.value = project
  activeTab.value = 'general'
  
  // Start polling if processing
  if (project.status !== 'completed' && project.status !== 'error') {
    startPolling()
  }
}

// Polling for processing status
function startPolling() {
  stopPolling()
  pollInterval = setInterval(async () => {
    if (!selectedProject.value) {
      stopPolling()
      return
    }
    
    try {
      const data = await api('GET', `/cad/projects/${selectedProject.value.id}/status`)
      
      if (data.success) {
        selectedProject.value.status = data.status
        selectedProject.value.progress = data.progress
        selectedProject.value.current_step = data.current_step
        selectedProject.value.error_message = data.error_message
        
        // If completed or error, reload full project and stop polling
        if (data.is_completed || data.status === 'error') {
          await reloadSelectedProject()
          stopPolling()
        }
      }
    } catch (error) {
      console.error('Polling error:', error)
    }
  }, 2000) // Poll every 2 seconds
}

function stopPolling() {
  if (pollInterval) {
    clearInterval(pollInterval)
    pollInterval = null
  }
}

async function reloadSelectedProject() {
  if (!selectedProject.value) return
  
  try {
    const data = await api('GET', `/cad/projects/${selectedProject.value.id}`)
    if (data.success) {
      selectedProject.value = data.project
      // Also update in list
      const idx = projects.value.findIndex(p => p.id === data.project.id)
      if (idx !== -1) {
        projects.value[idx] = data.project
      }
    }
  } catch (error) {
    console.error('Error reloading project:', error)
  }
}

// Re-analyze
async function reanalyzeProject() {
  if (!selectedProject.value) return
  
  try {
    const data = await api('POST', `/cad/projects/${selectedProject.value.id}/reanalyze`)
    
    if (data.success) {
      selectedProject.value = data.project
      startPolling()
    } else {
      alert(data.message || 'Error al re-analizar')
    }
  } catch (error) {
    console.error('Error re-analyzing:', error)
    alert('Error al re-analizar')
  }
}

// Delete
function confirmDelete() {
  showDeleteConfirm.value = true
}

async function deleteProject() {
  if (!selectedProject.value) return
  
  try {
    const data = await api('DELETE', `/cad/projects/${selectedProject.value.id}`)
    
    if (data.success) {
      showDeleteConfirm.value = false
      selectedProject.value = null
      await loadProjects()
    } else {
      alert(data.message || 'Error al eliminar')
    }
  } catch (error) {
    console.error('Error deleting:', error)
    alert('Error al eliminar')
  }
}

// Helpers
function getImageUrl(path) {
  if (!path) return ''
  const storageBase = props.storageUrl || props.apiUrl.replace('/api', '')
  return `${storageBase}/storage/${path}`
}

function getProjectTypeLabel(type) {
  return projectTypes[type] || type
}

function getStatusLabel(status) {
  return statusLabels[status] || status
}

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleDateString('es-ES', {
    day: '2-digit',
    month: 'short',
    year: 'numeric'
  })
}

// Lifecycle
onMounted(() => {
  loadProjects()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.blueprint-panel {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

.panel-header {
  margin-bottom: 24px;
}

.panel-header h2 {
  margin: 0;
  font-size: 1.8rem;
  color: #1a1a2e;
}

.subtitle {
  margin: 4px 0 0;
  color: #666;
  font-size: 0.95rem;
}

/* Upload Section */
.upload-section {
  margin-bottom: 32px;
}

.upload-dropzone {
  border: 2px dashed #ccc;
  border-radius: 12px;
  padding: 40px 20px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s ease;
  background: #fafafa;
}

.upload-dropzone:hover,
.upload-dropzone.drag-over {
  border-color: #4a90d9;
  background: #f0f7ff;
}

.dropzone-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.upload-icon {
  font-size: 3rem;
}

.upload-text {
  font-size: 1.1rem;
  font-weight: 500;
  color: #333;
  margin: 0;
}

.upload-hint {
  color: #888;
  font-size: 0.9rem;
  margin: 0;
}

.upload-formats {
  color: #aaa;
  font-size: 0.8rem;
  margin: 8px 0 0;
}

/* Upload Form */
.upload-form {
  margin-top: 20px;
  padding: 20px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.selected-file {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: #f5f5f5;
  border-radius: 8px;
  margin-bottom: 16px;
}

.file-icon {
  font-size: 2rem;
}

.file-info {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.file-name {
  font-weight: 500;
  color: #333;
}

.file-size {
  font-size: 0.85rem;
  color: #888;
}

.btn-remove {
  background: none;
  border: none;
  font-size: 1.2rem;
  cursor: pointer;
  color: #888;
  padding: 4px 8px;
}

.btn-remove:hover {
  color: #e74c3c;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  font-weight: 500;
  color: #444;
}

.form-group input,
.form-group textarea,
.form-group select {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #ddd;
  border-radius: 8px;
  font-size: 1rem;
}

.form-group input:focus,
.form-group textarea:focus,
.form-group select:focus {
  outline: none;
  border-color: #4a90d9;
}

.form-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  margin-top: 20px;
}

.btn-cancel {
  padding: 10px 20px;
  background: #f5f5f5;
  border: 1px solid #ddd;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.95rem;
}

.btn-upload {
  padding: 10px 24px;
  background: linear-gradient(135deg, #4a90d9, #357abd);
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.95rem;
  font-weight: 500;
}

.btn-upload:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Projects Section */
.projects-section {
  margin-top: 32px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-header h3 {
  margin: 0;
  font-size: 1.3rem;
}

.filter-controls select {
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 8px;
  font-size: 0.9rem;
}

/* Projects Grid */
.projects-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 20px;
}

.project-card {
  background: white;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  cursor: pointer;
  transition: all 0.3s ease;
  position: relative;
}

.project-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0,0,0,0.15);
}

.project-card.processing {
  opacity: 0.9;
}

.project-thumbnail {
  height: 160px;
  background: #f0f0f0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.project-thumbnail img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumbnail-placeholder {
  font-size: 3rem;
  color: #ccc;
}

.spinner {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.project-info {
  padding: 16px;
}

.project-info h4 {
  margin: 0 0 8px;
  font-size: 1rem;
  color: #333;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.project-type {
  display: inline-block;
  font-size: 0.8rem;
  color: #666;
  background: #f0f0f0;
  padding: 2px 8px;
  border-radius: 4px;
}

.project-status {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-badge {
  font-size: 0.85rem;
}

.progress-text {
  font-size: 0.8rem;
  color: #4a90d9;
  font-weight: 500;
}

.project-date {
  display: block;
  margin-top: 8px;
  font-size: 0.8rem;
  color: #999;
}

.progress-bar {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 4px;
  background: #eee;
}

.progress-bar.large {
  position: relative;
  height: 8px;
  border-radius: 4px;
  margin-top: 12px;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #4a90d9, #67b26f);
  transition: width 0.3s ease;
}

/* Empty State */
.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: #888;
}

.empty-icon {
  font-size: 4rem;
  display: block;
  margin-bottom: 16px;
}

.empty-hint {
  font-size: 0.9rem;
  color: #aaa;
}

/* Pagination */
.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 16px;
  margin-top: 24px;
}

.pagination button {
  padding: 8px 16px;
  background: #f5f5f5;
  border: 1px solid #ddd;
  border-radius: 6px;
  cursor: pointer;
}

.pagination button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Project Detail */
.project-detail {
  background: white;
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.1);
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid #eee;
}

.detail-header h3 {
  flex: 1;
  margin: 0;
}

.btn-back {
  padding: 8px 16px;
  background: #f5f5f5;
  border: 1px solid #ddd;
  border-radius: 6px;
  cursor: pointer;
}

.detail-actions {
  display: flex;
  gap: 8px;
}

.btn-reanalyze {
  padding: 8px 16px;
  background: #4a90d9;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
}

.btn-reanalyze:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-delete {
  padding: 8px 16px;
  background: #e74c3c;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
}

/* Processing State */
.processing-state {
  text-align: center;
  padding: 60px 20px;
}

.processing-animation {
  margin-bottom: 20px;
}

.spinner-large {
  font-size: 4rem;
  animation: spin 2s linear infinite;
}

.progress-percent {
  color: #666;
  margin-top: 8px;
}

/* Error State */
.error-state {
  text-align: center;
  padding: 60px 20px;
}

.error-icon {
  font-size: 4rem;
  display: block;
  margin-bottom: 16px;
}

.error-message {
  color: #e74c3c;
  margin: 12px 0 20px;
}

.btn-retry {
  padding: 12px 24px;
  background: #4a90d9;
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 1rem;
}

/* Analysis Layout */
.analysis-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}

@media (max-width: 1024px) {
  .analysis-layout {
    grid-template-columns: 1fr;
  }
}

.image-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.image-container {
  position: relative;
  background: #f5f5f5;
  border-radius: 8px;
  overflow: hidden;
}

.image-container img {
  width: 100%;
  height: auto;
  display: block;
  cursor: zoom-in;
}

.btn-fullscreen {
  position: absolute;
  bottom: 12px;
  right: 12px;
  padding: 8px 16px;
  background: rgba(0,0,0,0.7);
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85rem;
}

/* Metadata */
.metadata-section {
  background: #f9f9f9;
  padding: 16px;
  border-radius: 8px;
}

.metadata-section h5 {
  margin: 0 0 12px;
  font-size: 0.95rem;
}

.metadata-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.meta-item {
  display: flex;
  flex-direction: column;
}

.meta-label {
  font-size: 0.8rem;
  color: #888;
}

.meta-value {
  font-weight: 500;
  color: #333;
}

/* Analysis Panel */
.analysis-panel {
  display: flex;
  flex-direction: column;
}

.analysis-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.analysis-tabs button {
  padding: 8px 16px;
  background: #f5f5f5;
  border: 1px solid #ddd;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85rem;
  transition: all 0.2s ease;
}

.analysis-tabs button:hover {
  background: #eee;
}

.analysis-tabs button.active {
  background: #4a90d9;
  color: white;
  border-color: #4a90d9;
}

.tab-content {
  flex: 1;
  background: #f9f9f9;
  border-radius: 8px;
  padding: 20px;
  min-height: 300px;
}

.analysis-content h4 {
  margin: 0 0 16px;
  font-size: 1.1rem;
  color: #333;
}

.ai-response {
  background: white;
  padding: 16px;
  border-radius: 8px;
  border-left: 4px solid #4a90d9;
}

.ai-response p {
  margin: 0;
  line-height: 1.6;
  white-space: pre-wrap;
}

.no-data {
  color: #999;
  font-style: italic;
}

/* Modal */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0,0,0,0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}

.modal-content {
  position: relative;
  max-width: 95vw;
  max-height: 95vh;
}

.modal-content img {
  max-width: 100%;
  max-height: 90vh;
  border-radius: 8px;
}

.modal-close {
  position: absolute;
  top: -40px;
  right: 0;
  background: white;
  border: none;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  cursor: pointer;
  font-size: 1.2rem;
}

.modal-dialog {
  background: white;
  padding: 24px;
  border-radius: 12px;
  max-width: 400px;
  text-align: center;
}

.modal-dialog h4 {
  margin: 0 0 12px;
}

.modal-dialog p {
  color: #666;
  margin: 0 0 20px;
}

.modal-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}
</style>
