import numpy as np
from .base import ISkillEvaluator
from ..domain.models import FrameData

class TechnicalEvaluator(ISkillEvaluator):
    def __init__(self):
        # Estados de Juggling
        self.juggles = 0
        self.last_hit_frame_idx = -100
        self.frame_counter = 0
        self.last_hit_leg = "N/A"
        
        # Estados de Dribbling/Pase
        self.dribbling_time = 0
        self.passes_detected = 0
        self.shots_detected = 0
        self.control_quality = 100 
        
        # Umbrales originales restaurados
        self.DRIBBLE_DIST_M = 0.7
        self.PASS_SPEED_MS = 3.0
        self.SHOT_SPEED_MS = 15.0 

    def process_frame(self, data: FrameData):
        self.frame_counter += 1
        
        if not data.ball or not data.player: return

        scale = data.scale_px_per_cm
        ball_y = data.ball.position.y
        velocity_y = data.ball.velocity.y
        
        # Altura del balón respecto al suelo (o a los pies si suelo no fiable)
        feet_y_avg = (data.player.feet["L"].y + data.player.feet["R"].y) / 2
        floor_ref = data.ground_y if data.ground_y > 0 else feet_y_avg
        
        height_cm = (floor_ref - ball_y) / scale

        # --- LÓGICA DE JUGGLING (Restaurada del original) ---
        # 1. Altura mínima para considerar juggling (> 15cm)
        if height_cm > 15:
            # 2. Detectar contacto: Cambio brusco de velocidad hacia arriba
            # (velocity_y es positivo hacia abajo en imagen, negativo hacia arriba)
            # En el original: velocity_y < -2.0 significaba "subiendo rápido"
            is_contact = (velocity_y < -2.0)
            
            hit_L = False
            hit_R = False
            
            # Chequeo Pie Izquierdo
            if data.player.feet_confidence["L"] > 0.4: # Confianza
                dx = abs(data.player.feet["L"].x - data.ball.position.x) / scale
                dy = abs(data.player.feet["L"].y - ball_y) / scale
                # dz ignorado por ahora si no hay depth real, asumimos plano 2D cercano
                
                # Condición original: (contacto Y cerca) O (muy cerca independientemente de vel)
                if ((is_contact and dx < 25 and dy < 30) or (dx < 15 and dy < 10)):
                    hit_L = True

            # Chequeo Pie Derecho
            if data.player.feet_confidence["R"] > 0.4:
                dx = abs(data.player.feet["R"].x - data.ball.position.x) / scale
                dy = abs(data.player.feet["R"].y - ball_y) / scale
                
                if ((is_contact and dx < 25 and dy < 30) or (dx < 15 and dy < 10)):
                    hit_R = True
            
            # Debounce: Evitar contar el mismo toque varias veces (mínimo 10 frames entre toques)
            if (hit_L or hit_R) and (self.frame_counter - self.last_hit_frame_idx) > 10:
                self.juggles += 1
                self.last_hit_frame_idx = self.frame_counter
                
                if hit_L and hit_R: self.last_hit_leg = "Simul"
                elif hit_L: self.last_hit_leg = "Izq"
                else: self.last_hit_leg = "Der"

        # --- LÓGICA DE DRIBBLING / PASE (Suelo) ---
        elif height_cm <= 15:
            # Distancia euclidiana a los pies
            dist_foot = self._min_dist(data.player.feet, data.ball.position) / scale
            
            # Si el jugador se mueve rápido y el balón está cerca
            if data.player.velocity > 1.5 and dist_foot < 60: # 60cm
                # Asumimos delta_time aprox 1/30 (0.033) si no viene en data
                dt = 0.033 
                self.dribbling_time += dt
            
            # TODO: Lógica de pase aquí

    def get_metrics(self):
        return {
            "juggles": self.juggles,
            "last_hit_leg": self.last_hit_leg,
            "dribble_sec": round(self.dribbling_time, 2),
            "control_quality": self.control_quality
        }

    def _min_dist(self, feet, ball_pos):
        d_l = np.linalg.norm(np.array([feet["L"].x - ball_pos.x, feet["L"].y - ball_pos.y]))
        d_r = np.linalg.norm(np.array([feet["R"].x - ball_pos.x, feet["R"].y - ball_pos.y]))
        return min(d_l, d_r)