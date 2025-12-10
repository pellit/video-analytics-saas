"""
VLM Engine - Moondream2 Vision Language Model
==============================================

Este módulo encapsula toda la lógica de Moondream2 para análisis de imágenes.
Diseñado para funcionar como servicio independiente.
"""

import os
import cv2
import numpy as np
from PIL import Image
from typing import Optional, Dict, Any
import threading
import time


class MoondreamAnalyzer:
    """
    Analizador de imágenes usando Moondream2 VLM.
    
    Características:
    - Carga lazy del modelo (solo cuando se necesita)
    - Thread-safe para múltiples requests
    - Optimizado para CPU
    """
    
    def __init__(self, model_id: str = "vikhyatk/moondream2", revision: str = "2024-08-26"):
        """
        Inicializa el analizador.
        
        Args:
            model_id: ID del modelo en HuggingFace
            revision: Versión/revisión del modelo (2024-08-26 is stable and doesn't require pyvips)
        """
        self.model_id = model_id
        self.revision = revision
        self.model = None
        self.tokenizer = None
        self._lock = threading.Lock()
        self._loading = False
        self._loaded = False
        self._load_error = None
        
        print(f"🤖 MoondreamAnalyzer inicializado (modelo: {model_id})")
    
    def _load_model(self) -> bool:
        """
        Carga el modelo de forma thread-safe.
        
        Returns:
            True si el modelo está listo, False si hay error
        """
        with self._lock:
            if self._loaded:
                return True
            
            if self._loading:
                # Otro thread está cargando, esperar
                return False
            
            self._loading = True
        
        try:
            print(f"⏳ Cargando modelo VLM: {self.model_id}...")
            start_time = time.time()
            
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
            
            # Cargar tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_id,
                revision=self.revision,
                trust_remote_code=True
            )
            
            # Cargar modelo (CPU only)
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_id,
                revision=self.revision,
                trust_remote_code=True,
                torch_dtype=torch.float32,  # CPU uses float32
                device_map="cpu"
            )
            
            load_time = time.time() - start_time
            print(f"✅ Modelo VLM cargado en {load_time:.1f}s")
            
            with self._lock:
                self._loaded = True
                self._loading = False
            
            return True
            
        except Exception as e:
            print(f"❌ Error cargando modelo VLM: {e}")
            import traceback
            traceback.print_exc()
            
            with self._lock:
                self._load_error = str(e)
                self._loading = False
            
            return False
    
    def is_loaded(self) -> bool:
        """Verifica si el modelo está cargado."""
        return self._loaded
    
    def is_loading(self) -> bool:
        """Verifica si el modelo está cargando."""
        return self._loading
    
    def get_error(self) -> Optional[str]:
        """Obtiene el error de carga si existe."""
        return self._load_error
    
    def ensure_loaded(self) -> bool:
        """
        Asegura que el modelo esté cargado.
        Bloquea hasta que termine de cargar o falle.
        """
        if self._loaded:
            return True
        
        if not self._loading:
            return self._load_model()
        
        # Esperar a que termine de cargar
        max_wait = 120  # 2 minutos max
        waited = 0
        while self._loading and waited < max_wait:
            time.sleep(1)
            waited += 1
        
        return self._loaded
    
    def analyze_image(self, image: np.ndarray, prompt: str) -> str:
        """
        Analiza una imagen con un prompt dado.
        
        Args:
            image: Imagen como numpy array (BGR de OpenCV)
            prompt: Pregunta o instrucción para el análisis
            
        Returns:
            Respuesta del modelo como string
        """
        if not self.ensure_loaded():
            error = self._load_error or "Modelo no disponible"
            return f"Error: {error}"
        
        try:
            # Convertir BGR a RGB
            if len(image.shape) == 3 and image.shape[2] == 3:
                image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            else:
                image_rgb = image
            
            # Convertir a PIL Image
            pil_image = Image.fromarray(image_rgb)
            
            # Analizar con el modelo
            with self._lock:
                # Encode image
                enc_image = self.model.encode_image(pil_image)
                
                # Generate response
                response = self.model.answer_question(
                    enc_image,
                    prompt,
                    self.tokenizer
                )
            
            return response.strip()
            
        except Exception as e:
            print(f"❌ Error analizando imagen: {e}")
            import traceback
            traceback.print_exc()
            return f"Error: {str(e)}"
    
    def analyze_pil_image(self, pil_image: Image.Image, prompt: str) -> str:
        """
        Analiza una imagen PIL directamente.
        
        Args:
            pil_image: Imagen PIL
            prompt: Pregunta o instrucción
            
        Returns:
            Respuesta del modelo
        """
        if not self.ensure_loaded():
            error = self._load_error or "Modelo no disponible"
            return f"Error: {error}"
        
        try:
            # Asegurar RGB
            if pil_image.mode != 'RGB':
                pil_image = pil_image.convert('RGB')
            
            with self._lock:
                enc_image = self.model.encode_image(pil_image)
                response = self.model.answer_question(
                    enc_image,
                    prompt,
                    self.tokenizer
                )
            
            return response.strip()
            
        except Exception as e:
            print(f"❌ Error analizando imagen: {e}")
            return f"Error: {str(e)}"
    
    def get_status(self) -> Dict[str, Any]:
        """
        Obtiene el estado actual del analizador.
        
        Returns:
            Dict con información de estado
        """
        return {
            "model_id": self.model_id,
            "revision": self.revision,
            "loaded": self._loaded,
            "loading": self._loading,
            "error": self._load_error
        }


# Prompts predefinidos para diferentes casos de uso
PREDEFINED_PROMPTS = {
    # Satellite / Aerial
    "satellite_general": "Describe what you see in this satellite image. Include terrain type, vegetation, and any structures.",
    "satellite_flood": "Does this satellite image show signs of flooding or water accumulation? Describe the affected areas.",
    "satellite_fire": "Are there any signs of fire, smoke, or burned areas in this satellite image?",
    "satellite_construction": "Identify any construction sites, new buildings, or infrastructure changes in this image.",
    "satellite_vegetation": "Analyze the vegetation in this satellite image. Describe forest coverage, agricultural areas, and any deforestation.",
    
    # CAD / Architecture
    "cad_general": "Describe this architectural floor plan in detail. What type of building is it? How many floors does it show?",
    "cad_rooms": "List all rooms or spaces visible in this floor plan. For each room, describe its apparent purpose and relative size.",
    "cad_safety": "Identify safety elements in this floor plan: emergency exits, fire extinguisher locations, escape routes, and any safety hazards.",
    "cad_structural": "Identify structural elements: load-bearing walls, columns, beams, and foundation indicators.",
    "cad_dimensions": "Estimate the approximate dimensions of the spaces shown. Identify any dimension annotations visible.",
    "cad_materials": "Based on the drawing style and annotations, suggest what materials might be used for walls, floors, and finishes.",
    
    # Video / Surveillance
    "video_describe": "Describe what you see in this image from a surveillance camera.",
    "video_people": "How many people are visible in this image? Describe their positions and activities.",
    "video_vehicles": "Identify any vehicles in this image. Describe their type, color, and position.",
    "video_anomaly": "Is there anything unusual or suspicious in this image? Describe any anomalies.",
    
    # General
    "general_describe": "Describe this image in detail.",
    "general_objects": "List all objects visible in this image.",
    "general_text": "Read and transcribe any text visible in this image.",
}


def get_prompt(prompt_key: str) -> Optional[str]:
    """
    Obtiene un prompt predefinido por su clave.
    
    Args:
        prompt_key: Clave del prompt (ej: 'satellite_general')
        
    Returns:
        El prompt si existe, None si no
    """
    return PREDEFINED_PROMPTS.get(prompt_key)


def list_prompts() -> Dict[str, str]:
    """
    Lista todos los prompts predefinidos.
    
    Returns:
        Dict con todos los prompts disponibles
    """
    return PREDEFINED_PROMPTS.copy()
