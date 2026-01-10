import numpy as np
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Tuple
from ..domain.models import FrameData, PlayerState, BallState, Point3D, AudioState

# ==========================================
# 0. PREPARACIÓN MOTOR DE VOZ (VOSK)
# ==========================================
# PASO 1: Instalar librería -> pip install vosk
# PASO 2: Descargar modelos -> https://alphacephei.com/vosk/models
#         - vosk-model-small-es-0.42 (Español)
#         - vosk-model-small-en-us-0.15 (Inglés)
# PASO 3: Descomprimir en /app/ai_engine/models/vosk/

# try:
#     from vosk import Model, KaldiRecognizer
#     VOSK_AVAILABLE = True
# except ImportError:
#     VOSK_AVAILABLE = False

class VoiceProcessor:
    """
    Encapsula la complejidad de VOSK.
    Maneja el cambio de idioma y el reconocimiento parcial.
    Instrucciones para activar VOSK (Inglés/Español)
    Descargar Modelos:

    No incluyas los modelos en el repositorio (son pesados, ~50MB cada uno).

    Descárgalos de: https://alphacephei.com/vosk/models

    Crea la carpeta /app/ai_engine/models/vosk/ en tu contenedor.

    Descomprímelos ahí. Deberías tener carpetas llamadas vosk-model-small-es-0.42 y vosk-model-small-en-us-0.15.

    Instalar Dependencia:

    Asegúrate de que tu requirements.txt o Dockerfile tenga: vosk==0.3.45 (o superior).

    Habilitar en Código:

    En el archivo de arriba, descomenta el bloque try/except al inicio y el bloque dentro de VoiceProcessor.__init__.

    Puedes pasar dinámicamente el idioma (lang='es' o 'en') cuando instancies el PhysicsEngine si quieres soportar bilingüismo.
    """
    def __init__(self, models_dir="models/vosk", lang="es"):
        self.enabled = False # Cambiar a VOSK_AVAILABLE cuando se instale
        self.recognizer = None
        
        
        # Lógica de carga de modelos (DESCOMENTAR CUANDO TENGAS VOSK)
        # if self.enabled:
        #     try:
        #         model_path = f"{models_dir}/vosk-model-small-{lang}"
        #         print(f"[VOICE] Cargando modelo: {model_path}")
        #         self.model = Model(model_path)
        #         self.recognizer = KaldiRecognizer(self.model, 16000) # 16kHz sample rate
        #     except Exception as e:
        #         print(f"[VOICE] Error cargando modelo: {e}")
        #         self.enabled = False

    def process_audio_buffer(self, raw_audio_bytes) -> Tuple[bool, str]:
        """
        Retorna (is_speaking, text)
        """
        if not self.enabled or not raw_audio_bytes:
            return False, ""
        
        # if self.recognizer.AcceptWaveform(raw_audio_bytes):
        #     result = json.loads(self.recognizer.Result())
        #     text = result.get("text", "")
        #     return (len(text) > 0), text
        # else:
        #     # Reconocimiento parcial (para feedback rápido)
        #     partial = json.loads(self.recognizer.PartialResult())
        #     return True, partial.get("partial", "")
        
        return False, ""

# ==========================================
# 1. HERRAMIENTAS DE FÍSICA
# ==========================================

def smooth_value(history: List[float], window_size: int = 5) -> float:
    """Media móvil simple para suavizar ruido de detección."""
    if not history: return 0.0
    return float(np.mean(history[-window_size:]))

class BallCalibrator:
    """
    Sistema de calibración autónoma.
    Calcula px_per_cm basado en la altura del jugador detectada vs altura promedio (1.75m).
    """
    def __init__(self):
        self.SIZES = {3: 18.0, 4: 20.0, 5: 22.0}
        self.samples = [] 
        self.is_calibrated = False
        self.selected_size_id = 5
        self.px_per_cm = 2.0  # Valor por defecto seguro

    def add_sample(self, width_px):
        if 10 < width_px < 200: 
            self.samples.append(width_px)

    def finalize(self, player_h_px):
        if not self.samples: return
        median_px = float(np.median(self.samples))
        if median_px == 0: return

        # Asumimos balón tamaño 5 para la primera estimación
        scale_t5 = median_px / 22.0
        h_hyp = player_h_px / scale_t5
        
        # Ajuste fino basado en la altura resultante del jugador
        if h_hyp > 155: self.selected_size_id = 5
        elif 135 < h_hyp <= 155: self.selected_size_id = 4
        else: self.selected_size_id = 3
            
        real_diameter = self.SIZES[self.selected_size_id]
        raw_scale = median_px / real_diameter
        
        # Clamping de seguridad (evita escalas infinitas o cero)
        self.px_per_cm = max(0.5, min(raw_scale, 10.0))
        self.is_calibrated = True

class PhysicsEngine:
    def __init__(self):
        self.calibrator = BallCalibrator()
        self.voice_processor = VoiceProcessor() # Instancia el motor de voz
        
        # -- Historiales para Cálculo de Velocidad --
        self.history_size = 5
        
        # Balón
        self.ball_pos_history = deque(maxlen=self.history_size)
        self.last_ball_pos = None
        
        # Jugador
        self.player_com_history = deque(maxlen=self.history_size) # Centro de masa
        self.player_heights_buffer = []
        self.last_player_com = None
        self.floor_y = None

    def _calculate_velocity(self, current_pos: Point3D, last_pos: Point3D, fps=30.0) -> float:
        """Calcula velocidad escalar (pixeles/segundo)"""
        if last_pos is None: return 0.0
        dx = current_pos.x - last_pos.x
        dy = current_pos.y - last_pos.y
        # Distancia euclidiana * FPS
        return np.sqrt(dx**2 + dy**2) * fps

    def _calculate_stability(self, kpts) -> float:
        """
        Calcula estabilidad (0.0 a 1.0) comparando oscilación de hombros vs caderas.
        Crucial para Yoga/Meditación.
        """
        if len(kpts) < 13: return 0.0
        # Hombros (5,6) vs Caderas (11,12)
        shoulders_x = (kpts[5]['x'] + kpts[6]['x']) / 2
        hips_x = (kpts[11]['x'] + kpts[12]['x']) / 2
        
        # Si el torso está alineado verticalmente con caderas = estable
        deviation = abs(shoulders_x - hips_x)
        # Normalizar desviación (arbitrario: 50px es mucha desviación)
        score = max(0.0, 1.0 - (deviation / 50.0))
        return score

    def process(self, raw_pose, raw_ball, raw_audio, floor_y, timestamp) -> FrameData:
        """
        Pipeline principal de física.
        raw_audio: Buffer de bytes de audio crudo (PCM 16k mono).
        """
        
        # 1. AUTO-CALIBRACIÓN
        if raw_pose and "box" in raw_pose:
            p_h = raw_pose["box"][3] # Altura bbox
            self.player_heights_buffer.append(p_h)
            
            if not self.calibrator.is_calibrated and len(self.player_heights_buffer) > 30:
                self.calibrator.finalize(np.median(self.player_heights_buffer))
            
            if raw_ball and hasattr(raw_ball, 'bbox'):
                bx1, by1, bx2, by2 = raw_ball.bbox
                self.calibrator.add_sample(bx2 - bx1)

        scale = self.calibrator.px_per_cm
        
        # 2. FÍSICA DEL BALÓN
        ball_state = None
        if raw_ball:
            bbox = raw_ball.bbox
            bx, by = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2 
            bz = 128 # Placeholder Z
            
            current_pos = Point3D(bx, by, bz)
            
            # Velocidad
            speed_px = self._calculate_velocity(current_pos, self.last_ball_pos)
            velocity_vec = Point3D(0, 0, 0) # Vector simple por ahora
            
            if self.last_ball_pos:
                velocity_vec = Point3D(bx - self.last_ball_pos.x, by - self.last_ball_pos.y, 0)
            
            self.last_ball_pos = current_pos
            
            ball_state = BallState(
                position=current_pos,
                velocity=velocity_vec,
                speed=speed_px / scale, # cm/s reales
                is_controlled=False 
            )
        else:
            self.last_ball_pos = None

        # 3. FÍSICA DEL JUGADOR
        player_state = None
        if raw_pose:
            kpts = raw_pose.get("kpts", [])
            feet = {}
            
            # Extracción Pies (Coco 15, 16)
            l_foot = kpts[15] if len(kpts) > 15 else {'x':0, 'y':0, 'conf':0}
            r_foot = kpts[16] if len(kpts) > 16 else {'x':0, 'y':0, 'conf':0}
            
            feet["L"] = Point3D(l_foot['x'], l_foot['y'], 128)
            feet["R"] = Point3D(r_foot['x'], r_foot['y'], 128)
            feet_conf = {"L": l_foot.get('conf', 0), "R": r_foot.get('conf', 0)}

            # Extracción Centro de Masa (Caderas 11, 12)
            cx, cy = 0, 0
            if len(kpts) > 12:
                cx = (kpts[11]['x'] + kpts[12]['x']) / 2
                cy = (kpts[11]['y'] + kpts[12]['y']) / 2
            com = Point3D(cx, cy, 128)
            
            # Extracción Nariz
            nx, ny = (kpts[0]['x'], kpts[0]['y']) if len(kpts) > 0 else (0,0)
            nose = Point3D(nx, ny, 0)

            # Cálculo de Velocidad del Jugador
            player_speed_px = self._calculate_velocity(com, self.last_player_com)
            self.last_player_com = com

            # Cálculo de Estabilidad
            stability = self._calculate_stability(kpts)

            player_state = PlayerState(
                feet=feet,
                center_of_mass=com,
                nose=nose,
                velocity=player_speed_px / scale, # Velocidad real en cm/s
                posture_stability=stability,
                feet_confidence=feet_conf
            )

        # 4. PROCESAMIENTO DE VOZ (VOSK)
        # Aquí convertimos el audio crudo en un AudioState usable por MentalEvaluator
        audio_state = None 
        if raw_audio:
            # Procesamos el buffer con VOSK
            is_speaking, text = self.voice_processor.process_audio_buffer(raw_audio)
            
            # Calculamos volumen simple (RMS) para detectar gritos
            # Asumiendo audio int16
            volume = 0.0
            try:
                # Convertir bytes a numpy array para cálculo rápido
                audio_data = np.frombuffer(raw_audio, dtype=np.int16)
                if len(audio_data) > 0:
                    volume = np.sqrt(np.mean(audio_data**2))
            except: pass

            audio_state = AudioState(
                is_speaking=is_speaking,
                transcribed_text=text,
                volume_level=volume
            )

        return FrameData(
            timestamp=timestamp,
            player=player_state,
            ball=ball_state,
            audio=audio_state,
            scale_px_per_cm=scale,
            ground_y=floor_y
        )