<script setup>
import { ref, onMounted } from 'vue'
const props = defineProps(['token'])
const stats = ref(null)

onMounted(async () => {
  const res = await fetch('http://192.168.0.38:8000/api/admin/stats', {
    headers: { 'Authorization': `Bearer ${props.token}`, 'Accept': 'application/json' }
  })
  if (res.ok) stats.value = await res.json()
})
</script>

<template>
  <div v-if="stats" class="admin-panel">
    <h1>Panel Global</h1>
    <div class="stats-grid">
        <div class="card purple">
            <h3>Usuarios</h3>
            <span>{{ stats.metrics.users }}</span>
        </div>
        <div class="card blue">
            <h3>Cámaras</h3>
            <span>{{ stats.metrics.cameras }}</span>
        </div>
    </div>
    
    <h3>Últimos Registros</h3>
    <ul>
        <li v-for="u in stats.recent_users" :key="u.id">{{ u.name }} ({{ u.email }})</li>
    </ul>
  </div>
</template>

<style scoped>
.stats-grid { display: flex; gap: 20px; margin-bottom: 30px; }
.card { padding: 20px; border-radius: 10px; color: white; min-width: 150px; }
.purple { background: #7367f0; }
.blue { background: #00cfe8; }
.card span { font-size: 2rem; font-weight: bold; display: block; }
</style>