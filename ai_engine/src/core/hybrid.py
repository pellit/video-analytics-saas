"""
Hybrid Integration Module - YOLO + Moondream2
Combina detección YOLO con validación VLM para reducir falsos positivos
y generar alertas inteligentes con contexto.
"""

import cv2
import json
import time
import numpy as np
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass, asdict
from enum import Enum


class AlertSeverity(Enum):
    """Niveles de severidad de alertas"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class HybridDetection:
    """Resultado de detección híbrida YOLO + VLM"""
    class_name: str
    confidence: float
    bbox: List[float]
    vlm_validated: bool = False
    vlm_context: Optional[str] = None
    is_false_positive: bool = False
    
    def to_dict(self):
        return asdict(self)


@dataclass
class SmartAlert:
    """Alerta inteligente con contexto VLM"""
    alert_type: str
    severity: AlertSeverity
    message: str
    detections: List[Dict]
    scene_context: str
    confidence_score: float
    timestamp: str
    camera_id: Optional[int] = None
    zone_id: Optional[int] = None
    recommended_action: Optional[str] = None
    
    def to_dict(self):
        d = asdict(self)
        d['severity'] = self.severity.value
        return d


class HybridAnalyzer:
    """
    Analizador híbrido que combina:
    - Detección YOLO (rápida, objetos específicos)
    - Interpretación Moondream (contexto semántico)
    
    Casos de uso:
    1. Validación de detecciones (reducir falsos positivos)
    2. Generación de alertas con contexto
    3. Análisis de escenas complejas
    """
    
    def __init__(self, detector=None, vlm=None):
        """
        Args:
            detector: Instancia del detector YOLO/RT-DETR
            vlm: Instancia de MoondreamAnalyzer
        """
        self.detector = detector
        self.vlm = vlm
        
        # Configuración de alertas
        self.alert_rules = {
            'person_in_restricted': {
                'severity': AlertSeverity.HIGH,
                'min_confidence': 0.6,
                'vlm_validation': True,
                'vlm_prompt': "Is there a person in a restricted or unusual area? Describe what they are doing."
            },
            'crowd_detected': {
                'severity': AlertSeverity.MEDIUM,
                'min_persons': 5,
                'vlm_validation': True,
                'vlm_prompt': "How many people are visible? Is this a crowd? What are they doing?"
            },
            'vehicle_anomaly': {
                'severity': AlertSeverity.MEDIUM,
                'classes': ['car', 'truck', 'bus'],
                'vlm_validation': True,
                'vlm_prompt': "Are there any vehicles in unusual positions or locations?"
            },
            'satellite_change': {
                'severity': AlertSeverity.MEDIUM,
                'vlm_validation': True,
                'vlm_prompt': "What changes or activities do you see in this satellite image?"
            }
        }
    
    def set_detector(self, detector):
        """Configurar detector YOLO/RT-DETR"""
        self.detector = detector
    
    def set_vlm(self, vlm):
        """Configurar VLM Moondream"""
        self.vlm = vlm
    
    def detect_and_validate(
        self,
        image: np.ndarray,
        validate_with_vlm: bool = True,
        confidence_threshold: float = 0.5
    ) -> Dict[str, Any]:
        """
        Detecta objetos con YOLO y opcionalmente valida con VLM.
        
        Args:
            image: Imagen OpenCV (BGR)
            validate_with_vlm: Si True, valida detecciones con Moondream
            confidence_threshold: Umbral de confianza mínimo
        
        Returns:
            {
                'detections': [...],
                'scene_context': '...',
                'validated_count': N,
                'false_positive_count': N
            }
        """
        if self.detector is None:
            return {'error': 'Detector not configured', 'detections': []}
        
        # 1. Detección YOLO
        raw_detections = self.detector.detect(image)
        
        # Filtrar por confianza
        filtered = [d for d in raw_detections if d.confidence >= confidence_threshold]
        
        # Convertir a formato HybridDetection
        hybrid_detections = []
        for det in filtered:
            hybrid_detections.append(HybridDetection(
                class_name=det.class_name,
                confidence=det.confidence,
                bbox=list(det.bbox)
            ))
        
        scene_context = None
        validated_count = 0
        false_positive_count = 0
        
        # 2. Validación VLM (si habilitada y disponible)
        if validate_with_vlm and self.vlm and self.vlm.available and hybrid_detections:
            # Obtener contexto de la escena
            context_result = self.vlm.analyze_image(
                image,
                "Describe this scene briefly. What objects and activities do you see?"
            )
            
            if context_result['success']:
                scene_context = context_result['answer']
            
            # Validar objetos detectados
            detected_classes = list(set(d.class_name for d in hybrid_detections))
            validation_result = self.vlm.validate_detection(
                image,
                detected_classes
            )
            
            if validation_result['success']:
                validation_text = validation_result.get('validation', '').lower()
                
                # Marcar detecciones según validación
                for det in hybrid_detections:
                    class_lower = det.class_name.lower()
                    if 'yes' in validation_text and class_lower in validation_text:
                        det.vlm_validated = True
                        validated_count += 1
                    elif 'no' in validation_text and class_lower in validation_text:
                        det.is_false_positive = True
                        false_positive_count += 1
                    else:
                        # No se puede determinar, asumir válido
                        det.vlm_validated = True
                        validated_count += 1
                
                det.vlm_context = validation_result.get('context')
        
        return {
            'detections': [d.to_dict() for d in hybrid_detections],
            'scene_context': scene_context,
            'validated_count': validated_count,
            'false_positive_count': false_positive_count,
            'total_detections': len(hybrid_detections)
        }
    
    def generate_smart_alert(
        self,
        image: np.ndarray,
        detections: List[Dict],
        alert_type: str = 'general',
        camera_id: Optional[int] = None,
        zone_id: Optional[int] = None
    ) -> Optional[SmartAlert]:
        """
        Genera una alerta inteligente con contexto VLM.
        
        Args:
            image: Imagen de la escena
            detections: Detecciones previas
            alert_type: Tipo de alerta (person_in_restricted, crowd_detected, etc.)
            camera_id: ID de cámara (opcional)
            zone_id: ID de zona satelital (opcional)
        
        Returns:
            SmartAlert o None si no aplica
        """
        rule = self.alert_rules.get(alert_type, {})
        
        if not rule:
            return None
        
        severity = rule.get('severity', AlertSeverity.MEDIUM)
        min_confidence = rule.get('min_confidence', 0.5)
        
        # Filtrar detecciones relevantes
        relevant = [d for d in detections if d.get('confidence', 0) >= min_confidence]
        
        if not relevant:
            return None
        
        # Obtener contexto VLM
        scene_context = ""
        if rule.get('vlm_validation') and self.vlm and self.vlm.available:
            vlm_prompt = rule.get('vlm_prompt', "Describe what is happening in this image.")
            result = self.vlm.analyze_image(image, vlm_prompt)
            if result['success']:
                scene_context = result['answer']
        
        # Construir mensaje
        classes_found = list(set(d.get('class_name', 'unknown') for d in relevant))
        message = f"Detectado: {', '.join(classes_found)}"
        if scene_context:
            message += f". Contexto: {scene_context[:200]}"
        
        # Calcular confianza promedio
        avg_confidence = sum(d.get('confidence', 0) for d in relevant) / len(relevant)
        
        # Generar recomendación
        recommended_action = self._get_recommended_action(alert_type, relevant, scene_context)
        
        return SmartAlert(
            alert_type=alert_type,
            severity=severity,
            message=message,
            detections=relevant,
            scene_context=scene_context,
            confidence_score=avg_confidence,
            timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
            camera_id=camera_id,
            zone_id=zone_id,
            recommended_action=recommended_action
        )
    
    def _get_recommended_action(
        self,
        alert_type: str,
        detections: List[Dict],
        context: str
    ) -> str:
        """Genera recomendación basada en el tipo de alerta y contexto"""
        
        recommendations = {
            'person_in_restricted': "Verificar identidad y autorización de acceso.",
            'crowd_detected': "Monitorear comportamiento del grupo. Considerar notificar a seguridad.",
            'vehicle_anomaly': "Revisar estacionamiento y circulación vehicular.",
            'satellite_change': "Comparar con imágenes anteriores para detectar cambios significativos."
        }
        
        base_rec = recommendations.get(alert_type, "Revisar la situación detectada.")
        
        # Mejorar recomendación con contexto VLM
        if context:
            context_lower = context.lower()
            if 'emergency' in context_lower or 'danger' in context_lower:
                return f"⚠️ URGENTE: {base_rec} Contexto indica posible situación de emergencia."
            if 'normal' in context_lower or 'routine' in context_lower:
                return f"ℹ️ {base_rec} Situación aparentemente normal según análisis visual."
        
        return base_rec
    
    def analyze_satellite_zone(
        self,
        image: np.ndarray,
        zone_id: int,
        analysis_type: str = 'general'
    ) -> Dict[str, Any]:
        """
        Análisis especializado para zonas satelitales.
        Combina detección de objetos con interpretación semántica.
        
        Args:
            image: Imagen satelital
            zone_id: ID de la zona
            analysis_type: 'general', 'flood', 'construction', 'deforestation', 'agriculture'
        
        Returns:
            Resultado del análisis completo
        """
        prompts = {
            'general': "Describe what you see in this satellite image. Include terrain, structures, and any notable features.",
            'flood': "Is there flooding or water accumulation visible? Describe the water bodies and any affected areas.",
            'construction': "Are there construction sites or recent building activity visible? Describe any structures.",
            'deforestation': "Is there evidence of deforestation or land clearing? Describe vegetation patterns.",
            'agriculture': "What agricultural activity is visible? Describe crops, fields, and farming patterns."
        }
        
        result = {
            'zone_id': zone_id,
            'analysis_type': analysis_type,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'detections': [],
            'interpretation': None,
            'recommendations': []
        }
        
        # Detección de objetos
        if self.detector:
            detections = self.detector.detect(image)
            result['detections'] = [
                {'class_name': d.class_name, 'confidence': d.confidence, 'bbox': list(d.bbox)}
                for d in detections
            ]
        
        # Interpretación VLM
        if self.vlm and self.vlm.available:
            prompt = prompts.get(analysis_type, prompts['general'])
            vlm_result = self.vlm.analyze_image(image, prompt)
            
            if vlm_result['success']:
                result['interpretation'] = vlm_result['answer']
                
                # Generar recomendaciones basadas en interpretación
                interpretation_lower = vlm_result['answer'].lower()
                
                if analysis_type == 'flood' and 'water' in interpretation_lower:
                    result['recommendations'].append("Monitorear niveles de agua en próximas capturas")
                    
                if analysis_type == 'construction' and ('building' in interpretation_lower or 'construction' in interpretation_lower):
                    result['recommendations'].append("Seguir evolución de obras detectadas")
                    
                if analysis_type == 'deforestation' and ('clear' in interpretation_lower or 'deforest' in interpretation_lower):
                    result['recommendations'].append("⚠️ Posible actividad de deforestación detectada")
        
        return result


# Singleton global para uso en worker
_hybrid_analyzer: Optional[HybridAnalyzer] = None


def get_hybrid_analyzer() -> HybridAnalyzer:
    """Obtiene instancia singleton del analizador híbrido"""
    global _hybrid_analyzer
    if _hybrid_analyzer is None:
        _hybrid_analyzer = HybridAnalyzer()
    return _hybrid_analyzer


def init_hybrid_analyzer(detector=None, vlm=None) -> HybridAnalyzer:
    """Inicializa el analizador híbrido con detector y VLM"""
    global _hybrid_analyzer
    _hybrid_analyzer = HybridAnalyzer(detector=detector, vlm=vlm)
    return _hybrid_analyzer
