from typing import Any, Dict
from .base import ISkillEvaluator
from ..domain.models import FrameData

class CrossfitEvaluator(ISkillEvaluator):
    def __init__(self, exercise_type: str = "general"):
        self.exercise_type = exercise_type
        self.reps = 0
        self.state = "START"  # START, DESCENDING, BOTTOM, ASCENDING
        self.last_hip_y = 0.0
        self.rep_quality = [] # List of scores per rep (0-100)
        self.current_rep_lowest_y = 0.0
        
        # Umbrales simples (en coordenadas normalizadas o relativas)
        self.SQUAT_DEPTH_THRESHOLD = 0.0 # Se calibrará dinámicamente

    def process_frame(self, data: FrameData):
        if not data.player: return
        
        # Usamos hips para detectar movimiento vertical (sentadillas, burpees, box jumps)
        # Asumiendo que player.feet es un dict, idealmente deberíamos tener hips en player state
        # Como fallback usamos Center of Mass (CoM)
        current_y = data.player.center_of_mass.y
        
        # Simple State Machine para contar repeticiones (basado en Squats/Burpees)
        if self.state == "START":
            if current_y > self.last_hip_y + 10: # Bajando (Y crece hacia abajo en imagenes)
                self.state = "DESCENDING"
                self.current_rep_lowest_y = current_y

        elif self.state == "DESCENDING":
            if current_y > self.current_rep_lowest_y:
                 self.current_rep_lowest_y = current_y
            
            if current_y < self.last_hip_y - 5: # Empieza a subir significativamente
                self.state = "ASCENDING"

        elif self.state == "ASCENDING":
            if current_y < self.last_hip_y - 2: # Sigue subiendo
                pass
            elif current_y > self.last_hip_y + 2: # Vuelve a bajar o se estabiliza arriba
                # Fin de repetición
                self.reps += 1
                self.state = "START"
                self._evaluate_rep_quality(data)

        self.last_hip_y = current_y

    def _evaluate_rep_quality(self, data: FrameData):
        # Lógica simplificada de calidad
        # En una implementación real, verificaríamos "hip crease below knee"
        score = 100
        feet_y = (data.player.feet["L"].y + data.player.feet["R"].y) / 2
        
        # Si bajó lo suficiente (acercándose al suelo/pies)
        if data.scale_px_per_cm > 0:
            depth_cm = (feet_y - self.current_rep_lowest_y) / data.scale_px_per_cm
            # Ejemplo: Si la cadera bajó a menos de 50cm del suelo (muy bajo) -> Good Squat
            if depth_cm > 60: # Falta profundidad
                score -= 20
        
        self.rep_quality.append(max(0, score))

    def get_metrics(self) -> Dict[str, Any]:
        avg_quality = sum(self.rep_quality) / len(self.rep_quality) if self.rep_quality else 0
        return {
            "exercise": self.exercise_type,
            "reps_counted": self.reps,
            "avg_form_score": round(avg_quality, 1),
            "last_state": self.state
        }
