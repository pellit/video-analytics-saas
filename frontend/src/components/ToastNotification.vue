<script setup>
import { ref, watch, onUnmounted } from 'vue'

const props = defineProps({
  show: { type: Boolean, default: false },
  message: { type: String, default: '' },
  type: { type: String, default: 'success' }, // success, error, warning, info
  duration: { type: Number, default: 3000 }
})

const emit = defineEmits(['close'])

const isVisible = ref(false)
const progress = ref(0)
let timer = null
let progressInterval = null

const typeConfig = {
  success: { bg: '#1a2e1a', color: '#4ade80', icon: '✓' },
  error: { bg: '#2e1a1a', color: '#f87171', icon: '✕' },
  warning: { bg: '#2e2a1a', color: '#fbbf24', icon: '⚠' },
  info: { bg: '#1a1a2e', color: '#60a5fa', icon: 'ℹ' }
}

watch(() => props.show, (newVal) => {
  if (newVal) {
    showToast()
  }
})

const showToast = () => {
  isVisible.value = true
  progress.value = 0
  
  // Progress animation
  const step = 100 / (props.duration / 30)
  progressInterval = setInterval(() => {
    progress.value += step
    if (progress.value >= 100) {
      clearInterval(progressInterval)
    }
  }, 30)
  
  // Auto close
  timer = setTimeout(() => {
    closeToast()
  }, props.duration)
}

const closeToast = () => {
  isVisible.value = false
  clearTimeout(timer)
  clearInterval(progressInterval)
  emit('close')
}

onUnmounted(() => {
  clearTimeout(timer)
  clearInterval(progressInterval)
})
</script>

<template>
  <Teleport to="body">
    <Transition name="toast">
      <div 
        v-if="isVisible" 
        class="toast-container"
        :style="{ 
          '--toast-bg': typeConfig[type].bg, 
          '--toast-color': typeConfig[type].color 
        }"
      >
        <div class="toast-body">
          <span class="toast-icon">{{ typeConfig[type].icon }}</span>
          <span class="toast-message">{{ message }}</span>
          <button class="toast-close" @click="closeToast">✕</button>
        </div>
        <div class="toast-progress" :style="{ transform: `scaleX(${progress / 100})` }"></div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.toast-container {
  position: fixed;
  bottom: 1.5rem;
  left: 50%;
  transform: translateX(-50%);
  min-width: 280px;
  max-width: 420px;
  background: var(--toast-bg);
  border: 1px solid var(--toast-color);
  border-radius: 0.5rem;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
  z-index: 10000;
  overflow: hidden;
}

.toast-body {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem 1.25rem;
  color: var(--toast-color);
  font-size: 0.9rem;
  font-weight: 500;
}

.toast-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  background: var(--toast-color);
  color: var(--toast-bg);
  border-radius: 50%;
  font-size: 0.75rem;
  font-weight: 700;
  flex-shrink: 0;
}

.toast-message {
  flex: 1;
}

.toast-close {
  background: transparent;
  border: none;
  color: var(--toast-color);
  opacity: 0.6;
  cursor: pointer;
  font-size: 0.8rem;
  padding: 0.25rem;
  transition: opacity 0.2s;
}

.toast-close:hover {
  opacity: 1;
}

.toast-progress {
  position: absolute;
  bottom: 0;
  left: 0;
  width: 100%;
  height: 3px;
  background: linear-gradient(to right, var(--toast-bg), var(--toast-color));
  transform-origin: left;
  transition: transform 0.03s linear;
}

/* Transitions */
.toast-enter-active {
  animation: toast-in 0.3s ease-out;
}

.toast-leave-active {
  animation: toast-out 0.25s ease-in;
}

@keyframes toast-in {
  from {
    opacity: 0;
    transform: translateX(-50%) translateY(1rem);
  }
  to {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
  }
}

@keyframes toast-out {
  from {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
  }
  to {
    opacity: 0;
    transform: translateX(-50%) translateY(1rem);
  }
}
</style>
