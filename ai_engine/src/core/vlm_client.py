"""
VLM Client - Cliente HTTP para el microservicio VLM
====================================================

Este módulo proporciona un cliente para comunicarse con el servicio VLM
separado vía HTTP API o Redis.
"""

import os
import json
import base64
import time
import uuid
from typing import Optional, Dict, Any

import cv2
import numpy as np
import requests
import redis

# ============================================================================
# Configuration
# ============================================================================

VLM_SERVICE_URL = os.environ.get('VLM_SERVICE_URL', 'http://vlm_service:5100')
REDIS_HOST = os.environ.get('REDIS_HOST', 'redis')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
VLM_TIMEOUT = int(os.environ.get('VLM_TIMEOUT', 120))  # 2 minutos default


class VLMClient:
    """
    Cliente para comunicarse con el microservicio VLM.
    
    Soporta:
    - Llamadas HTTP síncronas (más simple)
    - Llamadas Redis asíncronas (para procesamiento en cola)
    """
    
    def __init__(self, service_url: str = None, use_redis: bool = False):
        """
        Inicializa el cliente VLM.
        
        Args:
            service_url: URL del servicio VLM (default: VLM_SERVICE_URL env)
            use_redis: Si True, usa Redis para comunicación asíncrona
        """
        self.service_url = service_url or VLM_SERVICE_URL
        self.use_redis = use_redis
        self._redis_client = None
        self._available_cache = None
        self._last_health_check = 0
        
        print(f"🔌 VLMClient inicializado (URL: {self.service_url})")
    
    @property
    def available(self) -> bool:
        """
        Verifica si el servicio VLM está disponible.
        Cachea el resultado por 30 segundos para evitar llamadas excesivas.
        
        Returns:
            True si el servicio está disponible
        """
        now = time.time()
        if self._available_cache is not None and (now - self._last_health_check) < 30:
            return self._available_cache
        
        try:
            health = self.check_health()
            self._available_cache = health.get('status') == 'ok'
            self._last_health_check = now
            return self._available_cache
        except:
            self._available_cache = False
            self._last_health_check = now
            return False
    
    def status(self) -> Dict[str, Any]:
        """Alias para compatibilidad."""
        return self.get_status()
    
    def _get_redis(self) -> Optional[redis.Redis]:
        """Obtiene conexión Redis."""
        if self._redis_client is None:
            try:
                self._redis_client = redis.Redis(
                    host=REDIS_HOST,
                    port=REDIS_PORT,
                    decode_responses=True
                )
                self._redis_client.ping()
            except Exception as e:
                print(f"⚠️ Redis no disponible: {e}")
                self._redis_client = None
        return self._redis_client
    
    def _encode_image(self, image: np.ndarray) -> str:
        """Codifica imagen numpy a base64."""
        _, buffer = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return base64.b64encode(buffer).decode('utf-8')
    
    def check_health(self) -> Dict[str, Any]:
        """
        Verifica el estado del servicio VLM.
        
        Returns:
            Dict con estado del servicio
        """
        try:
            response = requests.get(
                f"{self.service_url}/health",
                timeout=10
            )
            return response.json()
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def get_status(self) -> Dict[str, Any]:
        """
        Obtiene estado detallado del servicio.
        
        Returns:
            Dict con información detallada
        """
        try:
            response = requests.get(
                f"{self.service_url}/status",
                timeout=10
            )
            return response.json()
        except Exception as e:
            return {"enabled": False, "error": str(e)}
    
    def preload_model(self) -> Dict[str, Any]:
        """
        Solicita pre-carga del modelo VLM.
        
        Returns:
            Dict con estado de la solicitud
        """
        try:
            response = requests.post(
                f"{self.service_url}/preload",
                timeout=10
            )
            return response.json()
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def analyze_image(self, image, prompt: str, prompt_key: str = None) -> Dict[str, Any]:
        """
        Analiza una imagen con el servicio VLM vía HTTP.
        
        Args:
            image: Imagen como numpy array (BGR de OpenCV) O string base64
            prompt: Pregunta o instrucción
            prompt_key: Clave de prompt predefinido (opcional)
            
        Returns:
            Dict con {"success": bool, "answer": str, "error": str opcional}
        """
        try:
            # Soportar tanto numpy array como base64 string
            if isinstance(image, np.ndarray):
                image_base64 = self._encode_image(image)
            elif isinstance(image, str):
                image_base64 = image
            else:
                return {"success": False, "error": f"Tipo de imagen no soportado: {type(image)}"}
            
            # Preparar request
            payload = {
                "image_base64": image_base64,
                "prompt": prompt
            }
            if prompt_key:
                payload["prompt_key"] = prompt_key
            
            # Llamar al servicio
            response = requests.post(
                f"{self.service_url}/analyze",
                json=payload,
                timeout=VLM_TIMEOUT
            )
            
            result = response.json()
            
            if result.get("success"):
                return {
                    "success": True,
                    "answer": result.get("response", "")
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Error desconocido")
                }
                
        except requests.Timeout:
            return {"success": False, "error": "Timeout al conectar con el servicio VLM"}
        except requests.ConnectionError:
            return {"success": False, "error": "No se pudo conectar con el servicio VLM"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def analyze_image_url(self, image_url: str, prompt: str, prompt_key: str = None) -> str:
        """
        Analiza una imagen desde URL.
        
        Args:
            image_url: URL de la imagen
            prompt: Pregunta o instrucción
            prompt_key: Clave de prompt predefinido (opcional)
            
        Returns:
            Respuesta del modelo
        """
        try:
            payload = {
                "image_url": image_url,
                "prompt": prompt
            }
            if prompt_key:
                payload["prompt_key"] = prompt_key
            
            response = requests.post(
                f"{self.service_url}/analyze-url",
                json=payload,
                timeout=VLM_TIMEOUT
            )
            
            result = response.json()
            
            if result.get("success"):
                return result.get("response", "")
            else:
                return f"Error: {result.get('error', 'Error desconocido')}"
                
        except Exception as e:
            return f"Error: {str(e)}"
    
    def analyze_image_async(
        self, 
        image: np.ndarray, 
        prompt: str, 
        callback_channel: str = None,
        timeout: int = 120
    ) -> Optional[str]:
        """
        Analiza imagen de forma asíncrona vía Redis.
        
        Args:
            image: Imagen numpy array
            prompt: Pregunta
            callback_channel: Canal Redis para respuesta (opcional)
            timeout: Timeout en segundos
            
        Returns:
            Respuesta del modelo o None si timeout
        """
        r = self._get_redis()
        if r is None:
            return self.analyze_image(image, prompt)  # Fallback a HTTP
        
        request_id = str(uuid.uuid4())
        reply_channel = callback_channel or f"vlm_response_{request_id}"
        
        try:
            # Subscribirse al canal de respuesta ANTES de enviar
            pubsub = r.pubsub()
            pubsub.subscribe(reply_channel)
            
            # Enviar solicitud
            image_base64 = self._encode_image(image)
            r.publish('vlm_requests', json.dumps({
                'request_id': request_id,
                'image_base64': image_base64,
                'prompt': prompt,
                'reply_channel': reply_channel
            }))
            
            # Esperar respuesta
            start_time = time.time()
            for message in pubsub.listen():
                if time.time() - start_time > timeout:
                    break
                    
                if message['type'] == 'message':
                    data = json.loads(message['data'])
                    if data.get('request_id') == request_id:
                        pubsub.unsubscribe()
                        if data.get('success'):
                            return data.get('response', '')
                        else:
                            return f"Error: {data.get('error', 'Unknown')}"
            
            pubsub.unsubscribe()
            return "Error: Timeout esperando respuesta VLM"
            
        except Exception as e:
            return f"Error: {str(e)}"
    
    def get_prompts(self) -> Dict[str, str]:
        """
        Obtiene lista de prompts predefinidos del servicio.
        
        Returns:
            Dict con prompts disponibles
        """
        try:
            response = requests.get(
                f"{self.service_url}/prompts",
                timeout=10
            )
            return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    def validate_detection(
        self, 
        image, 
        detected_objects: list,
        context_prompt: str = None
    ) -> Dict[str, Any]:
        """
        Valida detecciones YOLO usando VLM.
        
        Args:
            image: Imagen como numpy array o base64 string
            detected_objects: Lista de objetos detectados ["person", "car", etc]
            context_prompt: Contexto adicional opcional
            
        Returns:
            Dict con {"success": bool, "validation": str, "context": str opcional}
        """
        objects_str = ", ".join(detected_objects)
        prompt = f"Looking at this image, verify if these objects are really present: {objects_str}."
        if context_prompt:
            prompt += f" Additional context: {context_prompt}"
        prompt += " For each object, respond with 'Yes' if truly visible or 'No' if it might be a false detection."
        
        result = self.analyze_image(image, prompt)
        
        if result.get("success"):
            return {
                "success": True,
                "validation": result.get("answer", ""),
                "detected_objects": detected_objects
            }
        return result
    
    def suggest_classes(
        self, 
        image, 
        user_context: str = None
    ) -> Dict[str, Any]:
        """
        Sugiere clases de detección basadas en el análisis de la escena.
        
        Args:
            image: Imagen como numpy array o base64 string
            user_context: Contexto del usuario sobre la escena
            
        Returns:
            Dict con suggested_classes, scene_description, objects_found
        """
        try:
            # Soportar tanto numpy array como base64 string
            if isinstance(image, np.ndarray):
                image_base64 = self._encode_image(image)
            elif isinstance(image, str):
                image_base64 = image
            else:
                return {"success": False, "error": f"Tipo de imagen no soportado: {type(image)}"}
            
            payload = {"image_base64": image_base64}
            if user_context:
                payload["user_context"] = user_context
            
            response = requests.post(
                f"{self.service_url}/suggest-classes",
                json=payload,
                timeout=VLM_TIMEOUT
            )
            
            return response.json()
            
        except requests.Timeout:
            return {"success": False, "error": "Timeout al conectar con el servicio VLM"}
        except requests.ConnectionError:
            return {"success": False, "error": "No se pudo conectar con el servicio VLM"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def batch_analyze(self, image, questions: list) -> Dict[str, Any]:
        """
        Analiza una imagen con múltiples preguntas.
        
        Args:
            image: Imagen como numpy array o base64 string
            questions: Lista de preguntas
            
        Returns:
            Dict con {"success": bool, "answers": [str]}
        """
        answers = []
        for question in questions:
            result = self.analyze_image(image, question)
            if result.get("success"):
                answers.append(result.get("answer", ""))
            else:
                answers.append(f"Error: {result.get('error', 'Unknown')}")
        
        return {"success": True, "answers": answers}


# ============================================================================
# Singleton instance
# ============================================================================

_vlm_client: Optional[VLMClient] = None


def get_vlm_client() -> VLMClient:
    """Obtiene instancia singleton del cliente VLM."""
    global _vlm_client
    if _vlm_client is None:
        _vlm_client = VLMClient()
    return _vlm_client


def analyze_with_vlm(image: np.ndarray, prompt: str, prompt_key: str = None) -> str:
    """
    Función de conveniencia para analizar imágenes con VLM.
    
    Args:
        image: Imagen numpy array
        prompt: Pregunta o instrucción
        prompt_key: Clave de prompt predefinido
        
    Returns:
        Respuesta del modelo
    """
    client = get_vlm_client()
    return client.analyze_image(image, prompt, prompt_key)
