<script setup>
import { ref } from 'vue'
const emit = defineEmits(['success'])

const API_URL = 'http://192.168.0.38:8000/api'
const email = ref('')
const password = ref('')
const name = ref('')
const isRegistering = ref(false)

const login = async () => {
  try {
    const endpoint = isRegistering.value ? '/register' : '/login'
    const payload = isRegistering.value ? { name: name.value, email: email.value, password: password.value } : { email: email.value, password: password.value }
    
    const res = await fetch(`${API_URL}${endpoint}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' }, body: JSON.stringify(payload)
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.message)
    
    emit('success', data) // Avisar al padre
  } catch (e) { alert(e.message) }
}

const sendMagicLink = async () => {
  try {
    const res = await fetch(`${API_URL}/auth/magic-link`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: email.value })
    })
    alert('Enlace enviado. Revisa tu correo.')
  } catch (e) { alert(e.message) }
}
</script>

<template>
  <div class="auth-container">
    <div class="auth-card">
      <h2>{{ isRegistering ? 'Crear Cuenta' : 'Iniciar Sesión' }}</h2>
      <input v-if="isRegistering" v-model="name" placeholder="Nombre" />
      <input v-model="email" placeholder="Email" />
      <input v-model="password" type="password" placeholder="Contraseña" />
      <div class="actions">
        <button @click="login">{{ isRegistering ? 'Registrarse' : 'Entrar' }}</button>
        <button @click="sendMagicLink" v-if="!isRegistering" class="magic">✨ Sin Clave</button>
      </div>
      <p @click="isRegistering = !isRegistering">{{ isRegistering ? 'Ya tengo cuenta' : 'Crear cuenta' }}</p>
    </div>
  </div>
</template>

<style scoped>
.auth-container { display: flex; justify-content: center; align-items: center; height: 100vh; background: #1e1e2d; }
.auth-card { background: white; padding: 30px; border-radius: 10px; width: 300px; display: flex; flex-direction: column; gap: 10px; }
button { padding: 10px; cursor: pointer; background: #7367f0; color: white; border: none; border-radius: 5px; }
.magic { background: #ff9f43; margin-top: 5px; }
p { text-align: center; color: #7367f0; cursor: pointer; font-size: 0.9rem; }
input { padding: 8px; border: 1px solid #ddd; }
</style>