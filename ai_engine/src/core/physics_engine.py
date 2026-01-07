import numpy as np
from typing import Optional, List, Any
from ..domain.models import FrameData, PlayerState, BallState, AudioState, Point3D

class PhysicsEngine:
    def __init__(self):
        self.history_com = [] # Historial centro de masa
        self.px_per_cm = 2.0
        self.last_timestamp = 0.0
    
    def process(self, raw_pose: Any, raw_ball: Any, raw_audio: Optional[Dict] = None, floor_y: float = 0.0, timestamp: float = 0.0) -> FrameData:
        """
        Procesa datos crudos y aplica física para limpiar y calcular métricas derivadas.
        """
        scale = self.px_per_cm
        
        # 1. Procesar Pose
        player_state = None
        if raw_pose:
            # TODO: Adaptar según la estructura real de raw_pose (Keypoints)
            # Placeholder conversion
            player_state = self._process_pose(raw_pose)
            
        # 2. Procesar Ball
        ball_state = None
        if raw_ball:
            # TODO: Adaptar según raw_ball (Bounding Box)
             ball_state = self._process_ball(raw_ball)

        # 3. Calcular Estabilidad (Para Meditación)
        stability_score = 0.0
        if player_state:
            self.history_com.append(player_state.center_of_mass)
            if len(self.history_com) > 30:
                self.history_com.pop(0)
            
            # Si la varianza de la posición del CoM en los últimos frames es baja, 
            # stability_score tiende a 1.0
            if len(self.history_com) > 5:
                # Calculo varianza simple de la magnitud
                coms = [np.linalg.norm([p.x, p.y]) for p in self.history_com]
                variance = np.var(coms)
                # Normalizar: Varianza 0 -> 1.0, Varianza alta -> 0.0
                stability_score = max(0.0, 1.0 - (variance / 100.0))
            
            player_state.posture_stability = stability_score

        # 4. Procesar Audio (Simulacion o Real)
        audio_state = None
        if raw_audio:
            audio_state = AudioState(
                is_speaking=raw_audio.get('is_speaking', False), 
                transcribed_text=raw_audio.get('text', ""), 
                volume_level=raw_audio.get('volume', 0.0)
            )

        dt = timestamp - self.last_timestamp if self.last_timestamp > 0 else 0.033
        if dt <= 0: dt = 0.033
        self.last_timestamp = timestamp

        return FrameData(
            timestamp=timestamp, 
            player=player_state, 
            ball=ball_state, 
            audio=audio_state,
            scale_px_per_cm=scale,
            delta_time=dt,
            ground_y=floor_y
        )

    def _process_pose(self, raw_pose) -> PlayerState:
        # TODO: Implementar lógica real de parseo de keypoints
        # Mockup
        return PlayerState(
            feet={"L": Point3D(0,0,0), "R": Point3D(0,0,0)},
            center_of_mass=Point3D(0,0,0),
            nose=Point3D(0,0,0),
            velocity=0.0,
            posture_stability=0.0
        )

    def _process_ball(self, raw_ball) -> BallState:
         # TODO: Implementar lógica real
         return BallState(
             position=Point3D(0,0,0),
             velocity=Point3D(0,0,0),
             is_controlled=False,
             speed=0.0
         )
