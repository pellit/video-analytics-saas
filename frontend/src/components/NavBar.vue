<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  user: {
    type: Object,
    default: () => ({ name: 'Usuario', email: 'user@email.com', role: 'user' })
  },
  notifications: {
    type: Array,
    default: () => []
  },
  camerasOnline: {
    type: Number,
    default: 0
  },
  currentView: {
    type: String,
    default: 'dashboard'
  }
})

const emit = defineEmits(['logout', 'openProfile', 'openSettings', 'navigate'])

// Menu state
const isMenuOpen = ref(false)
const isNotificationsOpen = ref(false)
const isMobileMenuOpen = ref(false)

// Computed
const unreadCount = computed(() => props.notifications.filter(n => !n.read).length)
const userInitials = computed(() => {
  if (!props.user?.name) return '?'
  return props.user.name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
})

const roleLabel = computed(() => {
  const roles = {
    superadmin: 'Super Admin',
    admin: 'Administrador',
    user: 'Usuario'
  }
  return roles[props.user?.role] || 'Usuario'
})

const roleIcon = computed(() => {
  const icons = {
    superadmin: '👑',
    admin: '⭐',
    user: '👤'
  }
  return icons[props.user?.role] || '👤'
})

const isSuperAdmin = computed(() => props.user?.role === 'superadmin')

// Methods
const toggleMenu = () => {
  isMenuOpen.value = !isMenuOpen.value
  if (isMenuOpen.value) isNotificationsOpen.value = false
}

const toggleNotifications = () => {
  isNotificationsOpen.value = !isNotificationsOpen.value
  if (isNotificationsOpen.value) isMenuOpen.value = false
}

const toggleMobileMenu = () => {
  isMobileMenuOpen.value = !isMobileMenuOpen.value
}

const closeAll = () => {
  isMenuOpen.value = false
  isNotificationsOpen.value = false
  isMobileMenuOpen.value = false
}

const handleLogout = () => {
  closeAll()
  emit('logout')
}

const handleOpenProfile = () => {
  closeAll()
  emit('openProfile')
}

const handleOpenSettings = () => {
  closeAll()
  emit('openSettings')
}

const navigateTo = (view) => {
  closeAll()
  emit('navigate', view)
}


// Close menu when clicking outside
const handleClickOutside = (e) => {
  const menu = document.querySelector('.user-menu')
  const notifPanel = document.querySelector('.notifications-panel')
  const avatar = document.querySelector('.avatar-btn')
  const notifBtn = document.querySelector('.notif-btn')
  
  if (menu && !menu.contains(e.target) && avatar && !avatar.contains(e.target)) {
    isMenuOpen.value = false
  }
  if (notifPanel && !notifPanel.contains(e.target) && notifBtn && !notifBtn.contains(e.target)) {
    isNotificationsOpen.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>

<template>
  <nav class="navbar">
    <!-- Logo Section -->
    <div class="navbar-brand">
      <div class="logo">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M15 10L19.5528 7.72361C20.2177 7.39116 21 7.87465 21 8.61803V15.382C21 16.1253 20.2177 16.6088 19.5528 16.2764L15 14M5 18H13C14.1046 18 15 17.1046 15 16V8C15 6.89543 14.1046 6 13 6H5C3.89543 6 3 6.89543 3 8V16C3 17.1046 3.89543 18 5 18Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </div>
      <div class="brand-text">
        <span class="brand-name">Video Analytics</span>
        <span class="brand-badge">PRO</span>
      </div>
    </div>

    <!-- Center: Navigation & Status -->
    <div class="navbar-center">
      <nav class="nav-links">
        <button 
          class="nav-link" 
          :class="{ active: currentView === 'dashboard' }"
          @click="navigateTo('dashboard')"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
            <line x1="8" y1="21" x2="16" y2="21"/>
            <line x1="12" y1="17" x2="12" y2="21"/>
          </svg>
          <span>Cámaras</span>
        </button>
        <button 
          v-if="isSuperAdmin"
          class="nav-link" 
          :class="{ active: currentView === 'admin' }"
          @click="navigateTo('admin')"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
          </svg>
          <span>Admin</span>
        </button>
      </nav>
      <div class="status-chip" :class="{ active: camerasOnline > 0 }">
        <span class="status-dot"></span>
        <span class="status-text">{{ camerasOnline }} activa{{ camerasOnline !== 1 ? 's' : '' }}</span>
      </div>
    </div>

    <!-- Mobile Menu Toggle -->
    <button class="mobile-menu-btn" @click="toggleMobileMenu">
      <svg v-if="!isMobileMenuOpen" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="3" y1="6" x2="21" y2="6"/>
        <line x1="3" y1="12" x2="21" y2="12"/>
        <line x1="3" y1="18" x2="21" y2="18"/>
      </svg>
      <svg v-else width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="18" y1="6" x2="6" y2="18"/>
        <line x1="6" y1="6" x2="18" y2="18"/>
      </svg>
    </button>

    <!-- Right Actions -->
    <div class="navbar-actions">
      <!-- Notifications -->
      <button class="action-btn notif-btn" @click.stop="toggleNotifications" title="Notificaciones">
        <span v-if="unreadCount > 0" class="badge">{{ unreadCount > 9 ? '9+' : unreadCount }}</span>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
          <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
        </svg>
      </button>

      <!-- Settings -->
      <button class="action-btn" @click="handleOpenSettings" title="Configuración">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="3"/>
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
        </svg>
      </button>

      <!-- User Menu Trigger -->
      <button class="avatar-btn" @click.stop="toggleMenu">
        <div class="avatar">{{ userInitials }}</div>
        <div class="user-brief">
          <span class="user-name">{{ user?.name?.split(' ')[0] || 'Usuario' }}</span>
          <span class="user-role">{{ roleIcon }} {{ roleLabel }}</span>
        </div>
        <svg class="chevron" :class="{ rotated: isMenuOpen }" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </button>
    </div>

    <!-- Notifications Panel -->
    <Transition name="dropdown">
      <div v-if="isNotificationsOpen" class="notifications-panel">
        <div class="panel-header">
          <h3>🔔 Notificaciones</h3>
          <button v-if="unreadCount > 0" class="link-btn">Marcar leídas</button>
        </div>
        <div class="notifications-list" v-if="notifications.length > 0">
          <div v-for="notif in notifications.slice(0, 5)" :key="notif.id" 
               class="notification-item" :class="{ unread: !notif.read, [notif.type]: true }">
            <div class="notif-icon">
              <svg v-if="notif.type === 'alert'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
              </svg>
              <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>
              </svg>
            </div>
            <div class="notif-body">
              <p>{{ notif.message }}</p>
              <span class="notif-time">{{ notif.time }}</span>
            </div>
          </div>
        </div>
        <div v-else class="empty-state">
          <span class="empty-icon">🔕</span>
          <p>Sin notificaciones</p>
        </div>
      </div>
    </Transition>

    <!-- User Menu -->
    <Transition name="dropdown">
      <div v-if="isMenuOpen" class="user-menu">
        <div class="menu-header">
          <div class="avatar large">{{ userInitials }}</div>
          <div class="menu-user-info">
            <span class="name">{{ user?.name || 'Usuario' }}</span>
            <span class="email">{{ user?.email || '' }}</span>
          </div>
        </div>

        <div class="role-pill">
          <span>{{ roleIcon }}</span>
          <span>{{ roleLabel }}</span>
        </div>

        <div class="menu-section">
          <button class="menu-item" @click="handleOpenProfile">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
              <circle cx="12" cy="7" r="4"/>
            </svg>
            <span>Mi Perfil</span>
          </button>
          <button class="menu-item" @click="handleOpenSettings">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="3"/>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
            </svg>
            <span>Configuración</span>
          </button>
          <button class="menu-item">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/>
              <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>
              <path d="M12 17h.01"/>
            </svg>
            <span>Ayuda</span>
          </button>
        </div>

        <div class="menu-divider"></div>

        <div class="menu-section">
          <button class="menu-item danger" @click="handleLogout">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
              <polyline points="16 17 21 12 16 7"/>
              <line x1="21" y1="12" x2="9" y2="12"/>
            </svg>
            <span>Cerrar Sesión</span>
          </button>
        </div>

        <div class="menu-footer">
          <span>Video Analytics v1.0</span>
        </div>
      </div>
    </Transition>

    <!-- Mobile Menu Overlay -->
    <Transition name="mobile-menu">
      <div v-if="isMobileMenuOpen" class="mobile-menu-overlay" @click="closeAll">
        <div class="mobile-menu" @click.stop>
          <div class="mobile-menu-header">
            <div class="avatar">{{ userInitials }}</div>
            <div class="mobile-user-info">
              <span class="name">{{ user?.name || 'Usuario' }}</span>
              <span class="role">{{ roleIcon }} {{ roleLabel }}</span>
            </div>
          </div>
          
          <nav class="mobile-nav">
            <button 
              class="mobile-nav-item" 
              :class="{ active: currentView === 'dashboard' }"
              @click="navigateTo('dashboard')"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
                <line x1="8" y1="21" x2="16" y2="21"/>
                <line x1="12" y1="17" x2="12" y2="21"/>
              </svg>
              <span>Mis Cámaras</span>
            </button>
            <button 
              v-if="isSuperAdmin"
              class="mobile-nav-item"
              :class="{ active: currentView === 'admin' }"
              @click="navigateTo('admin')"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
              </svg>
              <span>SuperAdmin</span>
            </button>
          </nav>
          
          <div class="mobile-menu-divider"></div>
          
          <div class="mobile-actions">
            <button class="mobile-action-item" @click="handleOpenProfile">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                <circle cx="12" cy="7" r="4"/>
              </svg>
              <span>Mi Perfil</span>
            </button>
            <button class="mobile-action-item" @click="handleOpenSettings">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="3"/>
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
              </svg>
              <span>Configuración</span>
            </button>
            <button class="mobile-action-item danger" @click="handleLogout">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
                <polyline points="16 17 21 12 16 7"/>
                <line x1="21" y1="12" x2="9" y2="12"/>
              </svg>
              <span>Cerrar Sesión</span>
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </nav>
</template>

<style scoped>
.navbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: var(--navbar-height, 4rem);
  padding: 0 1.25rem;
  background: var(--bg-secondary, #161b22);
  border-bottom: 1px solid var(--border-primary, #30363d);
  z-index: 300;
}

/* Brand */
.navbar-brand {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.logo {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.5rem;
  height: 2.5rem;
  background: linear-gradient(135deg, #8543CC 0%, #a855f7 100%);
  border-radius: 0.75rem;
  color: white;
}

.brand-text {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.brand-name {
  font-weight: 600;
  font-size: 1.125rem;
  color: var(--text-primary, #e6edf3);
}

.brand-badge {
  padding: 0.15rem 0.5rem;
  background: linear-gradient(135deg, #d97706 0%, #F4BD50 100%);
  border-radius: 0.375rem;
  font-size: 0.65rem;
  font-weight: 700;
  color: #0d1117;
  letter-spacing: 0.05em;
}

/* Center Status */
.navbar-center {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
}

.status-chip {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 1rem;
  background: var(--bg-elevated, #21262d);
  border: 1px solid var(--border-primary, #30363d);
  border-radius: 9999px;
  font-size: 0.875rem;
  color: var(--text-secondary, #8b949e);
  transition: all 0.2s ease;
}

.status-chip.active {
  background: rgba(63, 185, 80, 0.15);
  border-color: #3fb950;
  color: #3fb950;
}

.status-dot {
  width: 8px;
  height: 8px;
  background: #484f58;
  border-radius: 50%;
  transition: all 0.2s ease;
}

.status-chip.active .status-dot {
  background: #3fb950;
  box-shadow: 0 0 8px #3fb950;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.7; transform: scale(1.1); }
}

/* Actions */
.navbar-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.action-btn {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.5rem;
  height: 2.5rem;
  background: transparent;
  border: 1px solid var(--border-primary, #30363d);
  border-radius: 0.5rem;
  color: var(--text-secondary, #8b949e);
  cursor: pointer;
  transition: all 0.2s ease;
}

.action-btn:hover {
  background: var(--bg-elevated, #21262d);
  border-color: #8543CC;
  color: #8543CC;
}

.action-btn .badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  background: #f85149;
  border-radius: 9999px;
  font-size: 0.65rem;
  font-weight: 700;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* Avatar Button */
.avatar-btn {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.35rem 0.75rem 0.35rem 0.35rem;
  background: var(--bg-elevated, #21262d);
  border: 1px solid var(--border-primary, #30363d);
  border-radius: 9999px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.avatar-btn:hover {
  border-color: #8543CC;
  box-shadow: 0 0 20px rgba(133, 67, 204, 0.3);
}

.avatar {
  width: 2rem;
  height: 2rem;
  background: linear-gradient(135deg, #8543CC 0%, #a855f7 100%);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.875rem;
  font-weight: 600;
  color: white;
}

.avatar.large {
  width: 3rem;
  height: 3rem;
  font-size: 1.125rem;
}

.user-brief {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  text-align: left;
}

.user-brief .user-name {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-primary, #e6edf3);
  line-height: 1.2;
}

.user-brief .user-role {
  font-size: 0.7rem;
  color: var(--text-secondary, #8b949e);
}

.chevron {
  color: var(--text-secondary, #8b949e);
  transition: transform 0.2s ease;
}

.chevron.rotated {
  transform: rotate(180deg);
}

/* Dropdown Panels */
.notifications-panel,
.user-menu {
  position: absolute;
  top: calc(4rem + 0.5rem);
  right: 1rem;
  background: var(--bg-secondary, #161b22);
  border: 1px solid var(--border-primary, #30363d);
  border-radius: 1rem;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.6);
  overflow: hidden;
  z-index: 100;
}

.notifications-panel {
  width: 360px;
  max-height: 480px;
}

.user-menu {
  width: 280px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--border-primary, #30363d);
}

.panel-header h3 {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary, #e6edf3);
}

.link-btn {
  background: none;
  border: none;
  color: #8543CC;
  font-size: 0.875rem;
  cursor: pointer;
  transition: color 0.15s ease;
}

.link-btn:hover {
  color: #a855f7;
  text-decoration: underline;
}

/* Notifications */
.notifications-list {
  max-height: 360px;
  overflow-y: auto;
}

.notification-item {
  display: flex;
  gap: 0.75rem;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--border-primary, #30363d);
  transition: background 0.15s ease;
}

.notification-item:hover {
  background: var(--bg-elevated, #21262d);
}

.notification-item.unread {
  background: rgba(133, 67, 204, 0.05);
  border-left: 3px solid #8543CC;
}

.notification-item.alert .notif-icon {
  background: rgba(240, 136, 62, 0.15);
  color: #f0883e;
}

.notification-item.info .notif-icon {
  background: rgba(88, 166, 255, 0.15);
  color: #58a6ff;
}

.notif-icon {
  width: 2.25rem;
  height: 2.25rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-elevated, #21262d);
  border-radius: 0.5rem;
  flex-shrink: 0;
}

.notif-body {
  flex: 1;
  min-width: 0;
}

.notif-body p {
  font-size: 0.875rem;
  color: var(--text-primary, #e6edf3);
  margin-bottom: 0.25rem;
  line-height: 1.4;
}

.notif-time {
  font-size: 0.75rem;
  color: var(--text-secondary, #8b949e);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 2.5rem 1rem;
  color: #484f58;
}

.empty-icon {
  font-size: 2.5rem;
  margin-bottom: 0.5rem;
  opacity: 0.5;
}

.empty-state p {
  font-size: 0.875rem;
}

/* User Menu */
.menu-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1.25rem;
  background: #1f2336;
  border-bottom: 1px solid var(--border-primary, #30363d);
}

.menu-user-info {
  flex: 1;
  min-width: 0;
}

.menu-user-info .name {
  display: block;
  font-weight: 600;
  color: var(--text-primary, #e6edf3);
  font-size: 1rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.menu-user-info .email {
  display: block;
  font-size: 0.75rem;
  color: var(--text-secondary, #8b949e);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.role-pill {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  margin: 0.75rem 1rem;
  padding: 0.5rem;
  background: rgba(133, 67, 204, 0.3);
  border: 1px solid #42375d;
  border-radius: 0.5rem;
  font-size: 0.875rem;
  font-weight: 500;
  color: #a855f7;
}

.menu-section {
  padding: 0.5rem;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  width: 100%;
  padding: 0.65rem 0.75rem;
  background: transparent;
  border: none;
  border-radius: 0.5rem;
  font-size: 0.875rem;
  color: var(--text-secondary, #8b949e);
  cursor: pointer;
  transition: all 0.15s ease;
  text-align: left;
}

.menu-item:hover {
  background: var(--bg-elevated, #21262d);
  color: var(--text-primary, #e6edf3);
}

.menu-item.danger {
  color: #f85149;
}

.menu-item.danger:hover {
  background: rgba(248, 81, 73, 0.15);
}

.menu-divider {
  height: 1px;
  background: var(--border-primary, #30363d);
  margin: 0.25rem 1rem;
}

.menu-footer {
  padding: 0.75rem 1rem;
  border-top: 1px solid var(--border-primary, #30363d);
  font-size: 0.7rem;
  color: #484f58;
  text-align: center;
}

/* Transitions */
.dropdown-enter-active {
  animation: dropdownIn 0.2s ease-out;
}

.dropdown-leave-active {
  animation: dropdownOut 0.15s ease-in;
}

@keyframes dropdownIn {
  from {
    opacity: 0;
    transform: translateY(-8px) scale(0.96);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes dropdownOut {
  from {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
  to {
    opacity: 0;
    transform: translateY(-8px) scale(0.96);
  }
}

/* Navigation Links */
.nav-links {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.nav-link {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background: transparent;
  border: none;
  border-radius: 0.5rem;
  color: var(--text-secondary, #8b949e);
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.nav-link:hover {
  background: var(--bg-elevated, #21262d);
  color: var(--text-primary, #e6edf3);
}

.nav-link.active {
  background: linear-gradient(135deg, rgba(31, 111, 235, 0.15), rgba(168, 85, 247, 0.15));
  color: #a78bfa;
}

.nav-link.active svg {
  color: #a78bfa;
}

/* Mobile Menu Button */
.mobile-menu-btn {
  display: none;
  align-items: center;
  justify-content: center;
  width: 2.5rem;
  height: 2.5rem;
  background: transparent;
  border: none;
  border-radius: 0.5rem;
  color: var(--text-secondary, #8b949e);
  cursor: pointer;
  transition: all 0.15s ease;
}

.mobile-menu-btn:hover {
  background: var(--bg-elevated, #21262d);
  color: var(--text-primary, #e6edf3);
}

/* Mobile Menu Overlay */
.mobile-menu-overlay {
  position: fixed;
  top: var(--navbar-height, 4rem);
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  z-index: 250;
}

.mobile-menu {
  position: absolute;
  top: 0;
  right: 0;
  width: 280px;
  max-width: 85vw;
  height: 100%;
  background: var(--bg-secondary, #161b22);
  border-left: 1px solid var(--border-primary, #30363d);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.mobile-menu-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1.25rem;
  background: var(--bg-elevated, #21262d);
  border-bottom: 1px solid var(--border-primary, #30363d);
}

.mobile-user-info {
  display: flex;
  flex-direction: column;
}

.mobile-user-info .name {
  font-weight: 600;
  color: var(--text-primary, #e6edf3);
}

.mobile-user-info .role {
  font-size: 0.8rem;
  color: var(--text-secondary, #8b949e);
}

.mobile-nav {
  display: flex;
  flex-direction: column;
  padding: 0.75rem;
}

.mobile-nav-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.875rem 1rem;
  background: transparent;
  border: none;
  border-radius: 0.5rem;
  color: var(--text-secondary, #8b949e);
  font-size: 0.95rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  text-align: left;
}

.mobile-nav-item:hover {
  background: var(--bg-elevated, #21262d);
  color: var(--text-primary, #e6edf3);
}

.mobile-nav-item.active {
  background: linear-gradient(135deg, rgba(31, 111, 235, 0.15), rgba(168, 85, 247, 0.15));
  color: #a78bfa;
}

.mobile-menu-divider {
  height: 1px;
  background: var(--border-primary, #30363d);
  margin: 0.5rem 1rem;
}

.mobile-actions {
  display: flex;
  flex-direction: column;
  padding: 0.75rem;
  margin-top: auto;
}

.mobile-action-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.875rem 1rem;
  background: transparent;
  border: none;
  border-radius: 0.5rem;
  color: var(--text-secondary, #8b949e);
  font-size: 0.95rem;
  cursor: pointer;
  transition: all 0.15s ease;
  text-align: left;
}

.mobile-action-item:hover {
  background: var(--bg-elevated, #21262d);
  color: var(--text-primary, #e6edf3);
}

.mobile-action-item.danger {
  color: #f85149;
}

.mobile-action-item.danger:hover {
  background: rgba(248, 81, 73, 0.15);
}

/* Mobile Menu Transitions */
.mobile-menu-enter-active {
  transition: all 0.3s ease;
}

.mobile-menu-leave-active {
  transition: all 0.2s ease;
}

.mobile-menu-enter-active .mobile-menu {
  animation: slideIn 0.3s ease-out;
}

.mobile-menu-leave-active .mobile-menu {
  animation: slideOut 0.2s ease-in;
}

.mobile-menu-enter-from,
.mobile-menu-leave-to {
  opacity: 0;
}

@keyframes slideIn {
  from {
    transform: translateX(100%);
  }
  to {
    transform: translateX(0);
  }
}

@keyframes slideOut {
  from {
    transform: translateX(0);
  }
  to {
    transform: translateX(100%);
  }
}

/* Status Text Responsive */
.status-text {
  white-space: nowrap;
}

/* Responsive */
@media (max-width: 1024px) {
  .nav-link span {
    display: none;
  }
  
  .nav-link {
    padding: 0.5rem;
  }
  
  .status-text {
    display: none;
  }
  
  .status-chip {
    padding: 0.35rem;
    min-width: auto;
  }
  
  .status-chip .status-dot {
    margin: 0;
  }
}

@media (max-width: 768px) {
  .navbar-center {
    display: none;
  }
  
  .navbar-actions {
    display: none;
  }
  
  .mobile-menu-btn {
    display: flex;
  }
  
  .notifications-panel,
  .user-menu {
    display: none;
  }
}

@media (max-width: 480px) {
  .brand-text {
    display: none;
  }
  
  .navbar {
    padding: 0 0.75rem;
  }
}
</style>
