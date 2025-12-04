<template>
  <div class="satellite-panel">
    <!-- Header -->
    <div class="panel-header">
      <h3>🛰️ Zonas Satelitales</h3>
      <button class="btn-add" @click="openAddZoneModal" :disabled="!serviceAvailable">
        <span class="icon">+</span> Nueva Zona
      </button>
    </div>

    <!-- Service Status -->
    <div v-if="!serviceAvailable" class="service-warning">
      <span class="warning-icon">⚠️</span>
      <span>Servicio satelital no configurado. Configura SENTINEL_CLIENT_ID y SENTINEL_CLIENT_SECRET.</span>
    </div>

    <!-- Zones Grid -->
    <div class="zones-grid">
      <div 
        v-for="zone in zones" 
        :key="zone.id" 
        class="zone-card"
        :class="{ 'processing': zone.processing }"
      >
        <!-- Zone Header -->
        <div class="zone-header">
          <h4>{{ zone.name }}</h4>
          <div class="zone-actions">
            <button 
              class="btn-icon btn-analyze" 
              @click="analyzeZone(zone)" 
              :disabled="zone.processing"
              title="Analizar ahora"
            >
              <span v-if="zone.processing" class="spinner"></span>
              <span v-else>🔍</span>
            </button>
            <button class="btn-icon btn-delete" @click="confirmDeleteZone(zone)" title="Eliminar">
              🗑️
            </button>
          </div>
        </div>

        <!-- Zone Preview -->
        <div class="zone-preview">
          <img 
            v-if="zone.last_image_path" 
            :src="getImageUrl(zone.last_image_path)" 
            :alt="zone.name"
            @error="onImageError"
          />
          <div v-else class="no-image">
            <span class="globe-icon">🌍</span>
            <span class="no-image-text">Sin imagen</span>
          </div>
          <!-- Badge de alertas -->
          <div v-if="zone.unread_alerts_count > 0" class="alerts-badge">
            {{ zone.unread_alerts_count }}
          </div>
        </div>

        <!-- Zone Info -->
        <div class="zone-info">
          <div class="info-row">
            <span class="label">Coordenadas:</span>
            <span class="value">{{ formatCoords(zone.latitude, zone.longitude) }}</span>
          </div>
          <div class="info-row">
            <span class="label">Radio:</span>
            <span class="value">{{ zone.radius_km }} km</span>
          </div>
          <div class="info-row">
            <span class="label">Frecuencia:</span>
            <span class="value freq-badge" :class="zone.frequency">{{ zone.frequency }}</span>
          </div>
          <div class="info-row" v-if="zone.last_image_at">
            <span class="label">Última imagen:</span>
            <span class="value time-ago">{{ formatTimeAgo(zone.last_image_at) }}</span>
          </div>
        </div>

        <!-- Detections Summary -->
        <div class="detections-summary" v-if="zone.last_analysis?.detections?.length">
          <span class="detection-count">
            {{ zone.last_analysis.detections.length }} detecciones
          </span>
          <div class="detection-tags">
            <span 
              v-for="(det, idx) in getUniqueDetections(zone.last_analysis.detections).slice(0, 3)" 
              :key="idx"
              class="detection-tag"
            >
              {{ det.class_name }}
            </span>
            <span v-if="getUniqueDetections(zone.last_analysis.detections).length > 3" class="more-tag">
              +{{ getUniqueDetections(zone.last_analysis.detections).length - 3 }}
            </span>
          </div>
        </div>
      </div>

      <!-- Empty State -->
      <div v-if="zones.length === 0 && !loading" class="empty-state">
        <span class="empty-icon">🛰️</span>
        <p>No tienes zonas satelitales configuradas</p>
        <button class="btn-primary" @click="openAddZoneModal" :disabled="!serviceAvailable">
          Crear primera zona
        </button>
      </div>
    </div>

    <!-- Add Zone Modal with Map -->
    <div v-if="showAddZone" class="modal-overlay" @click.self="closeModal">
      <div class="modal-content modal-large">
        <div class="modal-header">
          <h3>🛰️ Nueva Zona Satelital</h3>
          <button class="btn-close" @click="closeModal">✕</button>
        </div>
        
        <form @submit.prevent="createZone" class="zone-form">
          <div class="form-group">
            <label for="zone-name">Nombre de la zona</label>
            <input 
              id="zone-name" 
              v-model="newZone.name" 
              type="text" 
              placeholder="Ej: Campo Norte, Planta Solar, etc." 
              required
            />
          </div>

          <!-- Interactive Map -->
          <div class="form-group">
            <label>📍 Selecciona ubicación en el mapa</label>
            <p class="map-help">Haz clic en el mapa para seleccionar el centro, o usa el botón de rectángulo para dibujar un área.</p>
            <div id="satellite-map" ref="mapContainer" class="map-container"></div>
            <div class="map-controls">
              <button type="button" class="btn-map-tool" :class="{ active: mapMode === 'point' }" @click="setMapMode('point')">
                📍 Punto
              </button>
              <button type="button" class="btn-map-tool" :class="{ active: mapMode === 'rectangle' }" @click="setMapMode('rectangle')">
                ⬜ Rectángulo
              </button>
              <button type="button" class="btn-map-tool" @click="clearMapSelection">
                🗑️ Limpiar
              </button>
              <button type="button" class="btn-map-tool" @click="locateUser">
                🎯 Mi ubicación
              </button>
            </div>
          </div>

          <!-- Coordinates display -->
          <div class="coords-display" v-if="newZone.latitude && newZone.longitude">
            <div class="coord-info">
              <span class="coord-label">Centro:</span>
              <span class="coord-value">{{ formatCoords(newZone.latitude, newZone.longitude) }}</span>
            </div>
            <div class="coord-info" v-if="newZone.bounds">
              <span class="coord-label">Área:</span>
              <span class="coord-value">{{ formatBounds(newZone.bounds) }}</span>
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label for="zone-lat">Latitud (manual)</label>
              <input 
                id="zone-lat" 
                v-model.number="newZone.latitude" 
                type="number" 
                step="0.000001"
                min="-90"
                max="90"
                placeholder="-32.94"
                @change="updateMapFromInputs"
                required
              />
            </div>
            <div class="form-group">
              <label for="zone-lon">Longitud (manual)</label>
              <input 
                id="zone-lon" 
                v-model.number="newZone.longitude"
                type="number"
                step="0.000001"
                min="-180"
                max="180"
                placeholder="-60.63"
                @change="updateMapFromInputs"
                required
              />
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label for="zone-radius">Radio (km)</label>
              <input 
                id="zone-radius" 
                v-model.number="newZone.radius_km" 
                type="number"
                step="0.1"
                min="0.1"
                max="50"
                placeholder="1.0"
                @change="updateMapRadius"
              />
            </div>
            <div class="form-group">
              <label for="zone-freq">Frecuencia de análisis</label>
              <select id="zone-freq" v-model="newZone.frequency">
                <option value="manual">Manual (bajo demanda)</option>
                <option value="daily">Diaria</option>
                <option value="weekly">Semanal</option>
              </select>
            </div>
          </div>

          <div class="form-group">
            <label for="zone-cloud">Cobertura máxima de nubes: {{ newZone.max_cloud_cover }}%</label>
            <input 
              id="zone-cloud" 
              v-model.number="newZone.max_cloud_cover" 
              type="range"
              min="0"
              max="100"
              step="5"
            />
            <p class="input-help">Imágenes con más nubes serán descartadas</p>
          </div>

          <div class="form-group">
            <label for="zone-desc">Descripción (opcional)</label>
            <textarea 
              id="zone-desc" 
              v-model="newZone.description" 
              placeholder="Descripción de la zona a monitorear..."
              rows="2"
            ></textarea>
          </div>

          <div class="form-actions">
            <button type="button" class="btn-secondary" @click="closeModal">Cancelar</button>
            <button type="submit" class="btn-primary" :disabled="creating || !newZone.latitude || !newZone.longitude">
              {{ creating ? 'Creando...' : '🛰️ Crear Zona' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Delete Confirmation Modal -->
    <div v-if="zoneToDelete" class="modal-overlay" @click.self="zoneToDelete = null">
      <div class="modal-content modal-small">
        <div class="modal-header">
          <h3>Eliminar Zona</h3>
        </div>
        <p class="confirm-text">
          ¿Estás seguro de eliminar la zona <strong>{{ zoneToDelete.name }}</strong>?
          Esta acción eliminará todas las imágenes y alertas asociadas.
        </p>
        <div class="form-actions">
          <button class="btn-secondary" @click="zoneToDelete = null">Cancelar</button>
          <button class="btn-danger" @click="deleteZone" :disabled="deleting">
            {{ deleting ? 'Eliminando...' : 'Eliminar' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'

const props = defineProps({
  apiUrl: {
    type: String,
    required: true
  },
  token: {
    type: String,
    required: true
  }
})

const emit = defineEmits(['toast'])

// State
const zones = ref([])
const loading = ref(false)
const showAddZone = ref(false)
const creating = ref(false)
const deleting = ref(false)
const zoneToDelete = ref(null)
const serviceAvailable = ref(true)

// Map state
const mapContainer = ref(null)
let map = null
let marker = null
let circle = null
let rectangle = null
const mapMode = ref('point') // 'point' or 'rectangle'

const newZone = ref({
  name: '',
  latitude: null,
  longitude: null,
  radius_km: 1.0,
  frequency: 'manual',
  max_cloud_cover: 20,
  description: '',
  bounds: null // For rectangle selection
})

// Load Leaflet dynamically
const loadLeaflet = () => {
  return new Promise((resolve, reject) => {
    if (window.L) {
      resolve(window.L)
      return
    }
    
    // Load CSS
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'
    document.head.appendChild(link)
    
    // Load JS
    const script = document.createElement('script')
    script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'
    script.onload = () => resolve(window.L)
    script.onerror = reject
    document.head.appendChild(script)
  })
}

// Initialize map
const initMap = async () => {
  try {
    const L = await loadLeaflet()
    
    await nextTick()
    
    if (!mapContainer.value) return
    
    // Create map centered on South America by default
    map = L.map(mapContainer.value, {
      center: [-25, -55],
      zoom: 4,
      zoomControl: true
    })
    
    // Add OpenStreetMap tiles
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors',
      maxZoom: 19
    }).addTo(map)
    
    // Add satellite layer option
    const satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      attribution: '© Esri',
      maxZoom: 19
    })
    
    // Layer control
    const baseMaps = {
      "Mapa": L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap'
      }),
      "Satélite": satellite
    }
    L.control.layers(baseMaps).addTo(map)
    
    // Click handler
    map.on('click', onMapClick)
    
    // Drawing handlers
    let drawStartPoint = null
    
    map.on('mousedown', (e) => {
      if (mapMode.value === 'rectangle') {
        drawStartPoint = e.latlng
      }
    })
    
    map.on('mouseup', (e) => {
      if (mapMode.value === 'rectangle' && drawStartPoint) {
        createRectangle(drawStartPoint, e.latlng)
        drawStartPoint = null
      }
    })
    
  } catch (error) {
    console.error('Error loading Leaflet:', error)
  }
}

// Map click handler
const onMapClick = (e) => {
  if (mapMode.value !== 'point') return
  
  const { lat, lng } = e.latlng
  newZone.value.latitude = parseFloat(lat.toFixed(6))
  newZone.value.longitude = parseFloat(lng.toFixed(6))
  newZone.value.bounds = null
  
  updateMapMarker()
}

// Create rectangle from two points
const createRectangle = (point1, point2) => {
  const L = window.L
  if (!L || !map) return
  
  // Remove existing shapes
  if (rectangle) map.removeLayer(rectangle)
  if (marker) map.removeLayer(marker)
  if (circle) map.removeLayer(circle)
  
  // Create bounds
  const bounds = L.latLngBounds(point1, point2)
  const center = bounds.getCenter()
  
  // Update zone data
  newZone.value.latitude = parseFloat(center.lat.toFixed(6))
  newZone.value.longitude = parseFloat(center.lng.toFixed(6))
  newZone.value.bounds = {
    north: bounds.getNorth(),
    south: bounds.getSouth(),
    east: bounds.getEast(),
    west: bounds.getWest()
  }
  
  // Calculate approximate radius (diagonal / 2 in km)
  const diagonal = point1.distanceTo(point2) / 1000
  newZone.value.radius_km = parseFloat((diagonal / 2).toFixed(2))
  
  // Draw rectangle
  rectangle = L.rectangle(bounds, {
    color: '#4CAF50',
    weight: 2,
    fillOpacity: 0.2
  }).addTo(map)
  
  // Add center marker
  marker = L.marker(center, {
    icon: L.divIcon({
      className: 'custom-marker',
      html: '📍',
      iconSize: [30, 30],
      iconAnchor: [15, 30]
    })
  }).addTo(map)
}

// Update marker on map
const updateMapMarker = () => {
  const L = window.L
  if (!L || !map) return
  
  const lat = newZone.value.latitude
  const lng = newZone.value.longitude
  const radius = newZone.value.radius_km
  
  if (!lat || !lng) return
  
  // Remove existing shapes
  if (marker) map.removeLayer(marker)
  if (circle) map.removeLayer(circle)
  if (rectangle) map.removeLayer(rectangle)
  
  // Add marker
  marker = L.marker([lat, lng], {
    icon: L.divIcon({
      className: 'custom-marker',
      html: '📍',
      iconSize: [30, 30],
      iconAnchor: [15, 30]
    })
  }).addTo(map)
  
  // Add circle for radius
  if (radius) {
    circle = L.circle([lat, lng], {
      radius: radius * 1000, // Convert km to meters
      color: '#4CAF50',
      fillColor: '#4CAF50',
      fillOpacity: 0.2,
      weight: 2
    }).addTo(map)
  }
  
  // Pan to location
  map.setView([lat, lng], Math.max(map.getZoom(), 10))
}

// Update map from manual inputs
const updateMapFromInputs = () => {
  if (newZone.value.latitude && newZone.value.longitude) {
    newZone.value.bounds = null
    updateMapMarker()
  }
}

// Update map when radius changes
const updateMapRadius = () => {
  if (newZone.value.latitude && newZone.value.longitude && !newZone.value.bounds) {
    updateMapMarker()
  }
}

// Set map drawing mode
const setMapMode = (mode) => {
  mapMode.value = mode
  if (map) {
    if (mode === 'rectangle') {
      map.dragging.disable()
      mapContainer.value.style.cursor = 'crosshair'
    } else {
      map.dragging.enable()
      mapContainer.value.style.cursor = 'grab'
    }
  }
}

// Clear map selection
const clearMapSelection = () => {
  if (marker) map.removeLayer(marker)
  if (circle) map.removeLayer(circle)
  if (rectangle) map.removeLayer(rectangle)
  marker = null
  circle = null
  rectangle = null
  
  newZone.value.latitude = null
  newZone.value.longitude = null
  newZone.value.bounds = null
  newZone.value.radius_km = 1.0
}

// Locate user
const locateUser = () => {
  if (!navigator.geolocation) {
    emit('toast', { type: 'error', message: 'Geolocalización no disponible' })
    return
  }
  
  navigator.geolocation.getCurrentPosition(
    (position) => {
      newZone.value.latitude = parseFloat(position.coords.latitude.toFixed(6))
      newZone.value.longitude = parseFloat(position.coords.longitude.toFixed(6))
      newZone.value.bounds = null
      updateMapMarker()
      emit('toast', { type: 'success', message: 'Ubicación obtenida' })
    },
    (error) => {
      emit('toast', { type: 'error', message: 'No se pudo obtener la ubicación' })
    }
  )
}

// Format bounds for display
const formatBounds = (bounds) => {
  if (!bounds) return ''
  return `${bounds.south.toFixed(4)}° a ${bounds.north.toFixed(4)}° / ${bounds.west.toFixed(4)}° a ${bounds.east.toFixed(4)}°`
}

// Open modal and init map
const openAddZoneModal = async () => {
  showAddZone.value = true
  await nextTick()
  setTimeout(initMap, 100)
}

// Destroy map on modal close
const destroyMap = () => {
  if (map) {
    map.remove()
    map = null
    marker = null
    circle = null
    rectangle = null
  }
}

// API Helper
const api = async (method, endpoint, body = null) => {
  const options = {
    method,
    headers: {
      'Authorization': `Bearer ${props.token}`,
      'Content-Type': 'application/json',
      'Accept': 'application/json'
    }
  }
  if (body) {
    options.body = JSON.stringify(body)
  }
  
  const response = await fetch(`${props.apiUrl}${endpoint}`, options)
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Error desconocido' }))
    throw new Error(error.message || error.error || 'Error en la solicitud')
  }
  return response.json()
}

// Load zones
const loadZones = async () => {
  loading.value = true
  try {
    const data = await api('GET', '/satellite/zones')
    zones.value = data
  } catch (error) {
    console.error('Error loading zones:', error)
    emit('toast', { type: 'error', message: 'Error cargando zonas satelitales' })
  } finally {
    loading.value = false
  }
}

// Check service status
const checkServiceStatus = async () => {
  try {
    // Podríamos hacer un health check al worker
    serviceAvailable.value = true
  } catch {
    serviceAvailable.value = false
  }
}

// Create zone
const createZone = async () => {
  creating.value = true
  try {
    const zone = await api('POST', '/satellite/zones', newZone.value)
    zones.value.unshift(zone)
    closeModal()
    emit('toast', { type: 'success', message: `Zona "${zone.name}" creada exitosamente` })
  } catch (error) {
    emit('toast', { type: 'error', message: error.message })
  } finally {
    creating.value = false
  }
}

// Analyze zone
const analyzeZone = async (zone) => {
  zone.processing = true
  try {
    await api('POST', `/satellite/zones/${zone.id}/analyze`)
    emit('toast', { type: 'info', message: `Análisis iniciado para "${zone.name}"` })
    
    // Poll for updates
    setTimeout(() => {
      loadZones()
    }, 5000)
  } catch (error) {
    emit('toast', { type: 'error', message: error.message })
  } finally {
    zone.processing = false
  }
}

// Delete zone
const confirmDeleteZone = (zone) => {
  zoneToDelete.value = zone
}

const deleteZone = async () => {
  if (!zoneToDelete.value) return
  
  deleting.value = true
  try {
    await api('DELETE', `/satellite/zones/${zoneToDelete.value.id}`)
    zones.value = zones.value.filter(z => z.id !== zoneToDelete.value.id)
    emit('toast', { type: 'success', message: 'Zona eliminada' })
    zoneToDelete.value = null
  } catch (error) {
    emit('toast', { type: 'error', message: error.message })
  } finally {
    deleting.value = false
  }
}

// Helpers
const closeModal = () => {
  destroyMap()
  showAddZone.value = false
  mapMode.value = 'point'
  newZone.value = {
    name: '',
    latitude: null,
    longitude: null,
    radius_km: 1.0,
    frequency: 'manual',
    max_cloud_cover: 20,
    description: '',
    bounds: null
  }
}

const getImageUrl = (path) => {
  if (!path) return ''
  if (path.startsWith('http')) return path
  // Adjust base URL for storage
  const baseUrl = props.apiUrl.replace('/api', '')
  return `${baseUrl}/storage/${path}`
}

const onImageError = (e) => {
  e.target.style.display = 'none'
}

const formatCoords = (lat, lon) => {
  const latDir = lat >= 0 ? 'N' : 'S'
  const lonDir = lon >= 0 ? 'E' : 'W'
  return `${Math.abs(lat).toFixed(4)}°${latDir}, ${Math.abs(lon).toFixed(4)}°${lonDir}`
}

const formatTimeAgo = (dateStr) => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now - date
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMins / 60)
  const diffDays = Math.floor(diffHours / 24)
  
  if (diffMins < 1) return 'Justo ahora'
  if (diffMins < 60) return `Hace ${diffMins} min`
  if (diffHours < 24) return `Hace ${diffHours}h`
  if (diffDays < 7) return `Hace ${diffDays}d`
  return date.toLocaleDateString()
}

const getUniqueDetections = (detections) => {
  if (!detections) return []
  const unique = {}
  detections.forEach(d => {
    if (!unique[d.class_name]) {
      unique[d.class_name] = d
    }
  })
  return Object.values(unique)
}

// Lifecycle
onMounted(() => {
  loadZones()
  checkServiceStatus()
})
</script>

<style scoped>
.satellite-panel {
  padding: 1rem;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.panel-header h3 {
  margin: 0;
  font-size: 1.25rem;
  color: var(--text-primary, #fff);
}

.btn-add {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background: var(--accent, #4CAF50);
  color: white;
  border: none;
  border-radius: 0.5rem;
  cursor: pointer;
  font-size: 0.9rem;
  transition: background 0.2s;
}

.btn-add:hover:not(:disabled) {
  background: var(--accent-hover, #45a049);
}

.btn-add:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.service-warning {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  background: rgba(255, 152, 0, 0.15);
  border: 1px solid rgba(255, 152, 0, 0.3);
  border-radius: 0.5rem;
  color: #ffb74d;
  margin-bottom: 1rem;
  font-size: 0.9rem;
}

.zones-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1rem;
}

.zone-card {
  background: var(--card-bg, rgba(255,255,255,0.05));
  border: 1px solid var(--border, rgba(255,255,255,0.1));
  border-radius: 0.75rem;
  overflow: hidden;
  transition: transform 0.2s, box-shadow 0.2s;
}

.zone-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.2);
}

.zone-card.processing {
  opacity: 0.7;
}

.zone-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 1rem;
  background: rgba(0,0,0,0.2);
}

.zone-header h4 {
  margin: 0;
  font-size: 1rem;
  color: var(--text-primary, #fff);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.zone-actions {
  display: flex;
  gap: 0.25rem;
}

.btn-icon {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 0.375rem;
  cursor: pointer;
  font-size: 1rem;
  transition: background 0.2s;
}

.btn-icon:hover:not(:disabled) {
  background: rgba(255,255,255,0.1);
}

.btn-icon:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-analyze:hover:not(:disabled) {
  background: rgba(76, 175, 80, 0.2);
}

.btn-delete:hover:not(:disabled) {
  background: rgba(244, 67, 54, 0.2);
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.zone-preview {
  position: relative;
  aspect-ratio: 16/10;
  background: rgba(0,0,0,0.3);
  overflow: hidden;
}

.zone-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.no-image {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-secondary, rgba(255,255,255,0.5));
}

.globe-icon {
  font-size: 2rem;
  opacity: 0.5;
}

.no-image-text {
  font-size: 0.8rem;
  margin-top: 0.5rem;
}

.alerts-badge {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  background: #f44336;
  color: white;
  font-size: 0.75rem;
  font-weight: bold;
  padding: 0.2rem 0.5rem;
  border-radius: 1rem;
  min-width: 20px;
  text-align: center;
}

.zone-info {
  padding: 0.75rem 1rem;
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.85rem;
  margin-bottom: 0.4rem;
}

.info-row:last-child {
  margin-bottom: 0;
}

.label {
  color: var(--text-secondary, rgba(255,255,255,0.6));
}

.value {
  color: var(--text-primary, #fff);
}

.freq-badge {
  padding: 0.15rem 0.5rem;
  border-radius: 0.25rem;
  font-size: 0.75rem;
  text-transform: uppercase;
}

.freq-badge.manual { background: rgba(100,100,100,0.3); }
.freq-badge.daily { background: rgba(76, 175, 80, 0.3); color: #81c784; }
.freq-badge.weekly { background: rgba(33, 150, 243, 0.3); color: #64b5f6; }

.time-ago {
  font-size: 0.8rem;
  color: var(--text-secondary, rgba(255,255,255,0.6));
}

.detections-summary {
  padding: 0.5rem 1rem 0.75rem;
  border-top: 1px solid var(--border, rgba(255,255,255,0.1));
}

.detection-count {
  font-size: 0.75rem;
  color: var(--text-secondary, rgba(255,255,255,0.6));
  margin-bottom: 0.25rem;
  display: block;
}

.detection-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
}

.detection-tag {
  padding: 0.15rem 0.4rem;
  background: rgba(76, 175, 80, 0.2);
  color: #81c784;
  border-radius: 0.25rem;
  font-size: 0.7rem;
}

.more-tag {
  padding: 0.15rem 0.4rem;
  background: rgba(100,100,100,0.3);
  color: var(--text-secondary, rgba(255,255,255,0.6));
  border-radius: 0.25rem;
  font-size: 0.7rem;
}

/* Empty State */
.empty-state {
  grid-column: 1 / -1;
  text-align: center;
  padding: 3rem 1rem;
  color: var(--text-secondary, rgba(255,255,255,0.6));
}

.empty-icon {
  font-size: 3rem;
  display: block;
  margin-bottom: 1rem;
  opacity: 0.5;
}

.empty-state p {
  margin-bottom: 1rem;
}

/* Modals */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 1rem;
}

.modal-content {
  background: var(--card-bg, #1a1a2e);
  border: 1px solid var(--border, rgba(255,255,255,0.1));
  border-radius: 0.75rem;
  width: 100%;
  max-width: 500px;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-content.modal-small {
  max-width: 400px;
}

.modal-content.modal-large {
  max-width: 700px;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--border, rgba(255,255,255,0.1));
}

.modal-header h3 {
  margin: 0;
  font-size: 1.1rem;
  color: var(--text-primary, #fff);
}

.btn-close {
  background: transparent;
  border: none;
  color: var(--text-secondary, rgba(255,255,255,0.6));
  font-size: 1.25rem;
  cursor: pointer;
  padding: 0.25rem;
  line-height: 1;
}

.btn-close:hover {
  color: var(--text-primary, #fff);
}

.zone-form {
  padding: 1.25rem;
}

.form-group {
  margin-bottom: 1rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.4rem;
  font-size: 0.85rem;
  color: var(--text-secondary, rgba(255,255,255,0.7));
}

.form-group input,
.form-group select,
.form-group textarea {
  width: 100%;
  padding: 0.6rem 0.75rem;
  background: rgba(0,0,0,0.3);
  border: 1px solid var(--border, rgba(255,255,255,0.2));
  border-radius: 0.375rem;
  color: var(--text-primary, #fff);
  font-size: 0.9rem;
}

.form-group input:focus,
.form-group select:focus,
.form-group textarea:focus {
  outline: none;
  border-color: var(--accent, #4CAF50);
}

.form-group input[type="range"] {
  padding: 0;
  background: transparent;
  border: none;
}

.range-value {
  display: inline-block;
  margin-left: 0.5rem;
  color: var(--text-primary, #fff);
  font-size: 0.9rem;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-top: 1.5rem;
}

.btn-primary,
.btn-secondary,
.btn-danger {
  padding: 0.6rem 1.25rem;
  border: none;
  border-radius: 0.375rem;
  font-size: 0.9rem;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-primary {
  background: var(--accent, #4CAF50);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: var(--accent-hover, #45a049);
}

.btn-secondary {
  background: rgba(100,100,100,0.3);
  color: var(--text-primary, #fff);
}

.btn-secondary:hover {
  background: rgba(100,100,100,0.5);
}

.btn-danger {
  background: #f44336;
  color: white;
}

.btn-danger:hover:not(:disabled) {
  background: #d32f2f;
}

.btn-primary:disabled,
.btn-danger:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.confirm-text {
  padding: 1rem 1.25rem;
  color: var(--text-primary, #fff);
  font-size: 0.95rem;
  line-height: 1.5;
}

.confirm-text strong {
  color: #f44336;
}

/* Responsive */
@media (max-width: 600px) {
  .zones-grid {
    grid-template-columns: 1fr;
  }
  
  .form-row {
    grid-template-columns: 1fr;
  }
  
  .panel-header {
    flex-direction: column;
    gap: 0.75rem;
    align-items: stretch;
  }
  
  .btn-add {
    justify-content: center;
  }
  
  .modal-content.modal-large {
    max-width: 100%;
  }
  
  .map-container {
    height: 250px;
  }
}

/* Map Styles */
.map-container {
  height: 350px;
  width: 100%;
  border-radius: 0.5rem;
  border: 1px solid var(--border, rgba(255,255,255,0.2));
  overflow: hidden;
  background: #1a1a2e;
}

.map-help {
  font-size: 0.8rem;
  color: var(--text-secondary, rgba(255,255,255,0.6));
  margin: 0.25rem 0 0.5rem;
}

.map-controls {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.5rem;
  flex-wrap: wrap;
}

.btn-map-tool {
  padding: 0.4rem 0.75rem;
  background: rgba(100,100,100,0.3);
  border: 1px solid var(--border, rgba(255,255,255,0.2));
  border-radius: 0.375rem;
  color: var(--text-primary, #fff);
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-map-tool:hover {
  background: rgba(100,100,100,0.5);
}

.btn-map-tool.active {
  background: var(--accent, #4CAF50);
  border-color: var(--accent, #4CAF50);
}

.coords-display {
  background: rgba(0,0,0,0.3);
  border-radius: 0.375rem;
  padding: 0.75rem;
  margin-bottom: 1rem;
}

.coord-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.85rem;
  margin-bottom: 0.25rem;
}

.coord-info:last-child {
  margin-bottom: 0;
}

.coord-label {
  color: var(--text-secondary, rgba(255,255,255,0.6));
}

.coord-value {
  color: var(--accent, #4CAF50);
  font-family: monospace;
}

.input-help {
  font-size: 0.75rem;
  color: var(--text-secondary, rgba(255,255,255,0.5));
  margin-top: 0.25rem;
}

/* Custom Leaflet marker */
:deep(.custom-marker) {
  background: transparent !important;
  border: none !important;
  font-size: 24px;
  text-shadow: 0 2px 4px rgba(0,0,0,0.5);
}

/* Leaflet overrides for dark theme */
:deep(.leaflet-container) {
  background: #1a1a2e;
  font-family: inherit;
}

:deep(.leaflet-control-layers) {
  background: rgba(30, 30, 50, 0.95);
  border: 1px solid rgba(255,255,255,0.2);
  border-radius: 0.5rem;
  color: #fff;
}

:deep(.leaflet-control-layers-toggle) {
  background-color: rgba(30, 30, 50, 0.95);
}

:deep(.leaflet-control-layers-expanded) {
  padding: 0.5rem;
}

:deep(.leaflet-control-layers label) {
  color: #fff;
}

:deep(.leaflet-control-zoom a) {
  background: rgba(30, 30, 50, 0.95);
  color: #fff;
  border-color: rgba(255,255,255,0.2);
}

:deep(.leaflet-control-zoom a:hover) {
  background: rgba(50, 50, 70, 0.95);
}

:deep(.leaflet-bar) {
  border: 1px solid rgba(255,255,255,0.2);
  border-radius: 0.375rem;
  overflow: hidden;
}

:deep(.leaflet-popup-content-wrapper) {
  background: rgba(30, 30, 50, 0.95);
  color: #fff;
  border-radius: 0.5rem;
}

:deep(.leaflet-popup-tip) {
  background: rgba(30, 30, 50, 0.95);
}
</style>
