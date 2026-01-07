import time
import numpy as np
from .base import ISkillEvaluator
from ..domain.models import FrameData

class TacticalEvaluator(ISkillEvaluator):
    def __init__(self):
        self.scans_count = 0
        self.reaction_times = []
        self.last_nose_x = 0
        self.is_scanning = False
        
        # Estado para test de reacción
        self.stimulus_time = 0
        self.waiting_reaction = False

    def trigger_stimulus(self):
        """Llamar a esto para iniciar un test de reacción (ej. sonido silbato)"""
        self.stimulus_time = time.time()
        self.waiting_reaction = True

    def process_frame(self, data: FrameData):
        if not data.player: return

        # 1. VISIÓN (Scanning / Checking Shoulders)
        nose = data.player.nose
        diff = abs(nose.x - self.last_nose_x)
        if diff > 10: # Umbral de movimiento de cabeza
            if not self.is_scanning:
                self.scans_count += 1
                self.is_scanning = True
        else:
            self.is_scanning = False
        self.last_nose_x = nose.x

        # 2. TOMA DE DECISIONES (Tiempo de Reacción)
        if self.waiting_reaction:
            # Si el jugador se empieza a mover rápido (arranca el sprint)
            if data.player.velocity > 0.5: # m/s (asumiendo m/s)
                reaction_sec = data.timestamp - self.stimulus_time
                self.reaction_times.append(reaction_sec)
                self.waiting_reaction = False

    def get_metrics(self):
        avg_reaction = np.mean(self.reaction_times) if self.reaction_times else 0
        return {
            "field_scans": self.scans_count,
            "avg_reaction_time_ms": round(avg_reaction * 1000, 0)
        }
