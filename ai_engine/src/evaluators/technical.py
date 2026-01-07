import numpy as np
from .base import ISkillEvaluator
from ..domain.models import FrameData

class TechnicalEvaluator(ISkillEvaluator):
    def __init__(self):
        # Estados
        self.juggles = 0
        self.dribpling_time = 0
        self.passes_detected = 0
        self.shots_detected = 0
        self.control_quality = 100 # Empieza en 100%
        
        # Umbrales (Calibrables)
        self.DRIBBLE_DIST_M = 0.7
        self.PASS_SPEED_MS = 3.0
        self.SHOT_SPEED_MS = 15.0 

    def process_frame(self, data: FrameData):
        if not data.ball or not data.player: return

        # 1. Variables Físicas
        dist_ball_foot = self._min_dist(data.player.feet, data.ball.position)
        player_speed = data.player.velocity
        ball_speed = data.ball.speed
        
        # 2. DETECCIÓN DE REGATE
        if player_speed > 1.5 and dist_ball_foot < self.DRIBBLE_DIST_M:
            self.dribpling_time += data.delta_time

        # 3. DETECCIÓN DE PASE vs TIRO
        if dist_ball_foot > 1.0: # El balón ya salió
            if ball_speed > self.SHOT_SPEED_MS:
                self.shots_detected += 1 
                # (Aquí iría lógica de cooldown)
            elif ball_speed > self.PASS_SPEED_MS:
                self.passes_detected += 1

        # 4. CONTROL (Primer toque)
        if self._detect_impact(data) and ball_speed < 0.5:
             self.control_quality += 5 

    def get_metrics(self):
        return {
            "dribble_sec": round(self.dribpling_time, 2),
            "passes": self.passes_detected,
            "shots": self.shots_detected,
            "control_quality": self.control_quality
        }

    def _min_dist(self, feet, ball_pos):
        d_l = np.linalg.norm(np.array([feet["L"].x - ball_pos.x, feet["L"].y - ball_pos.y]))
        d_r = np.linalg.norm(np.array([feet["R"].x - ball_pos.x, feet["R"].y - ball_pos.y]))
        return min(d_l, d_r)
    
    def _detect_impact(self, data: FrameData) -> bool:
        # TODO: Implementar deteccion real de impacto
        return False
