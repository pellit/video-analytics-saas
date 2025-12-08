<template>
  <div class="subscription-banner" :class="bannerClass">
    <div class="banner-content">
      <!-- Plan Info -->
      <div class="plan-info">
        <span class="plan-icon">{{ planIcon }}</span>
        <div class="plan-details">
          <span class="plan-name">{{ planName }}</span>
          <span class="plan-status">{{ statusText }}</span>
        </div>
      </div>

      <!-- Usage Summary -->
      <div class="usage-summary" v-if="!isSuperAdmin">
        <div class="usage-item" :class="{ 'warning': cameraUsagePercent > 80 }">
          <span class="usage-label">Cámaras</span>
          <div class="usage-bar">
            <div class="usage-fill" :style="{ width: cameraUsagePercent + '%' }"></div>
          </div>
          <span class="usage-text">{{ camerasUsed }}/{{ camerasLimit }}</span>
        </div>
        <div class="usage-item" :class="{ 'warning': apiUsagePercent > 80 }">
          <span class="usage-label">API</span>
          <div class="usage-bar">
            <div class="usage-fill" :style="{ width: apiUsagePercent + '%' }"></div>
          </div>
          <span class="usage-text">{{ apiUsed }}/{{ apiLimit }}</span>
        </div>
      </div>

      <!-- SuperAdmin Badge -->
      <div class="superadmin-badge" v-if="isSuperAdmin">
        <span class="badge-icon">⚡</span>
        <span class="badge-text">Sin límites</span>
      </div>

      <!-- Actions -->
      <div class="banner-actions">
        <button 
          v-if="canUpgrade" 
          class="btn-upgrade"
          @click="$emit('upgrade')"
        >
          <span>🚀</span> Mejorar Plan
        </button>
        <button 
          class="btn-manage"
          @click="$emit('manage')"
        >
          Gestionar
        </button>
      </div>
    </div>

    <!-- Trial Warning -->
    <div v-if="isTrialing && daysRemaining <= 7" class="trial-warning">
      <span class="warning-icon">⏰</span>
      <span>Tu prueba termina en {{ daysRemaining }} días</span>
      <button class="btn-activate" @click="$emit('activate')">Activar ahora</button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  plan: {
    type: Object,
    default: () => ({
      name: 'Free',
      slug: 'free',
      limits: { max_cameras: 1, api_calls_per_day: 10 }
    })
  },
  subscription: {
    type: Object,
    default: () => ({ status: 'active' })
  },
  usage: {
    type: Object,
    default: () => ({ cameras: 0, api_calls: 0 })
  },
  user: {
    type: Object,
    default: () => ({ role: 'user' })
  }
})

const emit = defineEmits(['upgrade', 'manage', 'activate'])

// Computed properties
const isSuperAdmin = computed(() => props.user?.role === 'superadmin')

const planName = computed(() => {
  if (isSuperAdmin.value) return 'SuperAdmin'
  return props.plan?.name || 'Free'
})

const planIcon = computed(() => {
  if (isSuperAdmin.value) return '👑'
  const icons = {
    free: '🆓',
    pro: '⭐',
    enterprise: '💎'
  }
  return icons[props.plan?.slug] || '📦'
})

const isTrialing = computed(() => props.subscription?.status === 'trialing')
const isActive = computed(() => ['active', 'trialing'].includes(props.subscription?.status))
const isCanceled = computed(() => props.subscription?.status === 'canceled')

const statusText = computed(() => {
  if (isSuperAdmin.value) return 'Acceso completo'
  if (isTrialing.value) return 'Periodo de prueba'
  if (isCanceled.value) return 'Cancelado'
  if (isActive.value) return 'Activo'
  return 'Inactivo'
})

const daysRemaining = computed(() => {
  if (!props.subscription?.trial_ends_at) return 0
  const trialEnd = new Date(props.subscription.trial_ends_at)
  const now = new Date()
  return Math.max(0, Math.ceil((trialEnd - now) / (1000 * 60 * 60 * 24)))
})

const camerasUsed = computed(() => props.usage?.cameras || 0)
const camerasLimit = computed(() => {
  const limit = props.plan?.limits?.max_cameras
  return limit === -1 ? '∞' : (limit || 1)
})
const cameraUsagePercent = computed(() => {
  if (camerasLimit.value === '∞') return 0
  return Math.min(100, (camerasUsed.value / camerasLimit.value) * 100)
})

const apiUsed = computed(() => props.usage?.api_calls || 0)
const apiLimit = computed(() => {
  const limit = props.plan?.limits?.api_calls_per_day
  return limit === -1 ? '∞' : (limit || 10)
})
const apiUsagePercent = computed(() => {
  if (apiLimit.value === '∞') return 0
  return Math.min(100, (apiUsed.value / apiLimit.value) * 100)
})

const canUpgrade = computed(() => {
  if (isSuperAdmin.value) return false
  return props.plan?.slug !== 'enterprise'
})

const bannerClass = computed(() => {
  if (isSuperAdmin.value) return 'superadmin'
  if (isCanceled.value) return 'canceled'
  if (isTrialing.value) return 'trialing'
  return props.plan?.slug || 'free'
})
</script>

<style scoped>
.subscription-banner {
  background: rgba(15, 23, 42, 0.8);
  backdrop-filter: blur(12px);
  border-radius: 12px;
  border: 1px solid rgba(99, 102, 241, 0.2);
  overflow: hidden;
}

.banner-content {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 12px 20px;
}

/* Plan Info */
.plan-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.plan-icon {
  font-size: 1.8rem;
}

.plan-details {
  display: flex;
  flex-direction: column;
}

.plan-name {
  font-weight: 600;
  color: #e2e8f0;
  font-size: 1rem;
}

.plan-status {
  font-size: 0.75rem;
  color: #64748b;
}

/* Usage Summary */
.usage-summary {
  display: flex;
  gap: 20px;
  flex: 1;
}

.usage-item {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 150px;
}

.usage-label {
  font-size: 0.75rem;
  color: #94a3b8;
  min-width: 50px;
}

.usage-bar {
  flex: 1;
  height: 6px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 3px;
  overflow: hidden;
  min-width: 60px;
}

.usage-fill {
  height: 100%;
  background: linear-gradient(90deg, #6366f1, #8b5cf6);
  border-radius: 3px;
  transition: width 0.3s ease;
}

.usage-item.warning .usage-fill {
  background: linear-gradient(90deg, #f59e0b, #ef4444);
}

.usage-text {
  font-size: 0.75rem;
  color: #e2e8f0;
  font-weight: 500;
  min-width: 45px;
  text-align: right;
}

/* SuperAdmin Badge */
.superadmin-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  background: linear-gradient(135deg, rgba(251, 191, 36, 0.2), rgba(245, 158, 11, 0.2));
  padding: 8px 16px;
  border-radius: 20px;
  border: 1px solid rgba(251, 191, 36, 0.3);
}

.badge-icon {
  font-size: 1rem;
}

.badge-text {
  font-size: 0.8rem;
  color: #fcd34d;
  font-weight: 600;
}

/* Actions */
.banner-actions {
  display: flex;
  gap: 8px;
}

.btn-upgrade {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  border: none;
  border-radius: 8px;
  color: white;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-upgrade:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4);
}

.btn-manage {
  padding: 8px 16px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  color: #94a3b8;
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-manage:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #e2e8f0;
}

/* Trial Warning */
.trial-warning {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 8px 20px;
  background: rgba(245, 158, 11, 0.15);
  border-top: 1px solid rgba(245, 158, 11, 0.2);
  font-size: 0.85rem;
  color: #fcd34d;
}

.warning-icon {
  animation: pulse-icon 2s ease-in-out infinite;
}

@keyframes pulse-icon {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.btn-activate {
  padding: 4px 12px;
  background: rgba(245, 158, 11, 0.3);
  border: 1px solid rgba(245, 158, 11, 0.5);
  border-radius: 6px;
  color: #fcd34d;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-activate:hover {
  background: rgba(245, 158, 11, 0.5);
}

/* Theme variations */
.subscription-banner.superadmin {
  border-color: rgba(251, 191, 36, 0.3);
  background: linear-gradient(135deg, rgba(15, 23, 42, 0.9), rgba(251, 191, 36, 0.1));
}

.subscription-banner.pro {
  border-color: rgba(99, 102, 241, 0.3);
}

.subscription-banner.enterprise {
  border-color: rgba(139, 92, 246, 0.3);
  background: linear-gradient(135deg, rgba(15, 23, 42, 0.9), rgba(139, 92, 246, 0.1));
}

.subscription-banner.canceled {
  border-color: rgba(239, 68, 68, 0.3);
  opacity: 0.8;
}

.subscription-banner.trialing {
  border-color: rgba(34, 197, 94, 0.3);
}

/* Responsive */
@media (max-width: 768px) {
  .banner-content {
    flex-wrap: wrap;
    gap: 12px;
  }

  .usage-summary {
    flex-direction: column;
    gap: 8px;
    width: 100%;
  }

  .usage-item {
    width: 100%;
  }
}
</style>
