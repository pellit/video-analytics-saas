<script setup>
import { ref } from 'vue'

// Estado de la aplicación
const cameras = ref([
  { id: 1, name: 'Cámara Principal', status: 'offline', url: 'https://www.youtube.com/watch?v=3LXQWU67Ufk' }
])
const activeCamera = ref(cameras.value[0])
const isProcessing = ref(false)
const logs = ref([])

// URL del Backend (Ajusta la IP si es necesario)
const API_URL = 'http://192.168.0.38:8000/api'
// URL del Worker de Video (Lo configuraremos en el siguiente paso)
const STREAM_URL = 'http://192.168.0.38:5000/video_feed' 

// Funciones
const startAnalysis = async () => {
  logs.value.unshift(`🚀 Iniciando análisis en: ${activeCamera.value.name}`)
  isProcessing.value = true
  activeCamera.value.status = 'online'
  
  // Aquí llamaríamos a Laravel: axios.post(`${API_URL}/camera/start`, ...)
}

const stopAnalysis = () => {
  logs.value.unshift(`🛑 Deteniendo análisis...`)
  isProcessing.value = false
  activeCamera.value.status = 'offline'
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
          {{ cam.name }}
          <span class="status-dot" :class="cam.status"></span>
        </div>
      </div>
    </aside>

    <main class="content">
      <header>
        <h1>Monitor en Tiempo Real</h1>
        <div class="actions">
          <button v-if="!isProcessing" @click="startAnalysis" class="btn-start">▶ Iniciar Análisis</button>
          <button v-else @click="stopAnalysis" class="btn-stop">⏹ Detener</button>
        </div>
      </header>

      <div class="video-grid">
        <div class="video-card">
          <div class="video-wrapper">
            <img v-if="isProcessing" :src="STREAM_URL" class="live-stream" />
            <div v-else class="placeholder">
              <p>El análisis está detenido.</p>
              <small>Presiona "Iniciar" para conectar con la IA</small>
            </div>
          </div>
          <div class="video-info">
            <h3>Detecciones en vivo</h3>
            <div class="metrics">
              <div class="metric">👥 Personas: <span>0</span></div>
              <div class="metric">🚗 Vehículos: <span>0</span></div>
            </div>
          </div>
        </div>

        <div class="logs-card">
          <h3>Registro de Eventos</h3>
          <ul>
            <li v-for="(log, index) in logs" :key="index">{{ log }}</li>
          </ul>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
.dashboard { display: flex; height: 100vh; }
.sidebar { width: 250px; background: #1e1e2d; color: white; padding: 20px; }
.sidebar h2 { margin-bottom: 30px; font-size: 1.2rem; }
.camera-item { padding: 10px; cursor: pointer; border-radius: 5px; margin-bottom: 5px; display: flex; justify-content: space-between; align-items: center; }
.camera-item:hover { background: #2b2b40; }
.camera-item.active { background: #3699ff; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; background: #555; }
.status-dot.online { background: #00ff00; box-shadow: 0 0 5px #00ff00; }

.content { flex: 1; padding: 30px; overflow-y: auto; }
header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; }
.btn-start { background: #3699ff; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; font-weight: bold; }
.btn-stop { background: #f64e60; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; font-weight: bold; }

.video-card { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); margin-bottom: 20px; }
.video-wrapper { width: 100%; height: 400px; background: #000; display: flex; align-items: center; justify-content: center; border-radius: 5px; overflow: hidden; }
.live-stream { width: 100%; height: 100%; object-fit: contain; }
.placeholder { color: #666; text-align: center; }

.metrics { display: flex; gap: 20px; margin-top: 15px; }
.metric { font-weight: bold; font-size: 1.1rem; background: #f0f2f5; padding: 10px; border-radius: 5px; }

.logs-card { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
ul { list-style: none; padding: 0; }
li { padding: 8px 0; border-bottom: 1px solid #eee; font-size: 0.9rem; color: #555; }
</style>