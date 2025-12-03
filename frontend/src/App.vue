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

// Navegación entre vistas
const handleNavigate = (view) => {
  currentView.value = view
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

  <div v-else class="app-container">
    <UserDashboard 
      v-if="currentView === 'dashboard'" 
      :token="token" 
      :user="user" 
      @logout="handleLogout"
      @navigate="handleNavigate"
    />
    <AdminDashboard 
      v-if="currentView === 'admin'" 
      :token="token"
      :user="user"
      @logout="handleLogout"
      @navigate="handleNavigate"
    />
  </div>
</template>

<style>
/* Reset y estilos base - el tema viene de theme.css */
* {
  box-sizing: border-box;
}

body { 
  margin: 0; 
  font-family: 'Poppins', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
  background: #0d1117;
  color: #c9d1d9;
}

.app-container {
  min-height: 100vh;
  background: #0d1117;
}
</style>