from dataclasses import dataclass
from typing import Dict, List, Optional
import numpy as np

@dataclass
class Point3D:
    x: float
    y: float
    z: float

@dataclass
class PlayerState:
    feet: Dict[str, Point3D]
    center_of_mass: Point3D  # Clave para meditación (estabilidad)
    nose: Point3D            # Clave para "mirada al frente"
    velocity: float
    posture_stability: float # 0.0 (moviéndose) a 1.0 (estatua)

@dataclass
class BallState:
    position: Point3D
    velocity: Point3D
    is_controlled: bool
    speed: float = 0.0

@dataclass
class AudioState:
    is_speaking: bool
    transcribed_text: str    # Texto detectado en este frame/ventana
    volume_level: float      # Para detectar gritos o silencio

@dataclass
class FrameData:
    timestamp: float
    player: Optional[PlayerState]
    ball: Optional[BallState]
    audio: Optional[AudioState] # Nuevo campo
    scale_px_per_cm: float
    delta_time: float = 0.033 # Default to ~30fps
    ground_y: float = 0.0
