"""
VLM Engine - Moondream2 Vision Language Model
==============================================

Este módulo encapsula toda la lógica de Moondream2 para análisis de imágenes.
Diseñado para funcionar como servicio independiente.
"""

import os
import gc
import cv2
import numpy as np
from PIL import Image
from typing import Optional, Dict, Any
import threading
import time
import psutil
import torch.nn as nn
from transformers.generation.utils import GenerationMixin


class _GenerationAdapter(nn.Module, GenerationMixin):
    """Wrapper that adds `generate` support when base model doesn't implement it."""

    def __init__(self, base_model: nn.Module):
        super().__init__()
        self.base_model = base_model
        self.config = getattr(base_model, "config", None)
        self.main_input_name = getattr(base_model, "main_input_name", "input_ids")

    def forward(self, *args, **kwargs):
        return self.base_model(*args, **kwargs)

    def prepare_inputs_for_generation(self, *args, **kwargs):
        if hasattr(self.base_model, "prepare_inputs_for_generation"):
            return self.base_model.prepare_inputs_for_generation(*args, **kwargs)
        return super().prepare_inputs_for_generation(*args, **kwargs)

    def __getattr__(self, name):
        if name in {"base_model", "config", "main_input_name"}:
            return super().__getattribute__(name)
        return getattr(self.base_model, name)

    def __setattr__(self, name, value):
        if name in {"base_model", "config", "main_input_name"}:
            super().__setattr__(name, value)
        else:
            setattr(self.base_model, name, value)


class MoondreamAnalyzer:
    """
    Analizador de imágenes usando Moondream2 VLM.
    
    Características:
    - Carga lazy del modelo (solo cuando se necesita)
    - Thread-safe para múltiples requests
    - Optimizado para CPU
    """
    
    def __init__(
        self,
        model_id: str = "vikhyatk/moondream2",
        revision: str = "2024-08-26",
        max_memory_mb: Optional[int] = None,
        idle_unload_seconds: Optional[int] = None,
        monitor_interval: int = 30,
    ):
        """
        Inicializa el analizador.
        
        Args:
            model_id: ID del modelo en HuggingFace
            revision: Versión/revisión del modelo (2024-08-26 is stable and doesn't require pyvips)
            max_memory_mb: Límite de memoria blanda; si se supera se descarga el modelo
            idle_unload_seconds: Tiempo de inactividad antes de descargar el modelo
            monitor_interval: Intervalo en segundos para revisar memoria/inactividad
        """
        self.model_id = model_id
        self.revision = revision
        self.model = None
        self.tokenizer = None
        self._lock = threading.Lock()
        self._loading = False
        self._loaded = False
        self._load_error = None
        self.max_memory_mb = max_memory_mb
        self.idle_unload_seconds = idle_unload_seconds
        self.monitor_interval = max(5, monitor_interval)
        self._last_used = time.time()
        self._monitor_thread: Optional[threading.Thread] = None
        try:
            self._process = psutil.Process(os.getpid())
        except Exception as e:
            print(f"⚠️ No se pudo inicializar psutil.Process: {e}")
            self._process = None
        
        print(f"🤖 MoondreamAnalyzer inicializado (modelo: {model_id})")
        
        if self.max_memory_mb or self.idle_unload_seconds:
            self._start_monitor_thread()

    def _start_monitor_thread(self):
        """Inicia el thread que monitorea memoria e inactividad."""
        if self._monitor_thread and self._monitor_thread.is_alive():
            return
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            name="vlm-memory-monitor",
            daemon=True,
        )
        self._monitor_thread.start()

    def _monitor_loop(self):
        """Revisa periódicamente memoria e inactividad."""
        while True:
            time.sleep(self.monitor_interval)
            try:
                self._enforce_memory_limit()
                self._check_idle_timeout()
            except Exception as e:
                print(f"⚠️ Monitor VLM error: {e}")

    def _check_idle_timeout(self):
        """Descarga el modelo si lleva inactivo demasiado tiempo."""
        if not self.idle_unload_seconds or not self._loaded:
            return
        idle_time = time.time() - self._last_used
        if idle_time >= self.idle_unload_seconds:
            print("♻️ Descargando modelo VLM por inactividad prolongada...")
            self._unload_model("Idle timeout reached")

    def _get_process_memory_mb(self) -> Optional[float]:
        """Obtiene la memoria RSS actual del proceso."""
        if self._process is None:
            return None
        try:
            rss = self._process.memory_info().rss
            return rss / (1024 * 1024)
        except Exception as e:
            print(f"⚠️ No se pudo leer memoria RSS: {e}")
            return None

    def _enforce_memory_limit(self):
        """Descarga el modelo si supera el límite configurado."""
        if not self.max_memory_mb or not self._loaded:
            return
        rss_mb = self._get_process_memory_mb()
        if rss_mb is None:
            return
        if rss_mb > self.max_memory_mb:
            print(
                f"⚠️ Límite de memoria VLM excedido "
                f"({rss_mb:.0f} MB > {self.max_memory_mb} MB). Descargando modelo..."
            )
            self._unload_model("Memory limit exceeded")

    def _update_last_used(self):
        """Actualiza el timestamp de último uso."""
        self._last_used = time.time()

    def _unload_model(self, reason: str) -> bool:
        """Libera la memoria del modelo."""
        with self._lock:
            if not self._loaded and self.model is None:
                return False
            self.model = None
            self.tokenizer = None
            self._loaded = False
            self._loading = False
            self._load_error = None
        
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        
        gc.collect()
        print(f"🧹 Modelo VLM descargado ({reason})")
        return True

    def unload_model(self, reason: str = "manual request") -> bool:
        """Permite descargar el modelo desde otros módulos."""
        return self._unload_model(reason)
    
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
            self._ensure_text_model_generate()
            
            load_time = time.time() - start_time
            print(f"✅ Modelo VLM cargado en {load_time:.1f}s")
            
            with self._lock:
                self._loaded = True
                self._loading = False
                self._last_used = time.time()
            
            return True
            
        except Exception as e:
            print(f"❌ Error cargando modelo VLM: {e}")
            import traceback
            traceback.print_exc()
            
            with self._lock:
                self._load_error = str(e)
                self._loading = False
            
            return False
    
    def _ensure_text_model_generate(self):
        """Envuelve text_model con GenerationMixin si hace falta."""
        text_model = getattr(self.model, "text_model", None)
        if text_model is None:
            return
        if hasattr(text_model, "generate"):
            return
        print("⚙️ text_model no expone .generate(); aplicando GenerationAdapter.")
        self.model.text_model = _GenerationAdapter(text_model)
    
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
        
        self._update_last_used()
        result = None
        
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
            
            result = response.strip()
            
        except Exception as e:
            print(f"❌ Error analizando imagen: {e}")
            import traceback
            traceback.print_exc()
            result = f"Error: {str(e)}"
        finally:
            self._enforce_memory_limit()
        
        return result
    
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
        
        self._update_last_used()
        result = None
        
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
            
            result = response.strip()
            
        except Exception as e:
            print(f"❌ Error analizando imagen: {e}")
            result = f"Error: {str(e)}"
        finally:
            self._enforce_memory_limit()
        
        return result
    
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
            "error": self._load_error,
            "max_memory_mb": self.max_memory_mb,
            "idle_unload_seconds": self.idle_unload_seconds,
            "last_used_at": self._last_used,
            "memory_usage_mb": self._get_process_memory_mb(),
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
