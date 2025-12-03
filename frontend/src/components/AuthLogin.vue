<script setup>
import { ref, onMounted } from 'vue'
const emit = defineEmits(['success'])

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'
const email = ref('')
const password = ref('')
const name = ref('')
const isRegistering = ref(false)
const rememberMe = ref(false)
const isLoading = ref(false)
const errorMessage = ref('')

onMounted(() => {
  const savedEmail = localStorage.getItem('saved_email')
  if (savedEmail) {
    email.value = savedEmail
    rememberMe.value = true
  }
})

const login = async () => {
  errorMessage.value = ''
  isLoading.value = true
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
    if (!res.ok) throw new Error(data.message || 'Error de autenticación')
    
    if (rememberMe.value) {
      localStorage.setItem('saved_email', email.value)
    } else {
      localStorage.removeItem('saved_email')
    }

    emit('success', data)
  } catch (e) { 
    errorMessage.value = e.message 
  } finally {
    isLoading.value = false
  }
}

const sendMagicLink = async () => {
  if (!email.value) {
    errorMessage.value = 'Ingresa tu email primero'
    return
  }
  isLoading.value = true
  try {
    const res = await fetch(`${API_URL}/auth/magic-link`, {
      method: 'POST', 
      headers: { 'Content-Type': 'application/json' }, 
      body: JSON.stringify({ email: email.value })
    })
    if (res.ok) {
      errorMessage.value = ''
      alert('✨ Enlace mágico enviado. Revisa tu correo.')
    } else {
      throw new Error('Error al enviar enlace')
    }
  } catch (e) { 
    errorMessage.value = e.message 
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="form-wrapper">
    <!-- Form Side -->
    <main class="form-side">
      <div class="logo">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M15 10L19.5528 7.72361C20.2177 7.39116 21 7.87465 21 8.61803V15.382C21 16.1253 20.2177 16.6088 19.5528 16.2764L15 14M5 18H13C14.1046 18 15 17.1046 15 16V8C15 6.89543 14.1046 6 13 6H5C3.89543 6 3 6.89543 3 8V16C3 17.1046 3.89543 18 5 18Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <span>Video Analytics</span>
      </div>
      
      <form class="my-form" @submit.prevent="login">
        <div class="form-welcome-row">
          <h1>{{ isRegistering ? 'Crear Cuenta 🚀' : 'Bienvenido! 👋' }}</h1>
          <h2>{{ isRegistering ? 'Regístrate para comenzar' : 'Inicia sesión en tu cuenta' }}</h2>
        </div>

        <!-- Magic Link Button -->
        <div class="socials-row" v-if="!isRegistering">
          <a href="#" @click.prevent="sendMagicLink" title="Magic Link">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M12 3L13.4302 8.31181C13.6047 8.96315 13.692 9.28881 13.8642 9.55878C14.0166 9.79769 14.2123 10.0034 14.4412 10.1658C14.7012 10.348 15.0168 10.4453 15.6481 10.6398L21 12.3L15.6481 13.9602C15.0168 14.1547 14.7012 14.252 14.4412 14.4342C14.2123 14.5966 14.0166 14.8023 13.8642 15.0412C13.692 15.3112 13.6047 15.6369 13.4302 16.2882L12 21.6L10.5698 16.2882C10.3953 15.6369 10.308 15.3112 10.1358 15.0412C9.98339 14.8023 9.78767 14.5966 9.55877 14.4342C9.2988 14.252 8.98315 14.1547 8.35186 13.9602L3 12.3L8.35186 10.6398C8.98315 10.4453 9.2988 10.348 9.55877 10.1658C9.78767 10.0034 9.98339 9.79769 10.1358 9.55878C10.308 9.28881 10.3953 8.96315 10.5698 8.31181L12 3Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            Acceso sin contraseña
          </a>
        </div>

        <div class="divider" v-if="!isRegistering">
          <div class="divider-line"></div>
          o
          <div class="divider-line"></div>
        </div>

        <!-- Error Message -->
        <div v-if="errorMessage" class="error-banner">
          {{ errorMessage }}
        </div>

        <!-- Name Field (Register only) -->
        <div class="text-field" v-if="isRegistering">
          <label for="name">Nombre</label>
          <input 
            type="text" 
            id="name" 
            v-model="name" 
            autocomplete="name" 
            placeholder="Tu nombre"
            required
          >
        </div>

        <!-- Email Field -->
        <div class="text-field">
          <label for="email">Email</label>
          <input 
            type="email" 
            id="email" 
            v-model="email" 
            autocomplete="email" 
            placeholder="tu@email.com"
            required
          >
        </div>

        <!-- Password Field -->
        <div class="text-field">
          <label for="password">Contraseña</label>
          <input 
            id="password" 
            type="password" 
            v-model="password" 
            placeholder="Tu contraseña" 
            :minlength="isRegistering ? 8 : 1"
            required
          >
        </div>

        <!-- Remember Me -->
        <div class="remember-row" v-if="!isRegistering">
          <label class="checkbox-label">
            <input type="checkbox" v-model="rememberMe">
            <span>Recordar mi email</span>
          </label>
        </div>

        <button class="my-form__button" type="submit" :disabled="isLoading">
          <span v-if="isLoading" class="loader"></span>
          {{ isLoading ? 'Cargando...' : (isRegistering ? 'Crear Cuenta' : 'Iniciar Sesión') }}
        </button>

        <div class="my-form__actions">
          <div class="my-form__row">
            <span>{{ isRegistering ? '¿Ya tienes cuenta?' : '¿No tienes cuenta?' }}</span>
            <a href="#" @click.prevent="isRegistering = !isRegistering; errorMessage = ''">
              {{ isRegistering ? 'Inicia Sesión' : 'Regístrate Ahora' }}
            </a>
          </div>
        </div>
      </form>
    </main>

    <!-- Info Side -->
    <aside class="info-side">
      <div class="info-content">
        <div class="feature-card">
          <div class="feature-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M2 12C2 8.22876 2 6.34315 3.17157 5.17157C4.34315 4 6.22876 4 10 4H14C17.7712 4 19.6569 4 20.8284 5.17157C22 6.34315 22 8.22876 22 12C22 15.7712 22 17.6569 20.8284 18.8284C19.6569 20 17.7712 20 14 20H10C6.22876 20 4.34315 20 3.17157 18.8284C2 17.6569 2 15.7712 2 12Z" stroke="white" stroke-width="1.5"/>
              <circle cx="15" cy="12" r="2" stroke="white" stroke-width="1.5"/>
              <path d="M15 10V7M15 14V17" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
              <path d="M6 8V16" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
              <path d="M9 10V14" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
            </svg>
          </div>
          <h3>Análisis de Video IA</h3>
          <p>Detección de objetos en tiempo real con YOLO, reconocimiento facial, y seguimiento automático.</p>
        </div>

        <div class="stats-grid">
          <div class="stat-item">
            <span class="stat-value">99.2%</span>
            <span class="stat-label">Precisión</span>
          </div>
          <div class="stat-item">
            <span class="stat-value">&lt;50ms</span>
            <span class="stat-label">Latencia</span>
          </div>
          <div class="stat-item">
            <span class="stat-value">24/7</span>
            <span class="stat-label">Monitoreo</span>
          </div>
        </div>

        <blockquote>
          "La plataforma más completa para análisis de video inteligente. Perfecto para seguridad y automatización."
        </blockquote>
        <div class="author">
          <div class="author-avatar">🎥</div>
          <span class="author-name">Video Analytics Pro</span>
        </div>
      </div>
    </aside>
  </div>
</template>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap');

:root {
  --primary: #6366f1;
  --primary-dark: #4f46e5;
  --primary-light: #818cf8;
  --secondary: #1e1b4b;
  --text: #1f2937;
  --text-gray: #6b7280;
  --text-placeholder: #9ca3af;
  --border: #e5e7eb;
  --input-bg: #f9fafb;
  --background: #f3f4f6;
  --error: #ef4444;
  --success: #22c55e;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

.form-wrapper {
  font-family: 'Poppins', sans-serif;
  display: grid;
  grid-template-columns: 1fr 1fr;
  min-height: 100vh;
  width: 100%;
  background: var(--background);
}

/* Form Side */
.form-side {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  background: white;
}

.logo {
  position: absolute;
  top: 1.5rem;
  left: 1.5rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
  font-size: 1.25rem;
  color: var(--primary);
}

.logo svg {
  color: var(--primary);
}

.my-form {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  max-width: 24rem;
  width: 100%;
}

.form-welcome-row {
  margin-bottom: 0.5rem;
}

.form-welcome-row h1 {
  color: #111827;
  font-size: 2rem;
  font-weight: 700;
  margin-bottom: 0.5rem;
}

.form-welcome-row h2 {
  color: #4b5563;
  font-size: 1rem;
  font-weight: 400;
}

/* Social/Magic Link Button */
.socials-row {
  display: flex;
}

.socials-row a {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  width: 100%;
  padding: 0.75rem 1rem;
  border: 2px solid #d1d5db;
  border-radius: 0.5rem;
  text-decoration: none;
  color: #1f2937;
  font-size: 0.95rem;
  font-weight: 500;
  transition: all 0.2s ease;
  background: white;
}

.socials-row a:hover {
  background: #f9fafb;
  border-color: var(--primary);
  color: var(--primary);
}

.socials-row svg {
  color: var(--primary);
}

/* Divider */
.divider {
  display: flex;
  align-items: center;
  gap: 1rem;
  color: #6b7280;
  font-size: 0.875rem;
  font-weight: 500;
}

.divider-line {
  flex: 1;
  height: 1px;
  background: #d1d5db;
}

/* Error Banner */
.error-banner {
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: var(--error);
  padding: 0.75rem 1rem;
  border-radius: 0.5rem;
  font-size: 0.875rem;
}

/* Text Fields */
.text-field {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.text-field label {
  color: #1f2937;
  font-size: 0.875rem;
  font-weight: 600;
}

.text-field input {
  width: 100%;
  padding: 0.75rem 1rem;
  border: 2px solid #d1d5db;
  border-radius: 0.5rem;
  font-size: 1rem;
  font-family: inherit;
  background: #ffffff;
  color: #111827;
  transition: all 0.2s ease;
}

.text-field input::placeholder {
  color: #9ca3af;
}

.text-field input:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15);
}

.text-field input:hover:not(:focus) {
  border-color: #9ca3af;
}

/* Remember Row */
.remember-row {
  display: flex;
  align-items: center;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  font-size: 0.875rem;
  color: #374151;
  font-weight: 500;
}

.checkbox-label input {
  width: 1rem;
  height: 1rem;
  accent-color: var(--primary);
}

/* Submit Button */
.my-form__button {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.875rem 1.5rem;
  background: var(--primary);
  color: white;
  border: none;
  border-radius: 0.5rem;
  font-size: 1rem;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.2s ease;
  margin-top: 0.5rem;
}

.my-form__button:hover:not(:disabled) {
  background: var(--primary-dark);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}

.my-form__button:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.loader {
  width: 1rem;
  height: 1rem;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Form Actions */
.my-form__actions {
  margin-top: 1rem;
}

.my-form__row {
  display: flex;
  justify-content: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: #374151;
}

.my-form__row a {
  color: var(--primary);
  text-decoration: none;
  font-weight: 500;
}

.my-form__row a:hover {
  text-decoration: underline;
}

/* Info Side */
.info-side {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  background: linear-gradient(135deg, var(--secondary) 0%, #312e81 100%);
  position: relative;
  overflow: hidden;
}

.info-side::before {
  content: '';
  position: absolute;
  top: -50%;
  right: -50%;
  width: 100%;
  height: 100%;
  background: radial-gradient(circle, rgba(99, 102, 241, 0.3) 0%, transparent 60%);
}

.info-content {
  position: relative;
  z-index: 1;
  max-width: 24rem;
  color: white;
}

.feature-card {
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  border-radius: 1rem;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.feature-icon {
  margin-bottom: 1rem;
}

.feature-card h3 {
  font-size: 1.25rem;
  font-weight: 600;
  margin-bottom: 0.5rem;
}

.feature-card p {
  font-size: 0.9rem;
  opacity: 0.8;
  line-height: 1.5;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.stat-item {
  text-align: center;
  padding: 1rem;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 0.75rem;
}

.stat-value {
  display: block;
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--primary-light);
}

.stat-label {
  font-size: 0.75rem;
  opacity: 0.7;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.info-content blockquote {
  font-size: 1rem;
  font-style: italic;
  opacity: 0.9;
  margin-bottom: 1rem;
  line-height: 1.6;
}

.author {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.author-avatar {
  width: 2.5rem;
  height: 2.5rem;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.25rem;
}

.author-name {
  font-weight: 500;
}

/* Responsive */
@media (max-width: 768px) {
  .form-wrapper {
    grid-template-columns: 1fr;
  }
  
  .info-side {
    display: none;
  }
  
  .logo {
    position: relative;
    top: 0;
    left: 0;
    margin-bottom: 2rem;
  }
  
  .form-side {
    padding: 1.5rem;
  }
}
</style>