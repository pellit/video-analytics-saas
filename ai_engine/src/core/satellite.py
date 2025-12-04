"""
Satellite Image Service - Sentinel Hub Integration
Descarga imágenes satelitales de alta resolución para análisis con IA.

Fuentes soportadas:
- Sentinel-2 (ESA): Gratuito, 10m resolución, actualización cada 5 días
- Futuro: Planet Labs (Pago), Google Earth Engine

Uso:
    from src.core.satellite import SatelliteService
    
    service = SatelliteService()
    image = service.get_latest_image(lat=-32.94, lon=-60.63, km_radius=1)
"""

import os
import numpy as np
import cv2
import requests
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass


@dataclass
class SatelliteConfig:
    """Configuración para Sentinel Hub API"""
    client_id: str
    client_secret: str
    instance_id: Optional[str] = None
    
    @classmethod
    def from_env(cls) -> 'SatelliteConfig':
        """Cargar configuración desde variables de entorno"""
        return cls(
            client_id=os.environ.get('SENTINEL_CLIENT_ID', ''),
            client_secret=os.environ.get('SENTINEL_CLIENT_SECRET', ''),
            instance_id=os.environ.get('SENTINEL_INSTANCE_ID')
        )
    
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)


class SatelliteService:
    """
    Servicio para obtener imágenes satelitales de Sentinel Hub.
    
    Las imágenes satelitales se tratan como "cámaras lentas" que se actualizan
    cada varios días en lugar de 30 FPS.
    """
    
    # Token OAuth2 cacheado
    _token: Optional[str] = None
    _token_expires: Optional[datetime] = None
    
    def __init__(self, config: Optional[SatelliteConfig] = None):
        self.config = config or SatelliteConfig.from_env()
        self.base_url = "https://services.sentinel-hub.com"
        
    def is_available(self) -> bool:
        """Verifica si el servicio está configurado y disponible"""
        return self.config.is_configured()
    
    def _get_token(self) -> Optional[str]:
        """Obtener token OAuth2 de Sentinel Hub"""
        if not self.config.is_configured():
            print("❌ Sentinel Hub no configurado. Faltan SENTINEL_CLIENT_ID/SECRET")
            return None
            
        # Usar token cacheado si aún es válido
        if self._token and self._token_expires and datetime.now() < self._token_expires:
            return self._token
            
        try:
            response = requests.post(
                f"{self.base_url}/oauth/token",
                data={
                    'grant_type': 'client_credentials',
                    'client_id': self.config.client_id,
                    'client_secret': self.config.client_secret
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                self._token = data['access_token']
                # Token válido por 1 hora menos 5 min de margen
                self._token_expires = datetime.now() + timedelta(seconds=data.get('expires_in', 3600) - 300)
                return self._token
            else:
                print(f"❌ Error OAuth Sentinel: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ Error conectando a Sentinel Hub: {e}")
            return None
    
    def _calculate_bbox(self, lat: float, lon: float, km_radius: float = 1.0) -> list:
        """
        Calcular bounding box alrededor de un punto.
        
        Args:
            lat: Latitud del centro
            lon: Longitud del centro  
            km_radius: Radio en kilómetros
            
        Returns:
            [min_lon, min_lat, max_lon, max_lat]
        """
        # 1 grado de latitud ≈ 111 km
        # 1 grado de longitud ≈ 111 * cos(lat) km
        lat_delta = km_radius / 111.0
        lon_delta = km_radius / (111.0 * np.cos(np.radians(lat)))
        
        return [
            lon - lon_delta,  # min_lon
            lat - lat_delta,  # min_lat
            lon + lon_delta,  # max_lon
            lat + lat_delta   # max_lat
        ]
    
    def get_latest_image(
        self, 
        lat: float, 
        lon: float, 
        km_radius: float = 1.0,
        days_back: int = 30,
        max_cloud_cover: float = 0.2,
        output_size: Tuple[int, int] = (512, 512)
    ) -> Optional[np.ndarray]:
        """
        Obtener la imagen satelital más reciente de una ubicación.
        
        Args:
            lat: Latitud del centro
            lon: Longitud del centro
            km_radius: Radio del área en km
            days_back: Buscar imágenes de los últimos N días
            max_cloud_cover: Máximo porcentaje de nubes (0.0-1.0)
            output_size: Tamaño de la imagen de salida (width, height)
            
        Returns:
            Imagen en formato OpenCV (BGR, numpy array) o None si falla
        """
        token = self._get_token()
        if not token:
            return None
            
        bbox = self._calculate_bbox(lat, lon, km_radius)
        
        # Evalscript para color verdadero con brillo mejorado
        evalscript = """
        //VERSION=3
        function setup() {
            return {
                input: ["B04", "B03", "B02", "dataMask"],
                output: { bands: 4 }
            };
        }
        
        function evaluatePixel(sample) {
            // Ajustar brillo (2.5x) y agregar canal alpha para transparencia
            return [
                2.5 * sample.B04,
                2.5 * sample.B03, 
                2.5 * sample.B02,
                sample.dataMask
            ];
        }
        """
        
        # Fechas
        date_to = datetime.now()
        date_from = date_to - timedelta(days=days_back)
        
        payload = {
            "input": {
                "bounds": {
                    "bbox": bbox,
                    "properties": {
                        "crs": "http://www.opengis.net/def/crs/EPSG/0/4326"
                    }
                },
                "data": [{
                    "type": "sentinel-2-l2a",
                    "dataFilter": {
                        "timeRange": {
                            "from": date_from.strftime("%Y-%m-%dT00:00:00Z"),
                            "to": date_to.strftime("%Y-%m-%dT23:59:59Z")
                        },
                        "maxCloudCoverage": int(max_cloud_cover * 100),
                        "mosaickingOrder": "leastCC"  # Priorizar menos nubes
                    }
                }]
            },
            "output": {
                "width": output_size[0],
                "height": output_size[1],
                "responses": [{
                    "identifier": "default",
                    "format": {
                        "type": "image/png"
                    }
                }]
            },
            "evalscript": evalscript
        }
        
        try:
            print(f"🛰️ Solicitando imagen satelital para ({lat}, {lon})...")
            
            response = requests.post(
                f"{self.base_url}/api/v1/process",
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                },
                timeout=60
            )
            
            if response.status_code == 200:
                # Decodificar PNG a numpy array
                image_bytes = np.frombuffer(response.content, np.uint8)
                image = cv2.imdecode(image_bytes, cv2.IMREAD_UNCHANGED)
                
                if image is not None:
                    # Convertir RGBA a BGR (OpenCV standard)
                    if image.shape[2] == 4:
                        # Usar alpha channel para máscara de datos válidos
                        alpha = image[:, :, 3]
                        bgr = cv2.cvtColor(image[:, :, :3], cv2.COLOR_RGB2BGR)
                        # Áreas sin datos (alpha=0) las dejamos negras
                        bgr[alpha == 0] = [0, 0, 0]
                        image = bgr
                    else:
                        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
                    
                    print(f"✅ Imagen satelital obtenida: {image.shape}")
                    return image
                else:
                    print("❌ No se pudo decodificar la imagen")
                    return None
            else:
                error_msg = response.text[:500] if response.text else "Unknown error"
                print(f"❌ Error Sentinel API: {response.status_code} - {error_msg}")
                return None
                
        except requests.Timeout:
            print("❌ Timeout al obtener imagen satelital")
            return None
        except Exception as e:
            print(f"❌ Error obteniendo imagen satelital: {e}")
            return None
    
    def get_image_metadata(self, lat: float, lon: float, km_radius: float = 1.0) -> Dict[str, Any]:
        """
        Obtener metadatos de las imágenes disponibles para una ubicación.
        Útil para saber la fecha de la última imagen disponible.
        """
        # TODO: Implementar búsqueda de catálogo
        return {
            "status": "not_implemented",
            "message": "Metadata search coming soon"
        }


# Instancia global (lazy loading)
_satellite_service: Optional[SatelliteService] = None

def get_satellite_service() -> SatelliteService:
    """Obtener instancia del servicio de satélite"""
    global _satellite_service
    if _satellite_service is None:
        _satellite_service = SatelliteService()
    return _satellite_service


# Función de conveniencia
def get_satellite_image(lat: float, lon: float, km_radius: float = 1.0) -> Optional[np.ndarray]:
    """
    Función de conveniencia para obtener imagen satelital.
    
    Ejemplo:
        from src.core.satellite import get_satellite_image
        image = get_satellite_image(-32.94, -60.63)
    """
    return get_satellite_service().get_latest_image(lat, lon, km_radius)


if __name__ == "__main__":
    # Test básico
    service = SatelliteService()
    
    if service.is_available():
        print("🛰️ Servicio satelital configurado")
        # Test con coordenadas de Rosario, Argentina
        image = service.get_latest_image(-32.94, -60.63)
        if image is not None:
            cv2.imwrite("test_satellite.jpg", image)
            print("✅ Imagen guardada en test_satellite.jpg")
    else:
        print("⚠️ Servicio satelital no configurado")
        print("   Configure SENTINEL_CLIENT_ID y SENTINEL_CLIENT_SECRET")
