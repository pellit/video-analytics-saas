"""
Moondream2 VLM (Vision Language Model) - CPU Optimized
Interpreta imágenes y responde preguntas sobre ellas.
Ideal para:
- Análisis de imágenes satelitales
- Validación de detecciones YOLO
- Generación de descripciones contextuales
"""

import os
import cv2
import numpy as np
from typing import Optional, Union
from PIL import Image
from io import BytesIO
import base64

# Global singleton instance (lazy loaded)
_vlm_instance = None

class MoondreamAnalyzer:
    """
    Moondream2 VLM para interpretación de imágenes en CPU.
    Modelo: vikhyatk/moondream2 (~1.8B parámetros)
    """
    
    def __init__(self, use_float16: bool = False):
        """
        Inicializa Moondream2.
        
        Args:
            use_float16: Si True, usa float16 (más rápido en CPUs modernas).
                        Si False, usa float32 (más compatible).
        """
        print("🧠 Cargando Moondream2 (Optimizado para CPU)...")
        
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError:
            raise ImportError("Se requieren torch y transformers. Instalar: pip install torch transformers")
        
        self.model_id = "vikhyatk/moondream2"
        self.revision = "2024-08-26"  # Versión estable más reciente
        
        # Determinar tipo de datos
        dtype = torch.float16 if use_float16 else torch.float32
        
        # Cache en volumen persistente
        cache_dir = os.environ.get("HF_HOME", "/app/models/hf_cache")
        os.makedirs(cache_dir, exist_ok=True)
        
        try:
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_id,
                revision=self.revision,
                trust_remote_code=True,
                torch_dtype=dtype,
                cache_dir=cache_dir,
                device_map="cpu"  # Forzar CPU
            )
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_id,
                revision=self.revision,
                cache_dir=cache_dir
            )
            self.available = True
            print("✅ Moondream2 cargado correctamente.")
        except Exception as e:
            print(f"❌ Error cargando Moondream2: {e}")
            self.model = None
            self.tokenizer = None
            self.available = False
    
    def _to_pil(self, image: Union[np.ndarray, Image.Image, bytes, str]) -> Image.Image:
        """
        Convierte cualquier formato de imagen a PIL Image.
        
        Args:
            image: Imagen en formato OpenCV (numpy), PIL, bytes o path
        
        Returns:
            PIL Image
        """
        if isinstance(image, Image.Image):
            return image
        elif isinstance(image, np.ndarray):
            # OpenCV a PIL
            if len(image.shape) == 3 and image.shape[2] == 3:
                # BGR a RGB
                image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            return Image.fromarray(image)
        elif isinstance(image, bytes):
            return Image.open(BytesIO(image))
        elif isinstance(image, str):
            if image.startswith("data:image"):
                # Base64
                base64_data = image.split(",", 1)[1]
                return Image.open(BytesIO(base64.b64decode(base64_data)))
            else:
                # Path
                return Image.open(image)
        else:
            raise ValueError(f"Formato de imagen no soportado: {type(image)}")
    
    def analyze_image(
        self, 
        image: Union[np.ndarray, Image.Image, bytes, str], 
        question: str = "Describe this image in detail."
    ) -> dict:
        """
        Analiza una imagen y responde una pregunta sobre ella.
        
        Args:
            image: Imagen en cualquier formato soportado
            question: Pregunta sobre la imagen
        
        Returns:
            dict con 'success', 'answer', 'error' (si aplica)
        """
        if not self.available:
            return {
                "success": False,
                "answer": None,
                "error": "Moondream2 no está disponible"
            }
        
        try:
            # Convertir a PIL
            pil_image = self._to_pil(image)
            
            # Redimensionar si es muy grande (para ahorrar RAM)
            max_size = 1024
            if max(pil_image.size) > max_size:
                pil_image.thumbnail((max_size, max_size), Image.LANCZOS)
            
            # Codificar imagen
            enc_image = self.model.encode_image(pil_image)
            
            # Obtener respuesta
            answer = self.model.answer_question(enc_image, question, self.tokenizer)
            
            return {
                "success": True,
                "answer": answer.strip(),
                "error": None
            }
            
        except Exception as e:
            return {
                "success": False,
                "answer": None,
                "error": str(e)
            }
    
    def batch_analyze(
        self, 
        image: Union[np.ndarray, Image.Image, bytes, str],
        questions: list[str]
    ) -> dict:
        """
        Analiza una imagen con múltiples preguntas.
        Eficiente: codifica la imagen una sola vez.
        
        Args:
            image: Imagen en cualquier formato soportado
            questions: Lista de preguntas
        
        Returns:
            dict con 'success', 'answers' (lista), 'error' (si aplica)
        """
        if not self.available:
            return {
                "success": False,
                "answers": [],
                "error": "Moondream2 no está disponible"
            }
        
        try:
            pil_image = self._to_pil(image)
            
            # Redimensionar si es muy grande
            max_size = 1024
            if max(pil_image.size) > max_size:
                pil_image.thumbnail((max_size, max_size), Image.LANCZOS)
            
            # Codificar imagen una sola vez
            enc_image = self.model.encode_image(pil_image)
            
            # Responder todas las preguntas
            answers = []
            for q in questions:
                answer = self.model.answer_question(enc_image, q, self.tokenizer)
                answers.append(answer.strip())
            
            return {
                "success": True,
                "answers": answers,
                "error": None
            }
            
        except Exception as e:
            return {
                "success": False,
                "answers": [],
                "error": str(e)
            }
    
    def suggest_detection_classes(
        self,
        image: Union[np.ndarray, Image.Image, bytes, str],
        user_context: str = None
    ) -> dict:
        """
        Analiza una imagen y sugiere qué clases COCO deberían detectarse.
        
        Args:
            image: Imagen en cualquier formato soportado
            user_context: Contexto adicional del usuario (ej: "esto es un estacionamiento")
        
        Returns:
            dict con descripción de escena, clases sugeridas y confianza
        """
        # Clases COCO disponibles para detección
        COCO_CLASSES = [
            'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', 'boat',
            'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench', 'bird', 'cat',
            'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe', 'backpack',
            'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee', 'skis', 'snowboard', 'sports ball',
            'kite', 'baseball bat', 'baseball glove', 'skateboard', 'surfboard', 'tennis racket',
            'bottle', 'wine glass', 'cup', 'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple',
            'sandwich', 'orange', 'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair',
            'couch', 'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse',
            'remote', 'keyboard', 'cell phone', 'microwave', 'oven', 'toaster', 'sink', 'refrigerator',
            'book', 'clock', 'vase', 'scissors', 'teddy bear', 'hair drier', 'toothbrush'
        ]
        
        if not self.available:
            return {
                "success": False,
                "scene_description": None,
                "suggested_classes": [],
                "all_visible_objects": [],
                "confidence": 0,
                "error": "Moondream2 no está disponible"
            }
        
        try:
            pil_image = self._to_pil(image)
            
            # Redimensionar si es muy grande
            max_size = 1024
            if max(pil_image.size) > max_size:
                pil_image.thumbnail((max_size, max_size), Image.LANCZOS)
            
            # Codificar imagen una sola vez
            enc_image = self.model.encode_image(pil_image)
            
            # Pregunta 1: Descripción general de la escena
            scene_q = "Describe this scene in detail. What type of location is this? What is the main activity or purpose of this place?"
            scene_desc = self.model.answer_question(enc_image, scene_q, self.tokenizer).strip()
            
            # Pregunta 2: Objetos visibles
            objects_q = "List ALL objects you can see in this image. Be comprehensive and list every visible item, person, or vehicle."
            objects_desc = self.model.answer_question(enc_image, objects_q, self.tokenizer).strip()
            
            # Pregunta 3: Si hay contexto del usuario, preguntamos específicamente
            if user_context:
                context_q = f"The user says this is: {user_context}. Based on this context and what you see, what specific objects should we look for?"
                context_desc = self.model.answer_question(enc_image, context_q, self.tokenizer).strip()
            else:
                context_desc = None
            
            # Analizar qué clases COCO están probablemente en la escena
            suggested = []
            objects_lower = objects_desc.lower()
            scene_lower = scene_desc.lower()
            context_lower = (context_desc or "").lower()
            combined_text = f"{objects_lower} {scene_lower} {context_lower}"
            
            # Mapeo de sinónimos comunes a clases COCO
            synonyms = {
                'person': ['people', 'man', 'woman', 'child', 'pedestrian', 'human', 'worker', 'employee'],
                'car': ['vehicle', 'automobile', 'sedan', 'suv', 'cars'],
                'truck': ['lorry', 'pickup', 'trucks', 'van'],
                'bicycle': ['bike', 'cyclist', 'bikes'],
                'motorcycle': ['motorbike', 'scooter', 'motorcycles'],
                'bus': ['buses', 'transit', 'coach'],
                'dog': ['dogs', 'puppy', 'canine'],
                'cat': ['cats', 'kitten', 'feline'],
                'chair': ['chairs', 'seating', 'seat'],
                'bottle': ['bottles', 'container'],
                'cell phone': ['phone', 'smartphone', 'mobile'],
                'laptop': ['computer', 'notebook'],
                'tv': ['television', 'monitor', 'screen'],
                'traffic light': ['signal', 'light', 'stoplight'],
            }
            
            for coco_class in COCO_CLASSES:
                # Buscar clase directamente
                if coco_class in combined_text:
                    suggested.append(coco_class)
                    continue
                
                # Buscar sinónimos
                if coco_class in synonyms:
                    for synonym in synonyms[coco_class]:
                        if synonym in combined_text:
                            suggested.append(coco_class)
                            break
            
            # Agregar clases por contexto de escena
            scene_class_hints = {
                'parking': ['car', 'truck', 'motorcycle', 'person', 'bicycle'],
                'street': ['car', 'person', 'bicycle', 'motorcycle', 'bus', 'truck', 'traffic light', 'stop sign'],
                'office': ['person', 'chair', 'laptop', 'cell phone', 'keyboard', 'mouse', 'tv'],
                'kitchen': ['person', 'bottle', 'cup', 'bowl', 'fork', 'knife', 'spoon', 'microwave', 'oven', 'refrigerator', 'sink'],
                'living room': ['person', 'couch', 'tv', 'remote', 'chair', 'potted plant', 'clock', 'vase'],
                'restaurant': ['person', 'chair', 'dining table', 'cup', 'bottle', 'bowl', 'fork', 'knife', 'spoon'],
                'warehouse': ['person', 'truck', 'forklift', 'backpack'],
                'entrance': ['person', 'backpack', 'handbag', 'suitcase'],
                'store': ['person', 'backpack', 'handbag', 'bottle', 'cell phone'],
                'outdoor': ['person', 'car', 'bicycle', 'dog', 'bird', 'bench'],
            }
            
            for context_key, classes in scene_class_hints.items():
                if context_key in combined_text:
                    for cls in classes:
                        if cls not in suggested:
                            suggested.append(cls)
            
            # Siempre incluir 'person' si hay indicios de actividad humana
            human_indicators = ['activity', 'working', 'walking', 'standing', 'sitting', 'someone', 'people']
            if any(ind in combined_text for ind in human_indicators) and 'person' not in suggested:
                suggested.insert(0, 'person')
            
            # Calcular confianza basada en cuántas clases coinciden
            confidence = min(100, len(suggested) * 15) if suggested else 30
            
            return {
                "success": True,
                "scene_description": scene_desc,
                "objects_found": objects_desc,
                "context_analysis": context_desc,
                "suggested_classes": list(set(suggested)),  # Eliminar duplicados
                "confidence": confidence,
                "error": None
            }
            
        except Exception as e:
            return {
                "success": False,
                "scene_description": None,
                "suggested_classes": [],
                "confidence": 0,
                "error": str(e)
            }

    def validate_detection(
        self,
        image: Union[np.ndarray, Image.Image],
        detected_objects: list[str],
        context_prompt: str = None
    ) -> dict:
        """
        Valida detecciones de YOLO usando comprensión visual.
        Útil para reducir falsos positivos.
        
        Args:
            image: Imagen original
            detected_objects: Lista de objetos detectados por YOLO
            context_prompt: Contexto adicional (opcional)
        
        Returns:
            dict con validación y contexto
        """
        if not detected_objects:
            return {
                "success": True,
                "validation": "No objects to validate",
                "context": None,
                "likely_false_positives": []
            }
        
        objects_str = ", ".join(detected_objects)
        
        questions = [
            f"I detected these objects: {objects_str}. Do you see them in the image? Answer yes or no for each.",
            "Describe the general scene in this image in one sentence.",
        ]
        
        if context_prompt:
            questions.append(context_prompt)
        
        result = self.batch_analyze(image, questions)
        
        if not result["success"]:
            return {
                "success": False,
                "validation": None,
                "context": None,
                "error": result["error"]
            }
        
        return {
            "success": True,
            "validation": result["answers"][0],
            "context": result["answers"][1],
            "custom_response": result["answers"][2] if len(questions) > 2 else None,
            "likely_false_positives": []  # TODO: Parse validation response
        }


def get_vlm_analyzer(lazy: bool = True) -> Optional[MoondreamAnalyzer]:
    """
    Obtiene la instancia singleton del analizador VLM.
    
    Args:
        lazy: Si True, solo carga cuando se necesita por primera vez
    
    Returns:
        MoondreamAnalyzer o None si lazy=True y no ha sido inicializado
    """
    global _vlm_instance
    
    if _vlm_instance is None and not lazy:
        _vlm_instance = MoondreamAnalyzer()
    
    return _vlm_instance


def init_vlm_analyzer(use_float16: bool = False) -> MoondreamAnalyzer:
    """
    Inicializa el analizador VLM (forzado).
    Usar al inicio del worker si se quiere pre-cargar el modelo.
    
    Args:
        use_float16: Usar precisión reducida para mayor velocidad
    
    Returns:
        MoondreamAnalyzer
    """
    global _vlm_instance
    
    if _vlm_instance is None:
        _vlm_instance = MoondreamAnalyzer(use_float16=use_float16)
    
    return _vlm_instance


# Preguntas predefinidas para casos comunes
class VLMPrompts:
    """Prompts predefinidos para casos de uso comunes"""
    
    # Satelital
    SATELLITE_GENERAL = "Describe what you see in this satellite image. Include terrain type, vegetation, and any structures."
    SATELLITE_FLOOD = "Does this satellite image show signs of flooding or water accumulation? Describe what you see."
    SATELLITE_CONSTRUCTION = "Are there any construction sites, buildings, or infrastructure visible in this satellite image?"
    SATELLITE_DEFORESTATION = "Does this image show signs of deforestation or land clearing?"
    SATELLITE_AGRICULTURE = "Describe the agricultural activity visible in this satellite image if any."
    
    # Seguridad
    SECURITY_SCENE = "Describe this security camera scene. What activity is happening?"
    SECURITY_PEOPLE = "How many people do you see? What are they doing?"
    SECURITY_VEHICLES = "What vehicles are visible and what is their status (moving, parked, etc.)?"
    SECURITY_ANOMALY = "Is there anything unusual or potentially concerning in this scene?"
    
    # Tráfico
    TRAFFIC_DENSITY = "Estimate the traffic density in this image: light, moderate, or heavy?"
    TRAFFIC_INCIDENTS = "Are there any traffic incidents, accidents, or obstructions visible?"
    
    # Validación
    VALIDATE_OBJECTS = "I detected {objects}. Do you confirm seeing these objects? Answer with yes/no for each."
