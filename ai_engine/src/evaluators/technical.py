import numpy as np
from .base import ISkillEvaluator
from ..domain.models import FrameData

class TechnicalEvaluator(ISkillEvaluator):
    def __init__(self):
        # Estados de Juggling
        self.juggles = 0
        self.count_left = 0
        self.count_right = 0
        self.count_simultaneous = 0
        self.last_hit_leg = "N/A"
        
        # Variables auxiliares
        self.last_hit_frame_idx = -100
        self.frame_counter = 0
        
        # Estados de Dribbling/Pase
        self.dribbling_time = 0
        self.passes_detected = 0
        self.shots_detected = 0
        self.control_quality = 100 
        self.final_state = "Parado"
        
        # Umbrales
        self.DRIBBLE_DIST_M = 0.7
        self.PASS_SPEED_MS = 3.0
        self.SHOT_SPEED_MS = 15.0 

    def process_frame(self, data: FrameData):
        self.frame_counter += 1
        
        if not data.ball or not data.player: 
            return

        scale = data.scale_px_per_cm
        # Usamos posiciones relativas
        ball_y = data.ball.position.y
        velocity_y = data.ball.velocity.y
        
        feet_y_avg = (data.player.feet["L"].y + data.player.feet["R"].y) / 2
        floor_ref = data.ground_y if data.ground_y > 0 else feet_y_avg
        
        height_cm = (floor_ref - ball_y) / scale

        # --- LÓGICA DE JUGGLING ---
        if height_cm > 15:
            # Detectar contacto (Velocidad negativa = subiendo)
            is_contact = (velocity_y < -2.0)
            
            hit_L = False
            hit_R = False
            
            # Chequeo Pie Izquierdo
            # Asumimos que data.player tiene feet_confidence (agregado en PhysicsEngine)
            conf_l = getattr(data.player, 'feet_confidence', {}).get("L", 1.0)
            if conf_l > 0.4:
                dx = abs(data.player.feet["L"].x - data.ball.position.x) / scale
                dy = abs(data.player.feet["L"].y - ball_y) / scale
                if ((is_contact and dx < 25 and dy < 30) or (dx < 15 and dy < 10)):
                    hit_L = True

            # Chequeo Pie Derecho
            conf_r = getattr(data.player, 'feet_confidence', {}).get("R", 1.0)
            if conf_r > 0.4:
                dx = abs(data.player.feet["R"].x - data.ball.position.x) / scale
                dy = abs(data.player.feet["R"].y - ball_y) / scale
                if ((is_contact and dx < 25 and dy < 30) or (dx < 15 and dy < 10)):
                    hit_R = True
            
            # Debounce y Conteo
            if (hit_L or hit_R) and (self.frame_counter - self.last_hit_frame_idx) > 10:
                self.juggles += 1
                self.last_hit_frame_idx = self.frame_counter
                
                if hit_L and hit_R: 
                    self.last_hit_leg = "Simul"
                    self.count_simultaneous += 1
                elif hit_L: 
                    self.last_hit_leg = "Izq"
                    self.count_left += 1
                else: 
                    self.last_hit_leg = "Der"
                    self.count_right += 1
            
            self.final_state = "Juggling"

        # --- LÓGICA DE DRIBBLING / PASE ---
        elif height_cm <= 15:
            dist_foot = self._min_dist(data.player.feet, data.ball.position) / scale
            if data.player.velocity > 1.5 and dist_foot < 60:
                self.dribbling_time += data.audio.volume_level if data.audio else 0.033 # Fallback delta time
                self.final_state = "Conducción"
            else:
                self.final_state = "Control/Suelo"

    def get_metrics(self):
        return {
            "total_juggles": self.juggles,
            "count_left": self.count_left,
            "count_right": self.count_right,
            "count_simultaneous": self.count_simultaneous,
            "last_hit_leg": self.last_hit_leg,
            "final_state": self.final_state,
            "dribble_sec": round(self.dribbling_time, 2),
            "passes": self.passes_detected,
            "shots": self.shots_detected,
            "control_quality": self.control_quality
        }

    def _min_dist(self, feet, ball_pos):
        d_l = np.linalg.norm(np.array([feet["L"].x - ball_pos.x, feet["L"].y - ball_pos.y]))
        d_r = np.linalg.norm(np.array([feet["R"].x - ball_pos.x, feet["R"].y - ball_pos.y]))
        return min(d_l, d_r)