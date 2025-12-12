<template>
  <div class="add-camera-modal glass-card">
    <div class="modal-header">
      <h3>📹 Nueva Cámara</h3>
      <button @click="$emit('close')" class="close-btn">×</button>
    </div>
    
    <form @submit.prevent="submitCamera" class="camera-form">
      <div class="form-group">
        <label>Nombre</label>
        <input 
          v-model="form.name" 
          type="text" 
          placeholder="Cámara Entrada Principal"
          required
        />
      </div>
      
      <div class="form-group">
        <label>URL RTSP</label>
        <input 
          v-model="form.rtsp_url" 
          type="text" 
          placeholder="rtsp://usuario:pass@192.168.1.100:554/stream"
          required
        />
      </div>
      
      <div class="form-row">
        <div class="form-group">
          <label>Latitud (opcional)</label>
          <input 
            v-model.number="form.latitude" 
            type="number" 
            step="any"
            placeholder="-34.6037"
          />
        </div>
        <div class="form-group">
          <label>Longitud (opcional)</label>
          <input 
            v-model.number="form.longitude" 
            type="number" 
            step="any"
            placeholder="-58.3816"
          />
        </div>
      </div>
      
      <div class="form-group">
        <label>Descripción (opcional)</label>
        <textarea 
          v-model="form.description"
          placeholder="Descripción de la ubicación y propósito de la cámara"
          rows="2"
        ></textarea>
      </div>
      
      <div class="form-actions">
        <button type="button" @click="$emit('close')" class="btn-secondary">
          Cancelar
        </button>
        <button type="submit" :disabled="loading" class="btn-primary">
          {{ loading ? 'Guardando...' : '✓ Agregar Cámara' }}
        </button>
      </div>
      
      <p v-if="error" class="error-message">{{ error }}</p>
    </form>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'

const props = defineProps({
  token: String
})

const emit = defineEmits(['close', 'camera-added'])

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

const loading = ref(false)
const error = ref('')

const form = reactive({
  name: '',
  rtsp_url: '',
  latitude: null,
  longitude: null,
  description: ''
})

const submitCamera = async () => {
  loading.value = true
  error.value = ''
  
  try {
    const res = await fetch(`${API_URL}/cameras`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${props.token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(form)
    })
    
    if (res.ok) {
      const camera = await res.json()
      emit('camera-added', camera)
    } else {
      const data = await res.json()
      error.value = data.message || 'Error al agregar cámara'
    }
  } catch (e) {
    error.value = 'Error de conexión'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.add-camera-modal {
  background: rgba(15, 23, 42, 0.95);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(99, 102, 241, 0.3);
  border-radius: 16px;
  padding: 24px;
  width: 100%;
  max-width: 500px;
  color: white;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.modal-header h3 {
  margin: 0;
  font-size: 1.25rem;
}

.close-btn {
  background: none;
  border: none;
  color: #94a3b8;
  font-size: 24px;
  cursor: pointer;
  padding: 0;
  line-height: 1;
}

.close-btn:hover {
  color: white;
}

.camera-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-group label {
  font-size: 0.85rem;
  color: #94a3b8;
}

.form-group input,
.form-group textarea {
  background: rgba(30, 41, 59, 0.8);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  padding: 10px 12px;
  color: white;
  font-size: 0.95rem;
  transition: border-color 0.2s;
}

.form-group input:focus,
.form-group textarea:focus {
  outline: none;
  border-color: #6366f1;
}

.form-group input::placeholder,
.form-group textarea::placeholder {
  color: #64748b;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.form-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  margin-top: 8px;
}

.btn-primary,
.btn-secondary {
  padding: 10px 20px;
  border-radius: 8px;
  font-size: 0.9rem;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-primary {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  border: none;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: #94a3b8;
}

.btn-secondary:hover {
  border-color: rgba(255, 255, 255, 0.4);
  color: white;
}

.error-message {
  color: #ef4444;
  font-size: 0.85rem;
  margin: 0;
  text-align: center;
}
</style>
