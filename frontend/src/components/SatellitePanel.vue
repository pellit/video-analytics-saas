<template>
  <div class="satellite-panel">
    <!-- Header -->
    <div class="panel-header">
      <h3>🛰️ Zonas Satelitales</h3>
      <div class="header-actions">
        <div class="view-toggle">
          <button 
            class="view-btn" 
            :class="{ active: viewMode === 'map' }" 
            @click="viewMode = 'map'"
            title="Vista de mapa"
          >
            🗺️
          </button>
          <button 
            class="view-btn" 
            :class="{ active: viewMode === 'grid' }" 
            @click="viewMode = 'grid'"
            title="Vista de tarjetas"
          >
            📋
          </button>
        </div>
        <button class="btn-add" @click="openAddZoneModal" :disabled="!serviceAvailable">
          <span class="icon">+</span> Nueva Zona
        </button>
      </div>
    </div>

    <!-- Service Status -->
    <div v-if="!serviceAvailable" class="service-warning">
      <span class="warning-icon">⚠️</span>
      <span>Servicio satelital no configurado. Configura SENTINEL_CLIENT_ID y SENTINEL_CLIENT_SECRET.</span>
    </div>

    <!-- Global Map View (Default) -->
    <div v-if="viewMode === 'map'" class="map-layout">
      <!-- Map Container -->
      <div class="global-map-container" :class="{ 'with-sidebar': showImagesSidebar }">
        <div id="global-satellite-map" ref="globalMapContainer" class="global-map"></div>
        
        <!-- Map Search -->
        <div class="map-search-overlay">
          <input 
            v-model="searchQuery" 
            @keyup.enter="searchLocation"
            type="text" 
            placeholder="🔍 Buscar ubicación..." 
            class="map-search-input"
          />
          <button v-if="searchQuery" class="search-btn" @click="searchLocation">
            Buscar
          </button>
        </div>
        
        <!-- Zone Info Popup -->
        <div v-if="selectedZoneOnMap" class="zone-info-popup">
          <button class="popup-close" @click="selectedZoneOnMap = null">✕</button>
          <h4>{{ selectedZoneOnMap.name }}</h4>
          <img 
            v-if="selectedZoneOnMap.last_image_path" 
            :src="getImageUrl(selectedZoneOnMap.last_image_path)" 
            class="popup-image"
          />
          <div v-else class="popup-no-image">Sin imagen</div>
          <div class="popup-info">
            <span>📍 {{ formatCoords(selectedZoneOnMap.latitude, selectedZoneOnMap.longitude) }}</span>
            <span>📏 Radio: {{ selectedZoneOnMap.radius_km }} km</span>
          </div>
          <div class="popup-actions">
            <button class="btn-sm btn-primary" @click="analyzeZone(selectedZoneOnMap)">
              🔍 Analizar
            </button>
            <button class="btn-sm btn-secondary" @click="viewZoneInSidebar(selectedZoneOnMap)">
              📷 Ver Imagen
            </button>
          </div>
        </div>
        
        <!-- Quick Add Button on Map -->
        <div class="map-fab-actions">
          <button class="fab-btn" @click="enableMapAddMode" title="Agregar zona desde mapa">
            ➕
          </button>
          <button class="fab-btn" @click="centerOnUserLocation" title="Mi ubicación">
            🎯
          </button>
          <button 
            class="fab-btn" 
            :class="{ active: showImagesSidebar }"
            @click="showImagesSidebar = !showImagesSidebar" 
            title="Panel de imágenes"
          >
            🖼️
          </button>
        </div>
      </div>

      <!-- Images Sidebar -->
      <Transition name="slide">
        <div v-if="showImagesSidebar" class="images-sidebar">
          <div class="sidebar-header">
            <h4>🛰️ Imágenes Sentinel</h4>
            <button class="btn-close" @click="showImagesSidebar = false">✕</button>
          </div>
          
          <div class="sidebar-content">
            <!-- Selected zone image -->
            <div v-if="sidebarSelectedZone" class="sidebar-zone-detail">
              <h5>{{ sidebarSelectedZone.name }}</h5>
              <div class="sidebar-image-container">
                <img 
                  v-if="sidebarSelectedZone.last_image_path"
                  :src="getImageUrl(sidebarSelectedZone.last_image_path)"
                  @click="openImageViewer(sidebarSelectedZone)"
                  class="sidebar-main-image"
                />
                <div v-else class="sidebar-no-image">
                  <span>🛰️</span>
                  <p>Sin imagen disponible</p>
                  <button class="btn-sm btn-primary" @click="analyzeZone(sidebarSelectedZone)">
                    Obtener imagen
                  </button>
                </div>
              </div>
              <div class="sidebar-zone-info">
                <span>📍 {{ formatCoords(sidebarSelectedZone.latitude, sidebarSelectedZone.longitude) }}</span>
                <span>📏 Radio: {{ sidebarSelectedZone.radius_km }} km</span>
                <span v-if="sidebarSelectedZone.last_capture">
                  📅 {{ formatDate(sidebarSelectedZone.last_capture) }}
                </span>
              </div>
              <div class="sidebar-actions">
                <button class="btn-sm btn-primary" @click="analyzeZone(sidebarSelectedZone)">
                  🔄 Actualizar
                </button>
                <button class="btn-sm btn-secondary" @click="openReportsModal(sidebarSelectedZone)">
                  📊 Reportes
                </button>
              </div>

              <!-- Image History Section -->
              <div class="sidebar-history">
                <div class="history-header">
                  <h5>📜 Historial de Cambios</h5>
                  <button 
                    v-if="!loadingHistory" 
                    class="btn-icon-sm" 
                    @click="loadZoneHistory(sidebarSelectedZone)"
                    title="Actualizar historial"
                  >
                    🔄
                  </button>
                </div>
                
                <div v-if="loadingHistory" class="history-loading">
                  <div class="spinner-sm"></div>
                  <span>Cargando historial...</span>
                </div>
                
                <div v-else-if="zoneImageHistory.length === 0" class="history-empty">
                  <span>Sin historial de imágenes</span>
                </div>
                
                <div v-else class="history-timeline">
                  <div 
                    v-for="(img, idx) in zoneImageHistory" 
                    :key="img.id" 
                    class="history-item"
                    :class="{ 
                      'has-changes': img.changes_detected && Object.keys(img.changes_detected).length > 0,
                      'failed': img.status === 'failed'
                    }"
                    @click="selectHistoryImage(img)"
                  >
                    <div class="history-thumb">
                      <img 
                        v-if="img.image_path" 
                        :src="getImageUrl(img.image_path)"
                      />
                      <div v-else class="thumb-placeholder-sm">
                        {{ img.status === 'pending' ? '⏳' : img.status === 'processing' ? '⚙️' : '❌' }}
                      </div>
                    </div>
                    <div class="history-info">
                      <span class="history-date">{{ formatDate(img.captured_at || img.created_at) }}</span>
                      <span class="history-status" :class="img.status">
                        {{ getStatusLabel(img.status) }}
                      </span>
                      <span v-if="img.changes_detected" class="history-changes">
                        {{ getChangeSummary(img.changes_detected) }}
                      </span>
                    </div>
                    <div v-if="idx < zoneImageHistory.length - 1 && img.image_path" class="history-compare">
                      <button 
                        class="btn-compare" 
                        @click.stop="compareImages(img, zoneImageHistory[idx + 1])"
                        title="Comparar con anterior"
                      >
                        ⇄
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            
            <!-- All zones thumbnails -->
            <div class="sidebar-zones-list">
              <h5>Todas las Zonas</h5>
              <div class="sidebar-thumbs-grid">
                <div 
                  v-for="zone in zones" 
                  :key="zone.id" 
                  class="sidebar-thumb"
                  :class="{ 
                    active: sidebarSelectedZone?.id === zone.id,
                    'has-alerts': zone.unread_alerts_count > 0
                  }"
                  @click="selectZoneInSidebar(zone)"
                >
                  <img 
                    v-if="zone.last_image_path" 
                    :src="getImageUrl(zone.last_image_path)"
                  />
                  <div v-else class="thumb-placeholder">
                    🛰️
                  </div>
                  <span class="thumb-label">{{ zone.name }}</span>
                  <span v-if="zone.unread_alerts_count" class="thumb-badge">
                    {{ zone.unread_alerts_count }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Transition>

      <!-- Image Comparison Modal -->
      <div v-if="showCompareModal" class="modal-overlay" @click.self="showCompareModal = false">
        <div class="modal-content modal-compare">
          <div class="modal-header">
            <h3>🔍 Comparar Imágenes</h3>
            <button class="btn-close" @click="showCompareModal = false">✕</button>
          </div>
          <div class="compare-container">
            <div class="compare-image">
              <h4>Anterior</h4>
              <img v-if="compareOldImage?.image_path" :src="getImageUrl(compareOldImage.image_path)" />
              <span class="compare-date">{{ formatDate(compareOldImage?.captured_at) }}</span>
            </div>
            <div class="compare-divider">→</div>
            <div class="compare-image">
              <h4>Actual</h4>
              <img v-if="compareNewImage?.image_path" :src="getImageUrl(compareNewImage.image_path)" />
              <span class="compare-date">{{ formatDate(compareNewImage?.captured_at) }}</span>
            </div>
          </div>
          <div v-if="compareNewImage?.changes_detected" class="compare-changes">
            <h4>Cambios Detectados</h4>
            <pre>{{ JSON.stringify(compareNewImage.changes_detected, null, 2) }}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- Zones Grid View -->
    <div v-else class="zones-grid">
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

// View mode state
const viewMode = ref('map') // 'map' or 'grid'
const globalMapContainer = ref(null)
let globalMap = null
const globalMapMarkers = ref([])
const selectedZoneOnMap = ref(null)
const searchQuery = ref('')
const mapAddMode = ref(false)

// Sidebar state
const showImagesSidebar = ref(true)
const sidebarSelectedZone = ref(null)

// History state
const zoneImageHistory = ref([])
const loadingHistory = ref(false)
const showCompareModal = ref(false)
const compareOldImage = ref(null)
const compareNewImage = ref(null)

// Map state for modal
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

const formatDate = (dateStr) => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleDateString('es-ES', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
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

// Initialize global map
const initGlobalMap = async () => {
  try {
    const L = await loadLeaflet()
    
    await nextTick()
    
    if (!globalMapContainer.value) return
    
    // Create map centered on world view
    globalMap = L.map(globalMapContainer.value, {
      center: [20, 0],  // World center
      zoom: 2,
      zoomControl: true,
      worldCopyJump: true
    })
    
    // Add satellite base layer (default)
    const satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      attribution: '© Esri',
      maxZoom: 19
    }).addTo(globalMap)
    
    // Add street layer option
    const streets = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap',
      maxZoom: 19
    })
    
    // Layer control
    const baseMaps = {
      "🛰️ Satélite": satellite,
      "🗺️ Mapa": streets
    }
    L.control.layers(baseMaps).addTo(globalMap)
    
    // Add existing zones as markers
    updateGlobalMapMarkers()
    
    // Click handler for adding new zone from map
    globalMap.on('click', (e) => {
      if (mapAddMode.value) {
        const { lat, lng } = e.latlng
        newZone.value.latitude = parseFloat(lat.toFixed(6))
        newZone.value.longitude = parseFloat(lng.toFixed(6))
        mapAddMode.value = false
        openAddZoneModal()
      }
    })
    
  } catch (error) {
    console.error('Error loading global map:', error)
  }
}

// Update markers on global map
const updateGlobalMapMarkers = () => {
  if (!globalMap || !window.L) return
  
  // Extra safety check - verify map container still exists
  try {
    if (!globalMap.getContainer()) return
  } catch (e) {
    return
  }
  
  const L = window.L
  
  // Clear existing markers
  globalMapMarkers.value.forEach(m => {
    try {
      if (globalMap) globalMap.removeLayer(m)
    } catch (e) { /* ignore */ }
  })
  globalMapMarkers.value = []
  
  // Add markers for each zone
  zones.value.forEach(zone => {
    if (zone.latitude && zone.longitude) {
      // Create custom icon
      const icon = L.divIcon({
        className: 'zone-marker',
        html: `<div class="zone-marker-inner">${zone.unread_alerts_count > 0 ? '🔴' : '🟢'}</div>`,
        iconSize: [30, 30],
        iconAnchor: [15, 15]
      })
      
      const markerObj = L.marker([zone.latitude, zone.longitude], { icon })
        .addTo(globalMap)
        .on('click', () => {
          selectedZoneOnMap.value = zone
          // Zoom to zone with appropriate level based on radius
          const zoomLevel = getZoomLevelForRadius(zone.radius_km)
          // Safety check before setView
          if (globalMap && globalMap.getContainer()) {
            globalMap.setView([zone.latitude, zone.longitude], zoomLevel, { animate: true })
          }
          // Also select in sidebar
          sidebarSelectedZone.value = zone
          loadZoneHistory(zone)
        })
      
      // Add circle for radius
      const circleObj = L.circle([zone.latitude, zone.longitude], {
        radius: zone.radius_km * 1000, // km to m
        color: zone.unread_alerts_count > 0 ? '#ef4444' : '#22c55e',
        fillOpacity: 0.1,
        weight: 2
      }).addTo(globalMap)
      
      globalMapMarkers.value.push(markerObj)
      globalMapMarkers.value.push(circleObj)
    }
  })
}

// Calculate appropriate zoom level based on radius
const getZoomLevelForRadius = (radiusKm) => {
  // Approximate zoom levels for different radii
  // At zoom 16, ~2.4km viewport at equator
  if (radiusKm <= 0.5) return 16
  if (radiusKm <= 1) return 15
  if (radiusKm <= 2) return 14
  if (radiusKm <= 5) return 13
  if (radiusKm <= 10) return 12
  if (radiusKm <= 20) return 11
  return 10
}

// Search location using Nominatim
const searchLocation = async () => {
  if (!searchQuery.value.trim() || !globalMap) return
  
  try {
    const response = await fetch(
      `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(searchQuery.value)}`
    )
    const results = await response.json()
    
    if (results.length > 0) {
      const { lat, lon, display_name } = results[0]
      globalMap.setView([parseFloat(lat), parseFloat(lon)], 12)
      
      emit('toast', { type: 'success', message: `Ubicación encontrada: ${display_name.split(',')[0]}` })
    } else {
      emit('toast', { type: 'warning', message: 'No se encontró la ubicación' })
    }
  } catch (e) {
    console.error('Search error:', e)
    emit('toast', { type: 'error', message: 'Error al buscar ubicación' })
  }
}

// Enable add mode on map
const enableMapAddMode = () => {
  mapAddMode.value = true
  emit('toast', { type: 'info', message: 'Haz clic en el mapa para agregar una zona' })
}

// Center on user location
const centerOnUserLocation = () => {
  if (!globalMap) return
  
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude } = position.coords
        globalMap.setView([latitude, longitude], 12)
      },
      (error) => {
        console.error('Geolocation error:', error)
        emit('toast', { type: 'error', message: 'No se pudo obtener tu ubicación' })
      }
    )
  } else {
    emit('toast', { type: 'warning', message: 'Geolocalización no disponible' })
  }
}

// Go to zone (show image modal)
const goToZone = (zone) => {
  if (globalMap && zone.latitude && zone.longitude) {
    globalMap.setView([zone.latitude, zone.longitude], 14)
  }
  selectedZoneOnMap.value = null
  // TODO: Could open image viewer modal here
}

// View zone in sidebar
const viewZoneInSidebar = (zone) => {
  sidebarSelectedZone.value = zone
  showImagesSidebar.value = true
  selectedZoneOnMap.value = null
  
  // Pan map to zone
  if (globalMap && zone.latitude && zone.longitude) {
    globalMap.setView([zone.latitude, zone.longitude], 14)
  }
}

// Select zone in sidebar
const selectZoneInSidebar = (zone) => {
  sidebarSelectedZone.value = zone
  
  // Pan map to zone
  if (globalMap && zone.latitude && zone.longitude) {
    globalMap.setView([zone.latitude, zone.longitude], 14)
  }
  
  // Load zone history
  loadZoneHistory(zone)
}

// Load zone image history
const loadZoneHistory = async (zone) => {
  if (!zone) return
  
  loadingHistory.value = true
  zoneImageHistory.value = []
  
  try {
    const response = await fetch(`${props.apiUrl}/satellite/zones/${zone.id}/images`, {
      headers: {
        'Authorization': `Bearer ${props.token}`,
        'Accept': 'application/json'
      }
    })
    
    if (response.ok) {
      const data = await response.json()
      zoneImageHistory.value = data.data || data || []
    }
  } catch (error) {
    console.error('Error loading zone history:', error)
  } finally {
    loadingHistory.value = false
  }
}

// Select history image to view
const selectHistoryImage = (img) => {
  if (img.image_path) {
    // Could show in main image area or open modal
    emit('toast', { type: 'info', message: `Imagen del ${formatDate(img.captured_at || img.created_at)}` })
  }
}

// Compare two images
const compareImages = (newImg, oldImg) => {
  compareNewImage.value = newImg
  compareOldImage.value = oldImg
  showCompareModal.value = true
}

// Get status label
const getStatusLabel = (status) => {
  const labels = {
    'pending': '⏳ Pendiente',
    'processing': '⚙️ Procesando',
    'completed': '✅ Completado',
    'failed': '❌ Error'
  }
  return labels[status] || status
}

// Get change summary
const getChangeSummary = (changes) => {
  if (!changes) return ''
  if (changes.similarity_score !== undefined) {
    const diff = 100 - (changes.similarity_score * 100)
    return `${diff.toFixed(1)}% cambios`
  }
  if (changes.changes_detected) {
    return '🔴 Cambios detectados'
  }
  return '🟢 Sin cambios'
}

// Open image viewer for a zone
const openImageViewer = (zone) => {
  // Could open fullscreen modal here
  emit('toast', { type: 'info', message: `Imagen de ${zone.name}` })
}

// Open reports modal for a zone
const openReportsModal = (zone) => {
  // This could open the existing reports functionality
  emit('toast', { type: 'info', message: `Reportes de ${zone.name}` })
  // Switch to grid view and scroll to zone's reports if available
}

// Watch zones changes to update markers
watch(zones, () => {
  if (globalMap) {
    // Debounce marker updates to prevent rapid fire
    setTimeout(() => {
      if (globalMap) updateGlobalMapMarkers()
    }, 100)
  }
}, { deep: true })

// Destroy global map
const destroyGlobalMap = () => {
  if (globalMap) {
    // Stop all event listeners first
    try {
      globalMap.off()
    } catch (e) { /* ignore */ }
    
    // Clear markers first
    globalMapMarkers.value.forEach(m => {
      try {
        globalMap.removeLayer(m)
      } catch (e) {
        // Ignore
      }
    })
    globalMapMarkers.value = []
    
    // Remove map
    try {
      globalMap.remove()
    } catch (e) {
      console.warn('Error removing map:', e)
    }
    globalMap = null
  }
}

// Watch viewMode to init/destroy global map
watch(viewMode, async (newMode) => {
  if (newMode === 'map') {
    // Always recreate map when switching to map view
    destroyGlobalMap()
    // Wait for DOM to be ready
    await nextTick()
    await nextTick()
    // Extra delay for DOM to fully render
    setTimeout(() => {
      if (globalMapContainer.value) {
        initGlobalMap()
      } else {
        // Retry after more time if container not ready
        setTimeout(() => {
          initGlobalMap()
        }, 200)
      }
    }, 150)
  } else {
    // Destroy map when switching away
    destroyGlobalMap()
  }
})

// Lifecycle
onMounted(() => {
  loadZones()
  checkServiceStatus()
  // Init global map after a small delay
  setTimeout(() => {
    if (viewMode.value === 'map') {
      initGlobalMap()
    }
  }, 100)
})

// Cleanup on unmount to prevent Leaflet errors
onUnmounted(() => {
  // Destroy modal map
  if (map) {
    try {
      map.off()
      map.remove()
    } catch (e) { /* ignore */ }
    map = null
  }
  // Destroy global map
  if (globalMap) {
    try {
      globalMap.off()
      globalMap.remove()
    } catch (e) { /* ignore */ }
    globalMap = null
  }
  // Clear markers
  marker = null
  circle = null
  rectangle = null
  globalMapMarkers.value = []
})

// Auto-select first zone with image when zones load
watch(zones, (newZones) => {
  if (newZones.length > 0 && !sidebarSelectedZone.value) {
    // Select first zone with image, or just first zone
    const zoneWithImage = newZones.find(z => z.last_image_path)
    const selectedZone = zoneWithImage || newZones[0]
    sidebarSelectedZone.value = selectedZone
    // Load history for the selected zone
    loadZoneHistory(selectedZone)
  }
}, { immediate: true })
</script>

<style scoped>
/* Map Layout */
.map-layout {
  display: flex;
  gap: 16px;
  height: calc(100vh - 200px);
  min-height: 400px;
}

/* Global Map Styles */
.global-map-container {
  position: relative;
  flex: 1;
  height: 100%;
  min-height: 400px;
  border-radius: 12px;
  overflow: hidden;
  transition: all 0.3s ease;
}

.global-map-container.with-sidebar {
  flex: 0 0 calc(100% - 350px);
}

.global-map {
  width: 100%;
  height: 100%;
  z-index: 1;
}

.map-search-overlay {
  position: absolute;
  top: 10px;
  left: 50px;
  z-index: 1000;
  display: flex;
  gap: 8px;
}

.map-search-input {
  width: 280px;
  padding: 10px 16px;
  background: rgba(30, 30, 45, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  color: #fff;
  font-size: 14px;
  backdrop-filter: blur(10px);
}

.map-search-input::placeholder {
  color: rgba(255, 255, 255, 0.5);
}

.map-search-input:focus {
  outline: none;
  border-color: #4CAF50;
}

.search-btn {
  padding: 10px 16px;
  background: linear-gradient(135deg, #4CAF50, #45a049);
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
}

.zone-info-popup {
  position: absolute;
  bottom: 20px;
  left: 20px;
  z-index: 1000;
  background: rgba(30, 30, 45, 0.95);
  backdrop-filter: blur(20px);
  border-radius: 12px;
  padding: 16px;
  min-width: 250px;
  max-width: 300px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}

.popup-close {
  position: absolute;
  top: 8px;
  right: 8px;
  background: none;
  border: none;
  color: rgba(255, 255, 255, 0.7);
  cursor: pointer;
  font-size: 16px;
}

.zone-info-popup h4 {
  margin: 0 0 12px;
  color: #fff;
  font-size: 16px;
}

.popup-image {
  width: 100%;
  height: 120px;
  object-fit: cover;
  border-radius: 8px;
  margin-bottom: 12px;
}

.popup-no-image {
  width: 100%;
  height: 120px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.4);
  margin-bottom: 12px;
}

.popup-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.7);
  margin-bottom: 12px;
}

.popup-actions {
  display: flex;
  gap: 8px;
}

.btn-sm {
  padding: 8px 12px;
  font-size: 12px;
  border-radius: 6px;
  border: none;
  cursor: pointer;
}

.btn-sm.btn-primary {
  background: linear-gradient(135deg, #4CAF50, #45a049);
  color: white;
}

.btn-sm.btn-secondary {
  background: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.8);
}

.map-fab-actions {
  position: absolute;
  bottom: 20px;
  right: 20px;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.fab-btn {
  width: 50px;
  height: 50px;
  border-radius: 50%;
  background: linear-gradient(135deg, #4CAF50, #45a049);
  color: white;
  border: none;
  font-size: 20px;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  transition: transform 0.2s, box-shadow 0.2s;
}

.fab-btn:hover {
  transform: scale(1.1);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.4);
}

/* Zone marker styles */
:deep(.zone-marker) {
  background: transparent !important;
  border: none !important;
}

:deep(.zone-marker-inner) {
  font-size: 20px;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.5);
}

/* Header styles */
.header-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.view-toggle {
  display: flex;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  overflow: hidden;
}

.view-btn {
  padding: 8px 12px;
  background: transparent;
  border: none;
  color: rgba(255, 255, 255, 0.6);
  cursor: pointer;
  font-size: 16px;
  transition: all 0.2s;
}

.view-btn.active {
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
}

.view-btn:hover:not(.active) {
  background: rgba(255, 255, 255, 0.1);
}

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

/* Images Sidebar */
.images-sidebar {
  width: 330px;
  flex-shrink: 0;
  background: rgba(30, 30, 45, 0.95);
  backdrop-filter: blur(20px);
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.sidebar-header h4 {
  margin: 0;
  font-size: 16px;
  color: #fff;
}

.sidebar-header .btn-close {
  background: none;
  border: none;
  color: rgba(255, 255, 255, 0.7);
  cursor: pointer;
  font-size: 18px;
  padding: 4px;
}

.sidebar-header .btn-close:hover {
  color: #fff;
}

.sidebar-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.sidebar-zone-detail {
  margin-bottom: 20px;
}

.sidebar-zone-detail h5 {
  margin: 0 0 12px;
  color: #fff;
  font-size: 14px;
}

.sidebar-image-container {
  border-radius: 8px;
  overflow: hidden;
  margin-bottom: 12px;
}

.sidebar-main-image {
  width: 100%;
  aspect-ratio: 4/3;
  object-fit: cover;
  cursor: pointer;
  transition: transform 0.3s ease;
}

.sidebar-main-image:hover {
  transform: scale(1.02);
}

.sidebar-no-image {
  width: 100%;
  aspect-ratio: 4/3;
  background: rgba(0, 0, 0, 0.3);
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 12px;
  color: rgba(255, 255, 255, 0.5);
  border-radius: 8px;
}

.sidebar-no-image span {
  font-size: 48px;
}

.sidebar-no-image p {
  margin: 0;
  font-size: 14px;
}

.sidebar-zone-info {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.7);
  margin-bottom: 12px;
}

.sidebar-actions {
  display: flex;
  gap: 8px;
}

.sidebar-zones-list {
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  padding-top: 16px;
}

.sidebar-zones-list h5 {
  margin: 0 0 12px;
  color: rgba(255, 255, 255, 0.7);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.sidebar-thumbs-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}

.sidebar-thumb {
  position: relative;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  border: 2px solid transparent;
  transition: all 0.2s ease;
}

.sidebar-thumb.active {
  border-color: #4CAF50;
}

.sidebar-thumb.has-alerts {
  border-color: #ef4444;
}

.sidebar-thumb img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
}

.thumb-placeholder {
  width: 100%;
  aspect-ratio: 1;
  background: rgba(0, 0, 0, 0.3);
  display: flex;
  justify-content: center;
  align-items: center;
  font-size: 24px;
}

.thumb-label {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: rgba(0, 0, 0, 0.7);
  padding: 4px 6px;
  font-size: 10px;
  color: #fff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.thumb-badge {
  position: absolute;
  top: 4px;
  right: 4px;
  background: #ef4444;
  color: white;
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 10px;
  font-weight: bold;
}

/* Sidebar Transition */
.slide-enter-active,
.slide-leave-active {
  transition: all 0.3s ease;
}

.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  transform: translateX(100%);
}

/* FAB Button Active State */
.fab-btn.active {
  background: linear-gradient(135deg, #4CAF50, #45a049);
  color: white;
}

/* History Section Styles */
.sidebar-history {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.history-header h5 {
  margin: 0;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.8);
}

.btn-icon-sm {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
  padding: 4px;
  opacity: 0.7;
  transition: opacity 0.2s;
}

.btn-icon-sm:hover {
  opacity: 1;
}

.history-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  color: rgba(255, 255, 255, 0.6);
  font-size: 12px;
  padding: 12px 0;
}

.spinner-sm {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.2);
  border-top-color: #4CAF50;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.history-empty {
  color: rgba(255, 255, 255, 0.5);
  font-size: 12px;
  text-align: center;
  padding: 16px 0;
}

.history-timeline {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 300px;
  overflow-y: auto;
}

.history-item {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 8px;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid transparent;
}

.history-item:hover {
  background: rgba(0, 0, 0, 0.3);
}

.history-item.has-changes {
  border-color: rgba(239, 68, 68, 0.5);
  background: rgba(239, 68, 68, 0.1);
}

.history-item.failed {
  opacity: 0.6;
}

.history-thumb {
  width: 48px;
  height: 48px;
  border-radius: 6px;
  overflow: hidden;
  flex-shrink: 0;
}

.history-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumb-placeholder-sm {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.3);
  font-size: 18px;
}

.history-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.history-date {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.9);
}

.history-status {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.6);
}

.history-status.completed {
  color: #4CAF50;
}

.history-status.failed {
  color: #ef4444;
}

.history-status.processing {
  color: #f59e0b;
}

.history-changes {
  font-size: 10px;
  color: #ef4444;
  font-weight: 500;
}

.history-compare {
  flex-shrink: 0;
}

.btn-compare {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: #fff;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.btn-compare:hover {
  background: rgba(255, 255, 255, 0.2);
}

/* Compare Modal */
.modal-compare {
  max-width: 900px;
  width: 95%;
}

.compare-container {
  display: flex;
  gap: 16px;
  align-items: center;
  padding: 16px 0;
}

.compare-image {
  flex: 1;
  text-align: center;
}

.compare-image h4 {
  margin: 0 0 8px;
  font-size: 14px;
  color: rgba(255, 255, 255, 0.8);
}

.compare-image img {
  width: 100%;
  max-height: 400px;
  object-fit: contain;
  border-radius: 8px;
}

.compare-date {
  display: block;
  margin-top: 8px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.6);
}

.compare-divider {
  font-size: 24px;
  color: rgba(255, 255, 255, 0.5);
  flex-shrink: 0;
}

.compare-changes {
  margin-top: 16px;
  padding: 16px;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 8px;
}

.compare-changes h4 {
  margin: 0 0 12px;
  font-size: 14px;
}

.compare-changes pre {
  margin: 0;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.8);
  white-space: pre-wrap;
  word-break: break-word;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
