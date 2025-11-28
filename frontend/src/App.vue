<script setup>
import { ref } from 'vue'

// --- CONFIGURACIÓN ---
// IP de tu servidor (Laravel)
const API_URL = 'http://192.168.0.38:8000/api'
// IP de tu servidor (Python Worker Video)
const STREAM_URL = 'http://192.168.0.38:5000/video_feed'

// Estado de la aplicación
const cameras = ref([
  { 
    id: 1, 
    name: 'Cámara Principal', 
    status: 'offline', 
    // Puedes cambiar esto por cualquier video de YouTube
    url: 'https://www.youtube.com/watch?v=3LXQWU67Ufk' 
  }
])

const activeCamera = ref(cameras.value[0])
const isProcessing = ref(false)
const logs = ref([])

// --- FUNCIONES ---

const startAnalysis = async () => {
  // 1. Feedback visual inmediato
  logs.value.unshift(`🚀 Solicitando análisis para: ${activeCamera.value.name}...`)
  
  try {
    // 2. Llamada a Laravel
    const response = await fetch(`${API_URL}/camera/start`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify({
        id: activeCamera.value.id,
        url: activeCamera.value.url,
        name: activeCamera.value.name
      })
    })

    if (!response.ok) {
      throw new Error(`Error HTTP: ${response.status}`)
    }

    const data = await response.json()

    // 3. Éxito: Actualizamos estado
    isProcessing.value = true
    activeCamera.value.status = 'online'
    logs.value.unshift(`✅ Backend respondió: ${data.message}`)

  } catch (error) {
    // 4. Error: Revertimos y mostramos log
    console.error(error)
    isProcessing.value = false
    activeCamera.value.status = 'error'
    logs.value.unshift(`❌ Error de conexión: ${error.message}`)
  }
}

const stopAnalysis = async () => {
  logs.value.unshift(`🛑 Deteniendo análisis...`)
  
  try {
    // Llamada a Laravel para detener
    const response = await fetch(`${API_URL}/camera/stop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: activeCamera.value.id })
    })
    
    // Asumimos que se detiene visualmente aunque el backend tarde un ms
    isProcessing.value = false
    activeCamera.value.status = 'offline'
    
    if (response.ok) {
      logs.value.unshift(`✅ Análisis detenido correctamente.`)
    }

  } catch (error) {
    logs.value.unshift(`⚠️ Error al detener (pero interfaz reseteada): ${error.message}`)
    isProcessing.value = false
    activeCamera.value.status = 'offline'
  }
}
</script>

<template>
  <div class="dashboard">
    <aside class="sidebar">
      <h2>👁️ Video SaaS</h2>
      <div class="camera-list">
        <div 
          v-for="cam in cameras" 
          :key="cam.id"
          class="camera-item"
          :class="{ active: activeCamera.id === cam.id }"
          @click="activeCamera = cam"
        >
          <div class="cam-info">
            <strong>{{ cam.name }}</strong>
            <small style="display:block; font-size: 0.7rem; opacity: 0.7">ID: {{ cam.id }}</small>
          </div>
          <span class="status-dot" :class="cam.status"></span>
        </div>
      </div>
      
      <div style="margin-top: auto; padding-top: 20px; font-size: 0.8rem; opacity: 0.5;">
        <p>Servidor: {{ API_URL }}</p>
      </div>
    </aside>

    <main class="content">
      <header>
        <h1>Monitor en Tiempo Real</h1>
        <div class="actions">
          <button v-if="!isProcessing" @click="startAnalysis" class="btn-start">
            ▶ Iniciar Análisis
          </button>
          <button v-else @click="stopAnalysis" class="btn-stop">
            ⏹ Detener
          </button>
        </div>
      </header>

      <div class="video-grid">
        <div class="video-card">
          <div class="video-wrapper">
            <img v-if="isProcessing" :src="STREAM_URL" class="live-stream" alt="Live Feed" />
            
            <div v-else class="placeholder">
              <div class="placeholder-content">
                <span style="font-size: 3rem;">📺</span>
                <p>El análisis está detenido.</p>
                <small>Presiona "Iniciar" para conectar Laravel con la IA</small>
              </div>
            </div>
          </div>
          
          <div class="video-info">
            <h3>Métricas en Vivo (Demo)</h3>
            <div class="metrics">
              <div class="metric">👥 Personas: <span>--</span></div>
              <div class="metric">🚗 Vehículos: <span>--</span></div>
            </div>
          </div>
        </div>

        <div class="logs-card">
          <h3>Registro de Eventos</h3>
          <ul class="logs-list">
            <li v-for="(log, index) in logs" :key="index">
              <span class="log-time">{{ new Date().toLocaleTimeString() }}</span>
              {{ log }}
            </li>
          </ul>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
/* Reset básico */
* { box-sizing: border-box; }

.dashboard { display: flex; height: 100vh; background-color: #f4f6f9; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }

/* Sidebar */
.sidebar { width: 260px; background: #1e1e2d; color: #ffffff; padding: 25px; display: flex; flex-direction: column; }
.sidebar h2 { margin-bottom: 30px; font-size: 1.4rem; letter-spacing: 1px; color: #7367f0; }
.camera-item { padding: 12px; cursor: pointer; border-radius: 8px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; transition: all 0.2s; background: #2b2b40; }
.camera-item:hover { background: #353550; transform: translateX(3px); }
.camera-item.active { background: #7367f0; box-shadow: 0 4px 12px rgba(115, 103, 240, 0.4); }
.status-dot { width: 10px; height: 10px; border-radius: 50%; background: #555; border: 2px solid #2b2b40; }
.status-dot.online { background: #28c76f; box-shadow: 0 0 8px #28c76f; }
.status-dot.error { background: #ea5455; }

/* Content */
.content { flex: 1; padding: 30px; overflow-y: auto; }

/* Header */
header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.03); }
h1 { margin: 0; font-size: 1.5rem; color: #333; }
.btn-start { background: #7367f0; color: white; border: none; padding: 12px 24px; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 1rem; transition: background 0.3s; }
.btn-start:hover { background: #5e50ee; }
.btn-stop { background: #ea5455; color: white; border: none; padding: 12px 24px; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 1rem; transition: background 0.3s; }
.btn-stop:hover { background: #d33a3b; }

/* Grid */
.video-grid { display: grid; grid-template-columns: 3fr 1fr; gap: 25px; }

/* Video Card */
.video-card { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.05); }
.video-wrapper { width: 100%; aspect-ratio: 16/9; background: #000; display: flex; align-items: center; justify-content: center; border-radius: 8px; overflow: hidden; position: relative; }
.live-stream { width: 100%; height: 100%; object-fit: contain; }
.placeholder { color: #888; text-align: center; display: flex; align-items: center; justify-content: center; height: 100%; width: 100%; background: #f0f0f0; }

.video-info { margin-top: 20px; }
.metrics { display: flex; gap: 20px; margin-top: 10px; }
.metric { font-weight: 600; font-size: 1rem; background: #f8f8f8; padding: 15px; border-radius: 8px; flex: 1; text-align: center; border: 1px solid #eee; }
.metric span { display: block; font-size: 1.8rem; color: #7367f0; margin-top: 5px; }

/* Logs Card */
.logs-card { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.05); height: fit-content; max-height: 600px; display: flex; flex-direction: column; }
.logs-list { list-style: none; padding: 0; margin: 0; overflow-y: auto; max-height: 500px; }
.logs-list li { padding: 10px 0; border-bottom: 1px solid #f0f0f0; font-size: 0.85rem; color: #555; display: flex; flex-direction: column; }
.log-time { font-size: 0.7rem; color: #999; margin-bottom: 3px; }

/* Responsive */
@media (max-width: 1000px) {
  .video-grid { grid-template-columns: 1fr; }
  .dashboard { flex-direction: column; height: auto; }
  .sidebar { width: 100%; flex-direction: row; align-items: center; justify-content: space-between; }
  .camera-list { display: flex; gap: 10px; overflow-x: auto; }
}
</style>