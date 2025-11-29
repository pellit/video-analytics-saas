<script setup>
import { ref, onMounted } from 'vue'
const props = defineProps(['token'])

const API_URL = 'http://192.168.0.38:8000/api'
const STREAM_URL = 'http://192.168.0.38:5000/video_feed'

const cameras = ref([])
const activeCamera = ref(null)
const isProcessing = ref(false)
const showAdd = ref(false)
const newCam = ref({ name: '', url: '' })

const fetchCameras = async () => {
  const res = await fetch(`${API_URL}/cameras`, { headers: { 'Authorization': `Bearer ${props.token}`, 'Accept': 'application/json' } })
  if (res.ok) {
      cameras.value = await res.json()
      if (cameras.value.length > 0) activeCamera.value = cameras.value[0]
  }
}

const addCamera = async () => {
  await fetch(`${API_URL}/cameras`, {
    method: 'POST', headers: { 'Authorization': `Bearer ${props.token}`, 'Content-Type': 'application/json' }, body: JSON.stringify(newCam.value)
  })
  showAdd.value = false; fetchCameras()
}

const toggleAnalysis = async (start) => {
  const endpoint = start ? 'start' : 'stop'
  await fetch(`${API_URL}/camera/${endpoint}`, {
    method: 'POST', headers: { 'Authorization': `Bearer ${props.token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ id: activeCamera.value.id, url: activeCamera.value.url })
  })
  isProcessing.value = start
}

onMounted(fetchCameras)
</script>

<template>
  <div class="dashboard-user">
    <div class="cam-bar">
        <div v-for="cam in cameras" :key="cam.id" 
             class="cam-chip" :class="{active: activeCamera?.id === cam.id}"
             @click="activeCamera = cam; isProcessing = false">
             {{ cam.name }}
        </div>
        <button @click="showAdd = true" class="btn-add">+</button>
    </div>

    <div v-if="showAdd" class="modal">
        <div class="modal-content">
            <h3>Nueva Cámara</h3>
            <input v-model="newCam.name" placeholder="Nombre">
            <input v-model="newCam.url" placeholder="URL">
            <button @click="addCamera">Guardar</button>
            <button @click="showAdd = false">Cancelar</button>
        </div>
    </div>

    <div v-if="activeCamera" class="video-section">
        <header>
            <h2>{{ activeCamera.name }}</h2>
            <button v-if="!isProcessing" @click="toggleAnalysis(true)" class="btn-start">▶ Iniciar</button>
            <button v-else @click="toggleAnalysis(false)" class="btn-stop">⏹ Detener</button>
        </header>
        <div class="video-box">
            <img v-if="isProcessing" :src="STREAM_URL" class="stream" />
            <div v-else class="placeholder">Stream Inactivo</div>
        </div>
    </div>
  </div>
</template>

<style scoped>
.cam-bar { display: flex; gap: 10px; padding-bottom: 20px; overflow-x: auto; }
.cam-chip { background: white; padding: 8px 15px; border-radius: 20px; cursor: pointer; border: 1px solid #ddd; }
.cam-chip.active { background: #7367f0; color: white; border-color: #7367f0; }
.video-box { background: black; height: 400px; display: flex; justify-content: center; align-items: center; color: white; border-radius: 10px; overflow: hidden; }
.stream { height: 100%; width: 100%; object-fit: contain; }
.btn-start { background: #28c76f; color: white; padding: 8px 20px; border: none; border-radius: 5px; cursor: pointer; }
.btn-stop { background: #ea5455; color: white; padding: 8px 20px; border: none; border-radius: 5px; cursor: pointer; }
header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.modal { position: fixed; top:0; left:0; width:100%; height:100%; background: rgba(0,0,0,0.5); display: flex; justify-content: center; align-items: center; }
.modal-content { background: white; padding: 20px; display: flex; flex-direction: column; gap: 10px; border-radius: 8px; }
</style>