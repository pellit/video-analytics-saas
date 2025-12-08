<template>
  <div class="usage-stats">
    <h3 class="stats-title">
      <span class="title-icon">📊</span>
      Uso del Plan
    </h3>

    <div class="stats-grid">
      <!-- Cameras Usage -->
      <div class="stat-card">
        <div class="stat-header">
          <span class="stat-icon">📹</span>
          <span class="stat-label">Cámaras</span>
        </div>
        <div class="stat-value">
          <span class="current">{{ camerasUsed }}</span>
          <span class="separator">/</span>
          <span class="limit">{{ camerasLimit }}</span>
        </div>
        <div class="progress-bar">
          <div 
            class="progress-fill cameras"
            :style="{ width: camerasPercent + '%' }"
            :class="{ warning: camerasPercent > 80, danger: camerasPercent >= 100 }"
          ></div>
        </div>
        <span class="stat-detail">{{ camerasRemaining }} disponibles</span>
      </div>

      <!-- API Calls Usage -->
      <div class="stat-card">
        <div class="stat-header">
          <span class="stat-icon">🔌</span>
          <span class="stat-label">Llamadas API (hoy)</span>
        </div>
        <div class="stat-value">
          <span class="current">{{ formatNumber(apiUsed) }}</span>
          <span class="separator">/</span>
          <span class="limit">{{ formatNumber(apiLimit) }}</span>
        </div>
        <div class="progress-bar">
          <div 
            class="progress-fill api"
            :style="{ width: apiPercent + '%' }"
            :class="{ warning: apiPercent > 80, danger: apiPercent >= 100 }"
          ></div>
        </div>
        <span class="stat-detail">Reinicia en {{ timeUntilReset }}</span>
      </div>

      <!-- Analysis Minutes -->
      <div class="stat-card">
        <div class="stat-header">
          <span class="stat-icon">🧠</span>
          <span class="stat-label">Análisis (este mes)</span>
        </div>
        <div class="stat-value">
          <span class="current">{{ formatNumber(analysisUsed) }}</span>
          <span class="separator">/</span>
          <span class="limit">{{ formatNumber(analysisLimit) }}</span>
        </div>
        <div class="progress-bar">
          <div 
            class="progress-fill analysis"
            :style="{ width: analysisPercent + '%' }"
            :class="{ warning: analysisPercent > 80, danger: analysisPercent >= 100 }"
          ></div>
        </div>
        <span class="stat-detail">{{ daysRemaining }} días restantes del ciclo</span>
      </div>

      <!-- Storage -->
      <div class="stat-card">
        <div class="stat-header">
          <span class="stat-icon">💾</span>
          <span class="stat-label">Almacenamiento</span>
        </div>
        <div class="stat-value">
          <span class="current">{{ formatStorage(storageUsed) }}</span>
          <span class="separator">/</span>
          <span class="limit">{{ formatStorage(storageLimit) }}</span>
        </div>
        <div class="progress-bar">
          <div 
            class="progress-fill storage"
            :style="{ width: storagePercent + '%' }"
            :class="{ warning: storagePercent > 80, danger: storagePercent >= 100 }"
          ></div>
        </div>
        <span class="stat-detail">{{ formatStorage(storageRemaining) }} disponible</span>
      </div>
    </div>

    <!-- Usage History Chart (simplified) -->
    <div class="usage-chart" v-if="showChart">
      <h4>Historial de uso (últimos 7 días)</h4>
      <div class="chart-bars">
        <div 
          v-for="(day, index) in usageHistory" 
          :key="index"
          class="chart-bar-container"
        >
          <div 
            class="chart-bar"
            :style="{ height: day.percent + '%' }"
            :class="{ today: index === usageHistory.length - 1 }"
          ></div>
          <span class="chart-label">{{ day.label }}</span>
        </div>
      </div>
    </div>

    <!-- Upgrade Prompt -->
    <div class="upgrade-prompt" v-if="showUpgradePrompt">
      <div class="prompt-content">
        <span class="prompt-icon">⚠️</span>
        <div class="prompt-text">
          <strong>Estás cerca del límite</strong>
          <p>Actualiza tu plan para continuar sin interrupciones</p>
        </div>
      </div>
      <button class="btn-upgrade" @click="$emit('upgrade')">
        Mejorar plan
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  usage: {
    type: Object,
    default: () => ({
      cameras: 0,
      api_calls: 0,
      analysis_count: 0,
      storage_mb: 0
    })
  },
  limits: {
    type: Object,
    default: () => ({
      max_cameras: 1,
      api_calls_per_day: 10,
      analysis_per_month: 100,
      storage_mb: 1000
    })
  },
  showChart: { type: Boolean, default: true },
  usageHistory: {
    type: Array,
    default: () => [
      { label: 'L', percent: 30 },
      { label: 'M', percent: 45 },
      { label: 'X', percent: 60 },
      { label: 'J', percent: 40 },
      { label: 'V', percent: 80 },
      { label: 'S', percent: 55 },
      { label: 'D', percent: 70 }
    ]
  }
})

const emit = defineEmits(['upgrade'])

// Cameras
const camerasUsed = computed(() => props.usage?.cameras || 0)
const camerasLimit = computed(() => {
  const limit = props.limits?.max_cameras
  return limit === -1 ? '∞' : (limit || 1)
})
const camerasPercent = computed(() => {
  if (camerasLimit.value === '∞') return 0
  return Math.min(100, (camerasUsed.value / camerasLimit.value) * 100)
})
const camerasRemaining = computed(() => {
  if (camerasLimit.value === '∞') return '∞'
  return Math.max(0, camerasLimit.value - camerasUsed.value)
})

// API
const apiUsed = computed(() => props.usage?.api_calls || 0)
const apiLimit = computed(() => {
  const limit = props.limits?.api_calls_per_day
  return limit === -1 ? Infinity : (limit || 10)
})
const apiPercent = computed(() => {
  if (apiLimit.value === Infinity) return 0
  return Math.min(100, (apiUsed.value / apiLimit.value) * 100)
})

// Analysis
const analysisUsed = computed(() => props.usage?.analysis_count || 0)
const analysisLimit = computed(() => {
  const limit = props.limits?.analysis_per_month
  return limit === -1 ? Infinity : (limit || 100)
})
const analysisPercent = computed(() => {
  if (analysisLimit.value === Infinity) return 0
  return Math.min(100, (analysisUsed.value / analysisLimit.value) * 100)
})

// Storage
const storageUsed = computed(() => props.usage?.storage_mb || 0)
const storageLimit = computed(() => {
  const limit = props.limits?.storage_mb
  return limit === -1 ? Infinity : (limit || 1000)
})
const storagePercent = computed(() => {
  if (storageLimit.value === Infinity) return 0
  return Math.min(100, (storageUsed.value / storageLimit.value) * 100)
})
const storageRemaining = computed(() => {
  if (storageLimit.value === Infinity) return Infinity
  return Math.max(0, storageLimit.value - storageUsed.value)
})

// Time calculations
const timeUntilReset = computed(() => {
  const now = new Date()
  const tomorrow = new Date(now)
  tomorrow.setDate(tomorrow.getDate() + 1)
  tomorrow.setHours(0, 0, 0, 0)
  const diff = tomorrow - now
  const hours = Math.floor(diff / (1000 * 60 * 60))
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))
  return `${hours}h ${minutes}m`
})

const daysRemaining = computed(() => {
  const now = new Date()
  const endOfMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0)
  return endOfMonth.getDate() - now.getDate()
})

// Show upgrade prompt when any usage > 80%
const showUpgradePrompt = computed(() => {
  return camerasPercent.value > 80 || apiPercent.value > 80 || analysisPercent.value > 80
})

// Formatters
const formatNumber = (num) => {
  if (num === Infinity || num === '∞') return '∞'
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M'
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K'
  return num.toString()
}

const formatStorage = (mb) => {
  if (mb === Infinity) return '∞'
  if (mb >= 1024) return (mb / 1024).toFixed(1) + ' GB'
  return mb + ' MB'
}
</script>

<style scoped>
.usage-stats {
  background: rgba(15, 23, 42, 0.6);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 16px;
  padding: 24px;
}

.stats-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 1.1rem;
  color: #e2e8f0;
  margin-bottom: 24px;
}

.title-icon {
  font-size: 1.3rem;
}

/* Stats Grid */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

@media (max-width: 600px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }
}

/* Stat Card */
.stat-card {
  background: rgba(0, 0, 0, 0.2);
  border-radius: 12px;
  padding: 16px;
}

.stat-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.stat-icon {
  font-size: 1.2rem;
}

.stat-label {
  font-size: 0.85rem;
  color: #94a3b8;
}

.stat-value {
  font-size: 1.5rem;
  margin-bottom: 8px;
}

.stat-value .current {
  font-weight: 700;
  color: #e2e8f0;
}

.stat-value .separator {
  color: #475569;
  margin: 0 4px;
}

.stat-value .limit {
  color: #64748b;
}

/* Progress Bar */
.progress-bar {
  height: 6px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 3px;
  overflow: hidden;
  margin-bottom: 8px;
}

.progress-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.5s ease;
}

.progress-fill.cameras {
  background: linear-gradient(90deg, #3b82f6, #6366f1);
}

.progress-fill.api {
  background: linear-gradient(90deg, #8b5cf6, #a855f7);
}

.progress-fill.analysis {
  background: linear-gradient(90deg, #06b6d4, #14b8a6);
}

.progress-fill.storage {
  background: linear-gradient(90deg, #f59e0b, #f97316);
}

.progress-fill.warning {
  background: linear-gradient(90deg, #f59e0b, #f97316);
}

.progress-fill.danger {
  background: linear-gradient(90deg, #ef4444, #dc2626);
}

.stat-detail {
  font-size: 0.75rem;
  color: #64748b;
}

/* Usage Chart */
.usage-chart {
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  padding-top: 24px;
  margin-bottom: 24px;
}

.usage-chart h4 {
  font-size: 0.9rem;
  color: #94a3b8;
  margin-bottom: 16px;
  font-weight: 500;
}

.chart-bars {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  height: 100px;
  gap: 8px;
}

.chart-bar-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  height: 100%;
}

.chart-bar {
  width: 100%;
  max-width: 32px;
  background: linear-gradient(180deg, #6366f1, #4f46e5);
  border-radius: 4px 4px 0 0;
  transition: height 0.3s ease;
  margin-top: auto;
}

.chart-bar.today {
  background: linear-gradient(180deg, #8b5cf6, #6366f1);
  box-shadow: 0 0 12px rgba(139, 92, 246, 0.4);
}

.chart-label {
  font-size: 0.7rem;
  color: #64748b;
  margin-top: 8px;
}

/* Upgrade Prompt */
.upgrade-prompt {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: rgba(245, 158, 11, 0.1);
  border: 1px solid rgba(245, 158, 11, 0.3);
  border-radius: 12px;
  padding: 16px 20px;
}

.prompt-content {
  display: flex;
  align-items: center;
  gap: 12px;
}

.prompt-icon {
  font-size: 1.5rem;
}

.prompt-text strong {
  display: block;
  color: #fcd34d;
  font-size: 0.9rem;
  margin-bottom: 4px;
}

.prompt-text p {
  margin: 0;
  font-size: 0.8rem;
  color: #94a3b8;
}

.btn-upgrade {
  padding: 10px 20px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  border: none;
  border-radius: 8px;
  color: white;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.btn-upgrade:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4);
}
</style>
