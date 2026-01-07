from .base import ISkillEvaluator
from ..domain.models import FrameData

class PhysicalEvaluator(ISkillEvaluator):
    def __init__(self):
        self.max_speed = 0.0
        self.total_distance = 0.0
        self.explosive_actions = 0 # Sprints o cambios de dirección
        self.jump_height_cm = 0.0
        self.last_com = None

    def process_frame(self, data: FrameData):
        if not data.player: return

        # 1. VELOCIDAD Y RESISTENCIA
        current_speed = data.player.velocity 
        if current_speed > self.max_speed:
            self.max_speed = current_speed
        
        # Distancia acumulada (Velocidad * tiempo)
        self.total_distance += current_speed * data.delta_time

        # 2. AGILIDAD (Cambio de Dirección)
        # TODO: Implementar logica de cambio de direccion
        pass
        
        # 3. POTENCIA (Salto Vertical)
        feet_y = (data.player.feet["L"].y + data.player.feet["R"].y) / 2
        floor_y = data.ground_y
        
        if data.scale_px_per_cm > 0:
            current_height = (floor_y - feet_y) / data.scale_px_per_cm
            if current_height > 20.0: # Más de 20cm del suelo es salto
                if current_height > self.jump_height_cm:
                    self.jump_height_cm = current_height

    def get_metrics(self):
        return {
            "top_speed_kmh": round(self.max_speed * 3.6, 2), # m/s a km/h
            "distance_m": round(self.total_distance, 1),
            "max_jump_cm": round(self.jump_height_cm, 1)
        }
