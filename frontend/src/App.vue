<script setup>
import { ref, onMounted } from 'vue'
import AuthLogin from './components/AuthLogin.vue'
import UserDashboard from './components/UserDashboard.vue'
import AdminDashboard from './components/AdminDashboard.vue'

// Estado Global
const token = ref(localStorage.getItem('token'))
const user = ref(JSON.parse(localStorage.getItem('user') || 'null'))
const currentView = ref('dashboard') // 'dashboard' o 'admin'
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

// Función para iniciar sesión (se pasa a AuthLogin)
const handleLoginSuccess = (data) => {
  token.value = data.token
  user.value = data.user
  localStorage.setItem('token', data.token)
  localStorage.setItem('user', JSON.stringify(data.user))
}

// Función para cerrar sesión (se pasa a los Dashboards)
const handleLogout = () => {
  token.value = null
  user.value = null
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  currentView.value = 'dashboard'
}

// Verificar Magic Link al cargar
onMounted(async () => {
  const urlParams = new URLSearchParams(window.location.search)
  if (urlParams.has('signature') && urlParams.has('id')) {
    // Lógica rápida de verificación para limpiar la URL
    try {
        const verifyUrl = `${API_URL}/auth/verify/${urlParams.get('id')}?expires=${urlParams.get('expires')}&signature=${urlParams.get('signature')}`
        const res = await fetch(verifyUrl)
        const data = await res.json()
        if (res.ok) {
            handleLoginSuccess(data)
            window.history.replaceState({}, document.title, "/")
        }
    } catch (e) {}
  }
})
</script>

<template>
  <AuthLogin 
    v-if="!token" 
    @success="handleLoginSuccess" 
  />

  <div v-else class="app-layout">
    <aside class="sidebar">
      <div class="user-info">
        <h3>Video SaaS</h3>
        <small>Rol: {{ user?.role }}</small>
      </div>
      
      <nav class="nav-menu">
        <button @click="currentView = 'dashboard'" :class="{ active: currentView === 'dashboard' }">
          📹 Mis Cámaras
        </button>
        <button 
          v-if="user?.role === 'superadmin'" 
          @click="currentView = 'admin'" 
          :class="{ active: currentView === 'admin' }"
          class="btn-admin"
        >
          ⚡ SuperAdmin
        </button>
      </nav>
      
      <button @click="handleLogout" class="btn-logout">Salir</button>
    </aside>

    <main class="content">
      <UserDashboard v-if="currentView === 'dashboard'" :token="token" />
      <AdminDashboard v-if="currentView === 'admin'" :token="token" />
    </main>
  </div>
</template>

<style>
/* Estilos Globales del Layout */
body { margin: 0; font-family: sans-serif; background: #f0f2f5; }
.app-layout { display: flex; height: 100vh; }
.sidebar { width: 250px; background: #1e1e2d; color: white; padding: 20px; display: flex; flex-direction: column; }
.content { flex: 1; padding: 20px; overflow-y: auto; }
.nav-menu { display: flex; flex-direction: column; gap: 10px; margin-bottom: auto; border-top: 1px solid #333; padding-top: 20px; }
.nav-menu button { background: transparent; color: #ccc; border: none; text-align: left; padding: 10px; cursor: pointer; }
.nav-menu button.active { color: white; font-weight: bold; border-left: 3px solid #7367f0; }
.btn-logout { margin-top: auto; background: #333; color: white; border: none; padding: 10px; cursor: pointer; }
</style>