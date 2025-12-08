<template>
  <div 
    class="glass-panel" 
    :class="[sizeClass, { 'expanded': isExpanded, 'minimized': isMinimized }]"
    :style="customStyle"
  >
    <!-- Header -->
    <div class="glass-header" @dblclick="toggleExpand">
      <div class="header-left">
        <span class="panel-icon">{{ icon }}</span>
        <h3 class="panel-title">{{ title }}</h3>
        <span v-if="badge" class="panel-badge" :class="badgeType">{{ badge }}</span>
      </div>
      <div class="header-controls">
        <button 
          v-if="showMinimize" 
          class="control-btn" 
          @click="toggleMinimize"
          :title="isMinimized ? 'Expandir' : 'Minimizar'"
        >
          {{ isMinimized ? '□' : '─' }}
        </button>
        <button 
          v-if="showExpand"
          class="control-btn"
          @click="toggleExpand"
          :title="isExpanded ? 'Contraer' : 'Expandir'"
        >
          {{ isExpanded ? '⤡' : '⤢' }}
        </button>
        <button 
          v-if="showClose"
          class="control-btn close-btn"
          @click="$emit('close')"
          title="Cerrar"
        >
          ×
        </button>
      </div>
    </div>

    <!-- Content -->
    <div class="glass-content" v-show="!isMinimized">
      <slot></slot>
    </div>

    <!-- Footer (optional) -->
    <div class="glass-footer" v-if="$slots.footer" v-show="!isMinimized">
      <slot name="footer"></slot>
    </div>

    <!-- Alert indicator -->
    <div v-if="alertLevel" class="alert-indicator" :class="alertLevel">
      <span class="pulse"></span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  title: { type: String, default: 'Panel' },
  icon: { type: String, default: '📊' },
  size: { type: String, default: 'medium' }, // small, medium, large, full
  badge: { type: [String, Number], default: null },
  badgeType: { type: String, default: 'info' }, // info, warning, danger, success
  alertLevel: { type: String, default: null }, // low, medium, high, critical
  showMinimize: { type: Boolean, default: true },
  showExpand: { type: Boolean, default: true },
  showClose: { type: Boolean, default: false },
  customStyle: { type: Object, default: () => ({}) }
})

const emit = defineEmits(['close', 'expand', 'minimize'])

const isExpanded = ref(false)
const isMinimized = ref(false)

const sizeClass = computed(() => `size-${props.size}`)

const toggleExpand = () => {
  isExpanded.value = !isExpanded.value
  isMinimized.value = false
  emit('expand', isExpanded.value)
}

const toggleMinimize = () => {
  isMinimized.value = !isMinimized.value
  isExpanded.value = false
  emit('minimize', isMinimized.value)
}
</script>

<style scoped>
.glass-panel {
  background: rgba(15, 23, 42, 0.75);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 16px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  box-shadow: 
    0 4px 24px rgba(0, 0, 0, 0.3),
    inset 0 1px 0 rgba(255, 255, 255, 0.05);
}

.glass-panel:hover {
  border-color: rgba(99, 102, 241, 0.4);
  transform: translateY(-2px);
  box-shadow: 
    0 8px 32px rgba(99, 102, 241, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.1);
}

/* Sizes */
.size-small {
  min-width: 200px;
  max-height: 300px;
}

.size-medium {
  min-width: 300px;
  max-height: 500px;
}

.size-large {
  min-width: 400px;
  max-height: 700px;
}

.size-full {
  width: 100%;
  height: 100%;
}

/* States */
.expanded {
  position: fixed !important;
  top: 80px !important;
  left: 20px !important;
  right: 20px !important;
  bottom: 20px !important;
  width: auto !important;
  height: auto !important;
  max-height: none !important;
  z-index: 1000;
}

.minimized {
  max-height: 48px !important;
  min-height: 48px !important;
}

/* Header */
.glass-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  background: rgba(0, 0, 0, 0.2);
  cursor: default;
  user-select: none;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.panel-icon {
  font-size: 1.2rem;
}

.panel-title {
  margin: 0;
  font-size: 0.9rem;
  font-weight: 600;
  color: #e2e8f0;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.panel-badge {
  font-size: 0.7rem;
  padding: 2px 8px;
  border-radius: 12px;
  font-weight: 600;
}

.panel-badge.info {
  background: rgba(59, 130, 246, 0.3);
  color: #93c5fd;
}

.panel-badge.warning {
  background: rgba(245, 158, 11, 0.3);
  color: #fcd34d;
}

.panel-badge.danger {
  background: rgba(239, 68, 68, 0.3);
  color: #fca5a5;
}

.panel-badge.success {
  background: rgba(34, 197, 94, 0.3);
  color: #86efac;
}

/* Header Controls */
.header-controls {
  display: flex;
  gap: 4px;
}

.control-btn {
  background: rgba(255, 255, 255, 0.05);
  border: none;
  color: #94a3b8;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.control-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #e2e8f0;
}

.close-btn:hover {
  background: rgba(239, 68, 68, 0.3);
  color: #fca5a5;
}

/* Content */
.glass-content {
  flex: 1;
  padding: 16px;
  overflow-y: auto;
  overflow-x: hidden;
}

.glass-content::-webkit-scrollbar {
  width: 6px;
}

.glass-content::-webkit-scrollbar-track {
  background: rgba(0, 0, 0, 0.2);
}

.glass-content::-webkit-scrollbar-thumb {
  background: rgba(99, 102, 241, 0.3);
  border-radius: 3px;
}

.glass-content::-webkit-scrollbar-thumb:hover {
  background: rgba(99, 102, 241, 0.5);
}

/* Footer */
.glass-footer {
  padding: 12px 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  background: rgba(0, 0, 0, 0.15);
}

/* Alert Indicator */
.alert-indicator {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.alert-indicator.low {
  background: #3b82f6;
}

.alert-indicator.medium {
  background: #f59e0b;
}

.alert-indicator.high {
  background: #f97316;
}

.alert-indicator.critical {
  background: #ef4444;
}

.pulse {
  position: absolute;
  inset: -4px;
  border-radius: 50%;
  animation: pulse 2s ease-in-out infinite;
}

.alert-indicator.low .pulse {
  background: rgba(59, 130, 246, 0.4);
}

.alert-indicator.medium .pulse {
  background: rgba(245, 158, 11, 0.4);
}

.alert-indicator.high .pulse {
  background: rgba(249, 115, 22, 0.4);
}

.alert-indicator.critical .pulse {
  background: rgba(239, 68, 68, 0.5);
  animation: pulse-critical 1s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.5); opacity: 0; }
}

@keyframes pulse-critical {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(2); opacity: 0; }
}
</style>
