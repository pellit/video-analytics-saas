<script setup>
import { ref, onMounted, computed } from 'vue'
import NavBar from './NavBar.vue'

const props = defineProps(['token', 'user'])
const emit = defineEmits(['logout', 'navigate'])

const stats = ref(null)
const apiStats = ref(null)
const apiKeys = ref([])
const isLoading = ref(true)
const showApiSection = ref(true)
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

onMounted(async () => {
  try {
    // Cargar stats generales y API stats en paralelo
    const [statsRes, apiRes, keysRes] = await Promise.all([
      fetch(`${API_URL}/admin/stats`, {
        headers: { 'Authorization': `Bearer ${props.token}`, 'Accept': 'application/json' }
      }),
      fetch(`${API_URL}/admin/api/overview`, {
        headers: { 'Authorization': `Bearer ${props.token}`, 'Accept': 'application/json' }
      }),
      fetch(`${API_URL}/admin/api/keys`, {
        headers: { 'Authorization': `Bearer ${props.token}`, 'Accept': 'application/json' }
      })
    ])
    
    if (statsRes.ok) stats.value = await statsRes.json()
    if (apiRes.ok) apiStats.value = await apiRes.json()
    if (keysRes.ok) {
      const keysData = await keysRes.json()
      apiKeys.value = keysData.keys || []
    }
  } catch (e) {
    console.error('Error loading stats:', e)
  } finally {
    isLoading.value = false
  }
})

const toggleApiKey = async (keyId) => {
  try {
    const res = await fetch(`${API_URL}/admin/api/keys/${keyId}/toggle`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${props.token}`, 'Accept': 'application/json' }
    })
    if (res.ok) {
      const updated = await res.json()
      const idx = apiKeys.value.findIndex(k => k.id === keyId)
      if (idx !== -1) apiKeys.value[idx] = updated.key
    }
  } catch (e) {
    console.error('Error toggling API key:', e)
  }
}

const formatNumber = (num) => {
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M'
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K'
  return num?.toString() || '0'
}

const navNotifications = computed(() => [])
</script>

<template>
  <div class="admin-layout">
    <!-- NavBar Component -->
    <NavBar 
      :user="user" 
      :notifications="navNotifications"
      :cameras-online="stats?.metrics?.cameras || 0"
      current-view="admin"
      @logout="emit('logout')"
      @navigate="(view) => emit('navigate', view)"
    />

    <main class="admin-content">
      <!-- Loading State -->
      <div v-if="isLoading" class="loading-state">
        <div class="spinner"></div>
        <p>Cargando estadísticas...</p>
      </div>

      <!-- Admin Panel -->
      <div v-else-if="stats" class="admin-panel">
        <header class="panel-header">
          <div class="header-info">
            <h1>🛡️ Panel de Administración</h1>
            <p class="subtitle">Gestión global del sistema</p>
          </div>
        </header>

        <!-- Stats Grid -->
        <div class="stats-grid">
          <div class="stat-card users">
            <div class="stat-icon">👥</div>
            <div class="stat-info">
              <span class="stat-value">{{ stats.metrics.users }}</span>
              <span class="stat-label">Usuarios Registrados</span>
            </div>
          </div>
          <div class="stat-card cameras">
            <div class="stat-icon">📹</div>
            <div class="stat-info">
              <span class="stat-value">{{ stats.metrics.cameras }}</span>
              <span class="stat-label">Cámaras Totales</span>
            </div>
          </div>
          <div class="stat-card alerts">
            <div class="stat-icon">🔔</div>
            <div class="stat-info">
              <span class="stat-value">{{ stats.metrics.alerts || 0 }}</span>
              <span class="stat-label">Alertas Activas</span>
            </div>
          </div>
          <div class="stat-card detections">
            <div class="stat-icon">🎯</div>
            <div class="stat-info">
              <span class="stat-value">{{ stats.metrics.detections || 0 }}</span>
              <span class="stat-label">Detecciones Hoy</span>
            </div>
          </div>
        </div>

        <!-- Recent Users Section -->
        <section class="section">
          <h2>👤 Usuarios Recientes</h2>
          <div class="users-list">
            <div v-for="u in stats.recent_users" :key="u.id" class="user-item">
              <div class="user-avatar">{{ u.name?.charAt(0)?.toUpperCase() || '?' }}</div>
              <div class="user-info">
                <span class="user-name">{{ u.name }}</span>
                <span class="user-email">{{ u.email }}</span>
              </div>
              <span class="user-role" :class="u.role">{{ u.role || 'user' }}</span>
            </div>
            <div v-if="!stats.recent_users?.length" class="empty-state">
              <p>No hay usuarios recientes</p>
            </div>
          </div>
        </section>

        <!-- External API Usage Section -->
        <section class="section api-section">
          <div class="section-header">
            <h2>🔌 API Externa - Uso de Terceros</h2>
            <button class="btn-toggle" @click="showApiSection = !showApiSection">
              {{ showApiSection ? '▼' : '▶' }}
            </button>
          </div>
          
          <div v-if="showApiSection" class="api-content">
            <!-- API Stats Overview -->
            <div class="api-stats-grid" v-if="apiStats">
              <div class="api-stat-card">
                <div class="api-stat-icon">🔑</div>
                <div class="api-stat-info">
                  <span class="api-stat-value">{{ apiStats.total_keys || 0 }}</span>
                  <span class="api-stat-label">API Keys Activas</span>
                </div>
              </div>
              <div class="api-stat-card">
                <div class="api-stat-icon">📊</div>
                <div class="api-stat-info">
                  <span class="api-stat-value">{{ formatNumber(apiStats.total_requests || 0) }}</span>
                  <span class="api-stat-label">Total Requests</span>
                </div>
              </div>
              <div class="api-stat-card">
                <div class="api-stat-icon">📈</div>
                <div class="api-stat-info">
                  <span class="api-stat-value">{{ formatNumber(apiStats.today_requests || 0) }}</span>
                  <span class="api-stat-label">Hoy</span>
                </div>
              </div>
              <div class="api-stat-card">
                <div class="api-stat-icon">🖼️</div>
                <div class="api-stat-info">
                  <span class="api-stat-value">{{ formatNumber(apiStats.today_frames || 0) }}</span>
                  <span class="api-stat-label">Frames Hoy</span>
                </div>
              </div>
            </div>

            <!-- API Keys List -->
            <div class="api-keys-section" v-if="apiKeys.length">
              <h3>🔐 API Keys Registradas</h3>
              <div class="api-keys-list">
                <div v-for="key in apiKeys" :key="key.id" class="api-key-item" :class="{ inactive: !key.is_active }">
                  <div class="key-info">
                    <div class="key-header">
                      <span class="key-name">{{ key.name }}</span>
                      <span class="key-status" :class="key.is_active ? 'active' : 'inactive'">
                        {{ key.is_active ? 'Activa' : 'Inactiva' }}
                      </span>
                    </div>
                    <span class="key-user">👤 {{ key.user?.name || key.user?.email || 'Usuario desconocido' }}</span>
                    <div class="key-meta">
                      <span>📊 {{ formatNumber(key.request_count || 0) }} requests</span>
                      <span>⏱️ Límite: {{ formatNumber(key.rate_limit) }}/día</span>
                    </div>
                  </div>
                  <button 
                    class="btn-toggle-key" 
                    :class="key.is_active ? 'deactivate' : 'activate'"
                    @click="toggleApiKey(key.id)"
                  >
                    {{ key.is_active ? 'Desactivar' : 'Activar' }}
                  </button>
                </div>
              </div>
            </div>

            <!-- Empty State -->
            <div v-else class="empty-api-state">
              <span class="empty-icon">🔌</span>
              <p>No hay API keys registradas</p>
              <p class="empty-hint">Las apps de terceros pueden solicitar acceso a la API para enviar videos a analizar</p>
            </div>
          </div>
        </section>
      </div>

      <!-- Error State -->
      <div v-else class="error-state">
        <span class="error-icon">⚠️</span>
        <p>No se pudieron cargar las estadísticas</p>
        <button @click="$router.go(0)" class="btn-retry">Reintentar</button>
      </div>
    </main>
  </div>
</template>

<style scoped>
.admin-layout {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: #0d1117;
}

.admin-content {
  flex: 1;
  padding: 2rem;
  margin-top: 4rem;
  overflow-y: auto;
}

/* Loading State */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 50vh;
  color: #8b949e;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid #30363d;
  border-top-color: #a855f7;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 1rem;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Panel Header */
.panel-header {
  margin-bottom: 2rem;
}

.panel-header h1 {
  font-size: 1.75rem;
  font-weight: 700;
  color: #e6edf3;
  margin: 0;
}

.panel-header .subtitle {
  color: #8b949e;
  margin: 0.25rem 0 0;
  font-size: 0.95rem;
}

/* Stats Grid */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 1.25rem;
  margin-bottom: 2rem;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1.25rem;
  background: #161b22;
  border-radius: 0.75rem;
  border: 1px solid #30363d;
  transition: all 0.2s ease;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
}

.stat-icon {
  font-size: 2rem;
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 0.75rem;
}

.stat-card.users .stat-icon {
  background: linear-gradient(135deg, rgba(168, 85, 247, 0.2), rgba(139, 92, 246, 0.1));
}

.stat-card.cameras .stat-icon {
  background: linear-gradient(135deg, rgba(31, 111, 235, 0.2), rgba(59, 130, 246, 0.1));
}

.stat-card.alerts .stat-icon {
  background: linear-gradient(135deg, rgba(248, 81, 73, 0.2), rgba(239, 68, 68, 0.1));
}

.stat-card.detections .stat-icon {
  background: linear-gradient(135deg, rgba(35, 134, 54, 0.2), rgba(34, 197, 94, 0.1));
}

.stat-info {
  display: flex;
  flex-direction: column;
}

.stat-value {
  font-size: 1.75rem;
  font-weight: 700;
  color: #e6edf3;
  line-height: 1;
}

.stat-label {
  font-size: 0.85rem;
  color: #8b949e;
  margin-top: 0.25rem;
}

/* Section */
.section {
  background: #161b22;
  border-radius: 0.75rem;
  border: 1px solid #30363d;
  padding: 1.25rem;
  margin-bottom: 1.5rem;
}

.section h2 {
  font-size: 1.1rem;
  font-weight: 600;
  color: #e6edf3;
  margin: 0 0 1rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid #30363d;
}

/* Users List */
.users-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.user-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem;
  background: #21262d;
  border-radius: 0.5rem;
  transition: background 0.15s ease;
}

.user-item:hover {
  background: #30363d;
}

.user-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, #1f6feb, #a855f7);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  color: white;
  font-size: 1rem;
}

.user-info {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.user-name {
  font-weight: 500;
  color: #e6edf3;
}

.user-email {
  font-size: 0.85rem;
  color: #8b949e;
}

.user-role {
  padding: 0.25rem 0.75rem;
  border-radius: 2rem;
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: capitalize;
  background: #21262d;
  color: #8b949e;
  border: 1px solid #30363d;
}

.user-role.superadmin {
  background: linear-gradient(135deg, rgba(168, 85, 247, 0.2), rgba(139, 92, 246, 0.1));
  color: #a78bfa;
  border-color: rgba(168, 85, 247, 0.3);
}

.user-role.admin {
  background: linear-gradient(135deg, rgba(31, 111, 235, 0.2), rgba(59, 130, 246, 0.1));
  color: #60a5fa;
  border-color: rgba(31, 111, 235, 0.3);
}

/* Empty State */
.empty-state {
  text-align: center;
  padding: 2rem;
  color: #8b949e;
}

/* Error State */
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 50vh;
  color: #8b949e;
}

.error-icon {
  font-size: 3rem;
  margin-bottom: 1rem;
}

.btn-retry {
  margin-top: 1rem;
  padding: 0.5rem 1.5rem;
  background: linear-gradient(135deg, #1f6feb, #a855f7);
  color: white;
  border: none;
  border-radius: 0.5rem;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s ease;
}

.btn-retry:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(31, 111, 235, 0.3);
}

/* Responsive */
@media (max-width: 768px) {
  .admin-content {
    padding: 1rem;
  }
  
  .panel-header h1 {
    font-size: 1.4rem;
  }
  
  .stats-grid {
    grid-template-columns: 1fr;
  }
  
  .stat-card {
    padding: 1rem;
  }
  
  .stat-icon {
    width: 48px;
    height: 48px;
    font-size: 1.5rem;
  }
  
  .stat-value {
    font-size: 1.5rem;
  }
  
  .user-item {
    flex-wrap: wrap;
  }
  
  .user-role {
    margin-left: auto;
  }
}

@media (max-width: 480px) {
  .admin-content {
    margin-top: 3.5rem;
    padding: 0.75rem;
  }
  
  .panel-header h1 {
    font-size: 1.2rem;
  }
  
  .section {
    padding: 1rem;
  }
  
  .section h2 {
    font-size: 1rem;
  }
}

/* API Section Styles */
.api-section {
  margin-top: 1.5rem;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid #30363d;
  margin-bottom: 1rem;
}

.section-header h2 {
  margin: 0;
  padding: 0;
  border: none;
}

.btn-toggle {
  background: transparent;
  border: none;
  color: #8b949e;
  cursor: pointer;
  padding: 0.25rem 0.5rem;
  font-size: 0.85rem;
  transition: color 0.15s;
}

.btn-toggle:hover {
  color: #e6edf3;
}

.api-stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.api-stat-card {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
  background: #21262d;
  border-radius: 0.5rem;
  border: 1px solid #30363d;
}

.api-stat-icon {
  font-size: 1.5rem;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, rgba(14, 165, 233, 0.2), rgba(6, 182, 212, 0.1));
  border-radius: 0.5rem;
}

.api-stat-info {
  display: flex;
  flex-direction: column;
}

.api-stat-value {
  font-size: 1.25rem;
  font-weight: 700;
  color: #e6edf3;
  line-height: 1;
}

.api-stat-label {
  font-size: 0.75rem;
  color: #8b949e;
  margin-top: 0.25rem;
}

.api-keys-section h3 {
  font-size: 1rem;
  font-weight: 600;
  color: #e6edf3;
  margin: 0 0 0.75rem;
}

.api-keys-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.api-key-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem;
  background: #21262d;
  border-radius: 0.5rem;
  border: 1px solid #30363d;
  transition: all 0.15s ease;
}

.api-key-item:hover {
  background: #30363d;
}

.api-key-item.inactive {
  opacity: 0.6;
}

.key-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.key-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.key-name {
  font-weight: 600;
  color: #e6edf3;
}

.key-status {
  padding: 0.15rem 0.5rem;
  border-radius: 2rem;
  font-size: 0.7rem;
  font-weight: 500;
}

.key-status.active {
  background: rgba(34, 197, 94, 0.2);
  color: #4ade80;
  border: 1px solid rgba(34, 197, 94, 0.3);
}

.key-status.inactive {
  background: rgba(239, 68, 68, 0.2);
  color: #f87171;
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.key-user {
  font-size: 0.85rem;
  color: #8b949e;
}

.key-meta {
  display: flex;
  gap: 1rem;
  font-size: 0.75rem;
  color: #6e7681;
}

.btn-toggle-key {
  padding: 0.4rem 0.75rem;
  border-radius: 0.375rem;
  font-size: 0.75rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  border: none;
}

.btn-toggle-key.activate {
  background: rgba(34, 197, 94, 0.2);
  color: #4ade80;
}

.btn-toggle-key.activate:hover {
  background: rgba(34, 197, 94, 0.3);
}

.btn-toggle-key.deactivate {
  background: rgba(239, 68, 68, 0.2);
  color: #f87171;
}

.btn-toggle-key.deactivate:hover {
  background: rgba(239, 68, 68, 0.3);
}

.empty-api-state {
  text-align: center;
  padding: 2rem;
  color: #8b949e;
}

.empty-icon {
  font-size: 2.5rem;
  display: block;
  margin-bottom: 0.75rem;
}

.empty-hint {
  font-size: 0.85rem;
  color: #6e7681;
  margin-top: 0.5rem;
}

/* Responsive for API Section */
@media (max-width: 768px) {
  .api-stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  
  .api-key-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.75rem;
  }
  
  .btn-toggle-key {
    width: 100%;
  }
  
  .key-meta {
    flex-wrap: wrap;
    gap: 0.5rem;
  }
}

@media (max-width: 480px) {
  .api-stats-grid {
    grid-template-columns: 1fr;
  }
  
  .api-stat-card {
    padding: 0.75rem;
  }
}
</style>