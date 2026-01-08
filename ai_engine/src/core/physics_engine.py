import numpy as np
from typing import Optional, List, Any, Dict
from ..domain.models import FrameData, PlayerState, BallState, AudioState, Point3D

class PhysicsEngine:
    def __init__(self):
        self.history_com = [] # Historial centro de masa
        self.px_per_cm = 2.0
        self.last_timestamp = 0.0
        self._prev_player_com = None
        self._prev_ball_pos = None
    
    def process(self, raw_pose: Any, raw_ball: Any, raw_audio: Optional[Dict] = None, floor_y: float = 0.0, timestamp: float = 0.0) -> FrameData:
        """
        Procesa datos crudos y aplica física para limpiar y calcular métricas derivadas.
        """
        scale = self.px_per_cm
        
        # 1. Procesar Pose
        player_state = None
        if raw_pose:
            player_state = self._process_pose(raw_pose)
            
        # 2. Procesar Ball
        ball_state = None
        if raw_ball:
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

        # 5. Velocidades y velocidades del balón
        if player_state and self._prev_player_com:
            dist_px = np.linalg.norm([player_state.center_of_mass.x - self._prev_player_com.x,
                                      player_state.center_of_mass.y - self._prev_player_com.y])
            player_state.velocity = self._px_to_m(dist_px) / dt
        if ball_state and self._prev_ball_pos:
            dist_px = np.linalg.norm([ball_state.position.x - self._prev_ball_pos.x,
                                      ball_state.position.y - self._prev_ball_pos.y])
            ball_state.speed = self._px_to_m(dist_px) / dt

        self._prev_player_com = player_state.center_of_mass if player_state else self._prev_player_com
        self._prev_ball_pos = ball_state.position if ball_state else self._prev_ball_pos

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
        """
        raw_pose se espera como dict con claves 'kpts' (lista de puntos) y 'box'.
        kpts indexados al estilo COCO: 0 nariz, 11/12 cadera, 15/16 tobillos.
        """
        if not isinstance(raw_pose, dict) or "kpts" not in raw_pose:
            return None

        kpts = raw_pose.get("kpts", [])
        def _pt(idx):
            if idx < len(kpts):
                kp = kpts[idx]
                return Point3D(float(kp.get("x", 0.0)), float(kp.get("y", 0.0)), 0.0)
            return Point3D(0.0, 0.0, 0.0)

        hip_l, hip_r = _pt(11), _pt(12)
        com = Point3D(
            x=(hip_l.x + hip_r.x) / 2.0,
            y=(hip_l.y + hip_r.y) / 2.0,
            z=0.0
        )

        return PlayerState(
            feet={"L": _pt(15), "R": _pt(16)},
            center_of_mass=com,
            nose=_pt(0),
            velocity=0.0,
            posture_stability=0.0
        )

    def _process_ball(self, raw_ball) -> BallState:
         """
         raw_ball esperado como [x, y, w, h, score].
         """
         if not isinstance(raw_ball, (list, tuple)) or len(raw_ball) < 4:
             return None

         x, y, w, h = raw_ball[:4]
         pos = Point3D(float(x + w/2), float(y + h), 0.0)
         return BallState(
             position=pos,
             velocity=Point3D(0.0, 0.0, 0.0),
             is_controlled=False,
             speed=0.0
         )

    def _px_to_m(self, dist_px: float) -> float:
        return (dist_px / self.px_per_cm) / 100.0 if self.px_per_cm > 0 else 0.0
