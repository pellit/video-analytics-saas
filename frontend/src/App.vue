<script setup>
import { ref, onMounted } from 'vue'

const API_URL = 'http://192.168.0.38:8000/api'
const STREAM_URL = 'http://192.168.0.38:5000/video_feed'

// Estado Auth
const token = ref(localStorage.getItem('token'))
const user = ref(null)
const email = ref('')
const password = ref('')
const isRegistering = ref(false)
const name = ref('')

// Estado App
const cameras = ref([])
const activeCamera = ref(null)
const newCameraName = ref('')
const newCameraUrl = ref('')
const showAddModal = ref(false)
const isProcessing = ref(false)

// --- AUTH ---
const login = async () => {
  try {
    const endpoint = isRegistering.value ? '/register' : '/login'
    const payload = isRegistering.value ? { name: name.value, email: email.value, password: password.value } : { email: email.value, password: password.value }
    
    const res = await fetch(`${API_URL}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    
    const data = await res.json()
    if (!res.ok) throw new Error(data.message)
    
    token.value = data.token
    localStorage.setItem('token', data.token)
    await fetchCameras()
  } catch (e) {
    alert(e.message)
  }
}

const logout = () => {
  token.value = null
  localStorage.removeItem('token')
  activeCamera.value = null
}

// --- CAMERAS ---
const fetchCameras = async () => {
  const res = await fetch(`${API_URL}/cameras`, {
    headers: { 'Authorization': `Bearer ${token.value}`, 'Accept': 'application/json' }
  })
  cameras.value = await res.json()
  if (cameras.value.length > 0) activeCamera.value = cameras.value[0]
}

const addCamera = async () => {
  await fetch(`${API_URL}/cameras`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token.value}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: newCameraName.value, url: newCameraUrl.value })
  })
  showAddModal.value = false
  newCameraName.value = ''
  newCameraUrl.value = ''
  await fetchCameras()
}

const startAnalysis = async () => {
  if(!activeCamera.value) return;
  await fetch(`${API_URL}/camera/start`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token.value}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: activeCamera.value.id, url: activeCamera.value.url })
  })
  isProcessing.value = true
}

const stopAnalysis = async () => {
  await fetch(`${API_URL}/camera/stop`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token.value}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: activeCamera.value.id })
  })
  isProcessing.value = false
}

onMounted(() => {
  if (token.value) fetchCameras()
})
</script>

<template>
  <div v-if="!token" class="auth-container">
    <div class="auth-card">
      <h2>{{ isRegistering ? 'Crear Cuenta' : 'Iniciar Sesión' }}</h2>
      <input v-if="isRegistering" v-model="name" placeholder="Nombre" />
      <input v-model="email" placeholder="Email" />
      <input v-model="password" type="password" placeholder="Contraseña" />
      <button @click="login" class="btn-primary">{{ isRegistering ? 'Registrarse' : 'Entrar' }}</button>
      <p @click="isRegistering = !isRegistering" class="toggle-link">
        {{ isRegistering ? '¿Ya tienes cuenta? Entra' : '¿No tienes cuenta? Regístrate' }}
      </p>
    </div>
  </div>

  <div v-else class="dashboard">
    <aside class="sidebar">
      <div class="user-info">
        <h3>Video SaaS</h3>
        <small>Hola, Usuario</small>
      </div>
      
      <div class="camera-header">
        <h4>Mis Cámaras</h4>
        <button @click="showAddModal = true" class="btn-sm">+</button>
      </div>

      <div class="camera-list">
        <div 
          v-for="cam in cameras" :key="cam.id"
          class="camera-item"
          :class="{ active: activeCamera?.id === cam.id }"
          @click="activeCamera = cam; isProcessing = false"
        >
          {{ cam.name }}
        </div>
      </div>
      
      <button @click="logout" class="btn-logout">Salir</button>
    </aside>

    <main class="content">
      <div v-if="showAddModal" class="modal">
        <div class="modal-content">
          <h3>Nueva Cámara</h3>
          <input v-model="newCameraName" placeholder="Nombre (Ej: Oficina)" />
          <input v-model="newCameraUrl" placeholder="URL YouTube o RTSP" />
          <div class="modal-actions">
            <button @click="addCamera">Guardar</button>
            <button @click="showAddModal = false" class="btn-cancel">Cancelar</button>
          </div>
        </div>
      </div>

      <header v-if="activeCamera">
        <h1>{{ activeCamera.name }}</h1>
        <div>
          <button v-if="!isProcessing" @click="startAnalysis" class="btn-start">▶ Iniciar</button>
          <button v-else @click="stopAnalysis" class="btn-stop">⏹ Detener</button>
        </div>
      </header>

      <div class="video-container">
        <img v-if="isProcessing" :src="STREAM_URL" class="live-stream" />
        <div v-else class="placeholder">Selecciona una cámara e inicia el análisis</div>
      </div>
    </main>
  </div>
</template>

<style scoped>
/* Estilos básicos agregados para Auth y Modal */
.auth-container { display: flex; justify-content: center; align-items: center; height: 100vh; background: #1e1e2d; }
.auth-card { background: white; padding: 30px; border-radius: 10px; width: 300px; display: flex; flex-direction: column; gap: 10px; }
.dashboard { display: flex; height: 100vh; font-family: sans-serif; }
.sidebar { width: 250px; background: #1e1e2d; color: white; padding: 20px; display: flex; flex-direction: column; }
.content { flex: 1; padding: 20px; background: #f0f2f5; }
.camera-item { padding: 10px; margin: 5px 0; cursor: pointer; background: #2b2b40; border-radius: 5px; }
.camera-item.active { background: #7367f0; }
.btn-primary { background: #7367f0; color: white; padding: 10px; border: none; border-radius: 5px; cursor: pointer; }
.toggle-link { text-align: center; color: #7367f0; cursor: pointer; font-size: 0.9rem; }
.modal { position: fixed; top:0; left:0; width:100%; height:100%; background: rgba(0,0,0,0.5); display: flex; justify-content: center; align-items: center; }
.modal-content { background: white; padding: 20px; border-radius: 10px; display: flex; flex-direction: column; gap: 10px; width: 300px; }
.live-stream { width: 100%; max-width: 800px; border-radius: 10px; }
.placeholder { width: 100%; height: 400px; background: black; color: white; display: flex; justify-content: center; align-items: center; border-radius: 10px; }
input { padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
</style>