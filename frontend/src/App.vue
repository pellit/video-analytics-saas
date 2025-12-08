<script setup>
import { ref, onMounted, computed } from 'vue'
import AuthLogin from './components/AuthLogin.vue'
import UserDashboard from './components/UserDashboard.vue'
import AdminDashboard from './components/AdminDashboard.vue'
import OctopusLayout from './components/OctopusLayout.vue'

// Estado Global
const token = ref(localStorage.getItem('token'))
const user = ref(JSON.parse(localStorage.getItem('user') || 'null'))
const currentView = ref('dashboard') // 'dashboard', 'admin', 'octopus'
const viewMode = ref(localStorage.getItem('viewMode') || 'classic') // 'classic' or 'octopus'
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

// Toggle view mode
const toggleViewMode = () => {
  viewMode.value = viewMode.value === 'classic' ? 'octopus' : 'classic'
  localStorage.setItem('viewMode', viewMode.value)
}

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
  const pathname = window.location.pathname
  
  // El magic link tiene formato: /auth/callback/auth/verify/{id}?expires=...&signature=...
  const verifyMatch = pathname.match(/\/auth\/callback\/auth\/verify\/(\d+)/)
  
  if (verifyMatch && urlParams.has('signature')) {
    const userId = verifyMatch[1]
    try {
        const verifyUrl = `${API_URL}/auth/verify/${userId}?expires=${urlParams.get('expires')}&signature=${urlParams.get('signature')}`
        const res = await fetch(verifyUrl)
        const data = await res.json()
        if (res.ok) {
            handleLoginSuccess(data)
            window.history.replaceState({}, document.title, "/")
        }
    } catch (e) {
      console.error('Error verificando magic link:', e)
    }
  }
})
</script>

<template>
  <AuthLogin 
    v-if="!token" 
    @success="handleLoginSuccess" 
  />

  <div v-else class="app-container">
    <!-- View Mode Toggle Button -->
    <button 
      class="view-mode-toggle"
      @click="toggleViewMode"
      :title="viewMode === 'classic' ? 'Cambiar a vista Octopus 🐙' : 'Cambiar a vista Clásica'"
    >
      {{ viewMode === 'classic' ? '🐙' : '📊' }}
    </button>

    <!-- Classic View -->
    <template v-if="viewMode === 'classic'">
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
    </template>

    <!-- Octopus Command Center View -->
    <OctopusLayout
      v-else
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
  position: relative;
}

/* View Mode Toggle Button */
.view-mode-toggle {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 9999;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  border: none;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: white;
  font-size: 24px;
  cursor: pointer;
  box-shadow: 0 4px 20px rgba(99, 102, 241, 0.4);
  transition: all 0.3s ease;
  display: flex;
  align-items: center;
  justify-content: center;
}

.view-mode-toggle:hover {
  transform: scale(1.1);
  box-shadow: 0 6px 30px rgba(99, 102, 241, 0.6);
}

.view-mode-toggle:active {
  transform: scale(0.95);
}
</style>