<script setup>
import { ref, onMounted } from 'vue'

// --- CONFIGURACIÓN ---
const API_URL = 'http://192.168.0.38:8000/api'
const STREAM_URL = 'http://192.168.0.38:5000/video_feed'

// --- ESTADO ---
// Auth
const token = ref(localStorage.getItem('token'))
const user = ref(JSON.parse(localStorage.getItem('user') || 'null'))
const email = ref('')
const password = ref('')
const name = ref('')
const isRegistering = ref(false) // Para alternar entre Login/Registro manual

// App
const cameras = ref([])
const activeCamera = ref(null)
const newCameraName = ref('')
const newCameraUrl = ref('')
const showAddModal = ref(false)
const isProcessing = ref(false)
const logs = ref([])
const adminStats = ref(null) // Para el panel de SuperAdmin

// --- FUNCIONES DE AUTH ---

// 1. Login Tradicional (Email + Contraseña)
const login = async () => {
  try {
    const endpoint = isRegistering.value ? '/register' : '/login'
    const payload = isRegistering.value 
      ? { name: name.value, email: email.value, password: password.value } 
      : { email: email.value, password: password.value }
    
    const res = await fetch(`${API_URL}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify(payload)
    })
    
    const data = await res.json()
    if (!res.ok) throw new Error(data.message || 'Error en autenticación')
    
    // Guardar sesión
    saveSession(data.token, data.user)
  } catch (e) {
    alert(e.message)
  }
}

// 2. Login con Magic Link (Sin Contraseña)
const sendMagicLink = async () => {
  if (!email.value) return alert('Escribe tu email primero')
  
  try {
    logs.value.unshift(`📧 Enviando enlace mágico a ${email.value}...`)
    const res = await fetch(`${API_URL}/auth/magic-link`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify({ email: email.value })
    })
    
    const data = await res.json()
    if (!res.ok) throw new Error(data.message)
    
    alert(`¡Listo! Revisa tu correo ${email.value} para entrar.`)
    logs.value.unshift(`✅ Enlace enviado. Revisa http://192.168.0.38:8025`)
  } catch (e) {
    alert(e.message)
  }
}

// Helper para guardar sesión
const saveSession = async (newToken, newUser) => {
  token.value = newToken
  user.value = newUser
  localStorage.setItem('token', newToken)
  localStorage.setItem('user', JSON.stringify(newUser))
  
  // Si es SuperAdmin, cargamos stats
  if (newUser.role === 'superadmin') {
    fetchAdminStats()
  }
  
  await fetchCameras()
}

const logout = () => {
  token.value = null
  user.value = null
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  activeCamera.value = null
}

// --- FUNCIONES DE CÁMARA (CRUD) ---

const fetchCameras = async () => {
  try {
    const res = await fetch(`${API_URL}/cameras`, {
      headers: { 'Authorization': `Bearer ${token.value}`, 'Accept': 'application/json' }
    })
    if (res.ok) {
      cameras.value = await res.json()
      if (cameras.value.length > 0 && !activeCamera.value) {
        activeCamera.value = cameras.value[0]
      }
    }
  } catch (e) { console.error(e) }
}

const addCamera = async () => {
  try {
    const res = await fetch(`${API_URL}/cameras`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token.value}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newCameraName.value, url: newCameraUrl.value })
    })
    if (res.ok) {
      showAddModal.value = false
      newCameraName.value = ''
      newCameraUrl.value = ''
      await fetchCameras()
    }
  } catch (e) { alert('Error al guardar') }
}

// --- CONTROL DE ANÁLISIS ---

const startAnalysis = async () => {
  if(!activeCamera.value) return;
  logs.value.unshift(`🚀 Iniciando: ${activeCamera.value.name}`)
  
  try {
    const res = await fetch(`${API_URL}/camera/start`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token.value}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: activeCamera.value.id, url: activeCamera.value.url })
    })
    if(res.ok) isProcessing.value = true
  } catch(e) { logs.value.unshift('Error al iniciar') }
}

const stopAnalysis = async () => {
  if(!activeCamera.value) return;
  try {
    await fetch(`${API_URL}/camera/stop`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token.value}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: activeCamera.value.id })
    })
    isProcessing.value = false
    logs.value.unshift('🛑 Análisis detenido')
  } catch(e) { console.error(e) }
}

// --- SUPERADMIN ---
const fetchAdminStats = async () => {
  try {
    const res = await fetch(`${API_URL}/admin/stats`, {
       headers: { 'Authorization': `Bearer ${token.value}` }
    })
    if(res.ok) adminStats.value = await res.json()
  } catch(e) {}
}

// --- CICLO DE VIDA (Manejo del Magic Link) ---
onMounted(async () => {
  // 1. Verificar si venimos de un Magic Link (URL tiene ?signature=...)
  const urlParams = new URLSearchParams(window.location.search)
  if (urlParams.has('signature') && urlParams.has('id')) {
    
    const verifyUrl = `${API_URL}/auth/verify/${urlParams.get('id')}?${urlParams.toString()}`.replace('/auth/callback', '')
    
    // Corregimos la URL porque el frontend recibe los params pero debemos mandarlos a la API
    // La forma más fácil es reconstruir la llamada a la API:
    // API espera: http://api:8000/api/auth/verify/{id}?signature=...
    
    try {
        // Hacemos la llamada de verificación a la API
        const apiCallUrl = `${API_URL}/auth/verify/${urlParams.get('id')}?expires=${urlParams.get('expires')}&signature=${urlParams.get('signature')}`
        
        const res = await fetch(apiCallUrl)
        const data = await res.json()
        
        if (res.ok) {
            saveSession(data.token, data.user)
            // Limpiamos la URL para que no se vea fea
            window.history.replaceState({}, document.title, "/")
            alert('¡Login Mágico Exitoso!')
        } else {
            alert('El enlace expiró o no es válido.')
        }
    } catch (e) {
        console.error('Error verificando magic link', e)
    }
  } 
  
  // 2. Si ya teníamos sesión guardada
  else if (token.value) {
    await fetchCameras()
    if (user.value?.role === 'superadmin') fetchAdminStats()
  }
})


// Nuevo Estado para Admin
const currentView = ref('dashboard') // 'dashboard' o 'admin'
const adminData = ref({ metrics: { users: 0, cameras: 0, active: 0 }, recent_users: [] })

// Función para cargar datos de admin
const loadAdminDashboard = async () => {
  currentView.value = 'admin'
  try {
    const res = await fetch(`${API_URL}/admin/stats`, {
      headers: { 
        'Authorization': `Bearer ${token.value}`,
        'Accept': 'application/json'
      }
    })
    if (res.ok) {
      adminData.value = await res.json()
    }
  } catch (e) {
    console.error("Error cargando admin stats", e)
  }
}

// Modifica la función logout para resetear la vista
const logout = () => {
  token.value = null
  user.value = null
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  activeCamera.value = null
  currentView.value = 'dashboard' // Reset
}
</script>

<template>
  <div v-if="!token" class="auth-container">
    <div class="auth-card">
      <h2>{{ isRegistering ? 'Crear Cuenta' : 'Iniciar Sesión' }}</h2>
      
      <input v-if="isRegistering" v-model="name" placeholder="Nombre" />
      <input v-model="email" placeholder="Email" />
      <input v-model="password" type="password" placeholder="Contraseña (Opcional si usas Magic Link)" />

      <div class="auth-actions">
          <button @click="login" class="btn-primary">
            {{ isRegistering ? 'Registrarse' : 'Entrar con Clave' }}
          </button>
          
          <button @click="sendMagicLink" class="btn-magic" v-if="!isRegistering">
            ✨ Entrar sin contraseña
          </button>
      </div>

      <p @click="isRegistering = !isRegistering" class="toggle-link">
        {{ isRegistering ? '¿Ya tienes cuenta?' : 'Crear cuenta nueva' }}
      </p>
    </div>
  </div>

  <div v-else class="dashboard">
      <div v-if="user?.role === 'superadmin'" class="admin-panel">
    <h3>⚡ SuperAdmin</h3>
    <div class="stats">
      <p>Usuarios Totales: {{ adminStats.users }}</p>
      <p>Cámaras Activas: {{ adminStats.cameras }}</p>
    </div>
  </div>
    <aside class="sidebar">
      <div class="user-info">
        <h3>Video SaaS</h3>
        <small>Rol: {{ user?.role }}</small>
      </div>
      
      <nav class="nav-menu">
        <button 
          @click="currentView = 'dashboard'" 
          :class="{ active: currentView === 'dashboard' }"
        >
          📹 Mis Cámaras
        </button>
        
        <button 
          v-if="user?.role === 'superadmin'" 
          @click="loadAdminDashboard"
          :class="{ active: currentView === 'admin' }"
          class="btn-admin"
        >
          ⚡ SuperAdmin
        </button>
      </nav>

      <div v-if="currentView === 'dashboard'" class="camera-list-container">
          <div class="camera-header">
            <h4>Mis Dispositivos</h4>
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
      </div>
      
      <button @click="logout" class="btn-logout">Cerrar Sesión</button>
    </aside>

    <main class="content">
      <div v-if="currentView === 'dashboard'">
         <header v-if="activeCamera">
            <h1>{{ activeCamera.name }}</h1>
            <div>
              <button v-if="!isProcessing" @click="startAnalysis" class="btn-start">▶ Iniciar</button>
              <button v-else @click="stopAnalysis" class="btn-stop">⏹ Detener</button>
            </div>
         </header>
         <div class="video-grid">
            <div class="video-card">
               <img v-if="isProcessing" :src="STREAM_URL" class="live-stream" />
               <div v-else class="placeholder">Selecciona una cámara</div>
            </div>
            </div>
      </div>

      <div v-else-if="currentView === 'admin'" class="admin-dashboard">
        <h1>Panel de Control Global</h1>
        
        <div class="stats-grid">
          <div class="stat-card purple">
            <h3>Usuarios Totales</h3>
            <span class="number">{{ adminData.metrics.users }}</span>
          </div>
          <div class="stat-card blue">
            <h3>Cámaras Registradas</h3>
            <span class="number">{{ adminData.metrics.cameras }}</span>
          </div>
          <div class="stat-card green">
            <h3>Streams Activos</h3>
            <span class="number">{{ adminData.metrics.active }}</span>
          </div>
        </div>

        <div class="users-table-card">
          <h3>Usuarios Registrados Recientemente</h3>
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Nombre</th>
                <th>Email</th>
                <th>Rol</th>
                <th>Fecha</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="u in adminData.recent_users" :key="u.id">
                <td>#{{ u.id }}</td>
                <td>{{ u.name }}</td>
                <td>{{ u.email }}</td>
                <td><span class="badge">{{ u.role }}</span></td>
                <td>{{ new Date(u.created_at).toLocaleDateString() }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
/* Estilos básicos agregados para Auth y Modal */
/* Navegación Sidebar */
.nav-menu { display: flex; flex-direction: column; gap: 10px; margin-bottom: 20px; border-bottom: 1px solid #3b3b52; padding-bottom: 20px; }
.nav-menu button { background: transparent; color: #ccc; border: none; text-align: left; padding: 10px; cursor: pointer; font-size: 1rem; border-radius: 5px; transition: 0.3s; }
.nav-menu button:hover { background: #2b2b40; color: white; }
.nav-menu button.active { background: #3b3b52; color: #fff; font-weight: bold; border-left: 4px solid #7367f0; }
.btn-admin { color: #ff9f43 !important; }

/* Dashboard Admin */
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
.stat-card { padding: 25px; border-radius: 12px; color: white; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
.stat-card h3 { margin: 0 0 10px 0; font-size: 1rem; opacity: 0.9; }
.stat-card .number { font-size: 2.5rem; font-weight: bold; }
.purple { background: linear-gradient(135deg, #7367f0, #9e95f5); }
.blue { background: linear-gradient(135deg, #00cfe8, #66e4f3); }
.green { background: linear-gradient(135deg, #28c76f, #5dd794); }

.users-table-card { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }
table { width: 100%; border-collapse: collapse; margin-top: 15px; }
th { text-align: left; color: #666; font-size: 0.85rem; padding: 10px; border-bottom: 2px solid #f0f0f0; }
td { padding: 12px 10px; border-bottom: 1px solid #f0f0f0; font-size: 0.9rem; color: #333; }
.badge { background: #eee; padding: 4px 8px; border-radius: 4px; font-size: 0.75rem; text-transform: uppercase; font-weight: bold; }
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