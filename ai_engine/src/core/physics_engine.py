import numpy as np
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Tuple
from ..domain.models import FrameData, PlayerState, BallState, Point3D

# --- Helpers del código original ---
def smooth_value(history: List[float], window_size: int = 5) -> float:
    """Media móvil simple para tiempo real."""
    if not history: return 0.0
    return float(np.mean(history[-window_size:]))

class BallCalibrator:
    """
    Sistema de calibración autónoma portado del servicio original.
    Calcula px_per_cm basado en la altura del jugador.
    """
    def __init__(self):
        self.SIZES = {3: 18.0, 4: 20.0, 5: 22.0}
        self.samples = [] 
        self.is_calibrated = False
        self.selected_size_id = 5
        self.real_diameter_cm = 22.0
        self.px_per_cm = 2.0  # Default fallback

    def add_sample(self, width_px):
        if 10 < width_px < 200: 
            self.samples.append(width_px)

    def finalize(self, player_h_px):
        if not self.samples: return
        median_px = float(np.median(self.samples))
        if median_px == 0: return

        scale_t5 = median_px / 22.0
        h_hyp = player_h_px / scale_t5
        
        # Estimar tamaño de balón basado en relación con altura jugador
        if h_hyp > 155: self.selected_size_id = 5
        elif 135 < h_hyp <= 155: self.selected_size_id = 4
        else: self.selected_size_id = 3
            
        self.real_diameter_cm = self.SIZES[self.selected_size_id]
        raw_scale = median_px / self.real_diameter_cm
        # Limites de seguridad para la escala
        self.px_per_cm = max(0.5, min(raw_scale, 10.0))
        self.is_calibrated = True

class PhysicsEngine:
    def __init__(self):
        self.calibrator = BallCalibrator()
        
        # Buffers para suavizado (History)
        self.history_size = 5
        self.ball_y_history = deque(maxlen=self.history_size)
        self.ball_speed_history = deque(maxlen=self.history_size)
        
        self.player_heights_buffer = []
        self.last_ball_y_smoothed = None
        self.floor_y = None

    def process(self, raw_pose, raw_ball, raw_audio, floor_y, timestamp) -> FrameData:
        """
        Limpia los datos crudos, calcula física y devuelve un FrameData estandarizado.
        """
        
        # 1. Calibración Continua
        # Usamos la altura de la bounding box del jugador para calibrar
        if raw_pose and "box" in raw_pose:
            p_h = raw_pose["box"][3] # Altura bbox
            self.player_heights_buffer.append(p_h)
            
            # Intentar calibrar cada 30 frames si aún no está listo
            if not self.calibrator.is_calibrated and len(self.player_heights_buffer) > 30:
                self.calibrator.finalize(np.median(self.player_heights_buffer))
            
            # Si hay balón, añadimos muestra para refinar
            if raw_ball:
                # raw_ball es un dict o objeto detection, asumimos bbox [x1, y1, x2, y2]
                # Calculamos ancho
                try:
                    bx1, by1, bx2, by2 = raw_ball.bbox
                    bw = bx2 - bx1
                    self.calibrator.add_sample(bw)
                except: pass

        scale = self.calibrator.px_per_cm
        
        # 2. Procesar Balón (Suavizado y Velocidad)
        ball_state = None
        if raw_ball:
            bbox = raw_ball.bbox
            bx, by = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2 # Centro X, Y abajo
            by_bottom = bbox[3] # Usamos la parte de abajo para contacto
            
            # Profundidad simulada o real si tuviéramos depth map
            # Por ahora, usamos 128 (medio) si no viene del servicio de profundidad
            bz = 128 
            
            # Suavizado Y
            self.ball_y_history.append(by_bottom)
            smoothed_y = smooth_value(list(self.ball_y_history))
            
            # Velocidad Vertical (Delta Y)
            velocity_y = 0.0
            if self.last_ball_y_smoothed is not None:
                velocity_y = smoothed_y - self.last_ball_y_smoothed
            
            self.last_ball_y_smoothed = smoothed_y
            
            ball_state = BallState(
                position=Point3D(bx, smoothed_y, bz),
                velocity=Point3D(0, velocity_y, 0), # Solo nos importa Y para juggling por ahora
                is_controlled=False # Se determina en evaluador
            )
        else:
            # Si se pierde el balón, reseteamos historial suavemente
            if len(self.ball_y_history) > 0:
                self.ball_y_history.popleft() 

        # 3. Procesar Jugador
        player_state = None
        if raw_pose:
            kpts = raw_pose.get("kpts", [])
            feet = {}
            
            # Indices COCO: 15 (Pie Izq), 16 (Pie Der)
            # Aseguramos formato Point3D
            if len(kpts) > 16:
                l_foot = kpts[15]
                r_foot = kpts[16]
                feet["L"] = Point3D(l_foot['x'], l_foot['y'], 128) # Z default
                feet["R"] = Point3D(r_foot['x'], r_foot['y'], 128)
                feet_conf = {"L": l_foot.get('conf', 0), "R": r_foot.get('conf', 0)}
            else:
                # Fallback si no hay keypoints completos
                feet = {"L": Point3D(0,0,0), "R": Point3D(0,0,0)}
                feet_conf = {"L": 0, "R": 0}

            # Centro de masa (aprox caderas 11 y 12)
            com = Point3D(0,0,0) 
            if len(kpts) > 12:
                cx = (kpts[11]['x'] + kpts[12]['x']) / 2
                cy = (kpts[11]['y'] + kpts[12]['y']) / 2
                com = Point3D(cx, cy, 128)
            
            # Nariz para táctica
            nose = Point3D(0,0,0)
            if len(kpts) > 0:
                nose = Point3D(kpts[0]['x'], kpts[0]['y'], 0)

            player_state = PlayerState(
                feet=feet,
                center_of_mass=com,
                nose=nose,
                velocity=0.0, # TODO: Calcular velocidad del jugador
                posture_stability=0.0,
                feet_confidence=feet_conf # Agregamos esto para filtrar
            )

        # 4. Audio (Placeholder)
        audio_state = None 
        if raw_audio:
            # Convertir dict simple a objeto AudioState
            pass

        return FrameData(
            timestamp=timestamp,
            player=player_state,
            ball=ball_state,
            audio=audio_state,
            scale_px_per_cm=scale,
            ground_y=floor_y
        )