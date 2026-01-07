from .base import ISkillEvaluator
from ..domain.models import FrameData

class MentalEvaluator(ISkillEvaluator):
    def __init__(self):
        self.mode = "IDLE" # MODOS: MEDITATION, SPEECH_CHALLENGE
        self.meditation_time = 0
        self.focus_score = 100
        
        # Para Challenges Hablados
        self.target_phrase = "" 
        self.words_detected = []
        self.challenge_completed = False

    def set_mode_meditation(self):
        self.mode = "MEDITATION"
        self.focus_score = 100

    def set_mode_speech_challenge(self, target_phrase):
        self.mode = "SPEECH_CHALLENGE"
        self.target_phrase = target_phrase.lower()
        self.words_detected = []

    def process_frame(self, data: FrameData):
        if not data.player: return

        # 1. LÓGICA DE MEDITACIÓN (Control Mental)
        if self.mode == "MEDITATION":
            # Penalizar si se mueve
            if data.player.posture_stability < 0.8:
                self.focus_score -= 1 # Pierde concentración
            
            # Penalizar si habla durante meditación
            if data.audio and data.audio.is_speaking:
                self.focus_score -= 2
            
            if self.focus_score > 0:
                self.meditation_time += 1 # Sumar tiempo (frames)

        # 2. LÓGICA DE CHALLENGE HABLADO (Lección/Países)
        elif self.mode == "SPEECH_CHALLENGE":
            if data.audio and data.audio.transcribed_text:
                text = data.audio.transcribed_text.lower()
                
                # Verificar si dijo lo correcto
                if text in self.target_phrase and text not in self.words_detected:
                    self.words_detected.append(text)
                
                # Chequear completitud
                required_words = self.target_phrase.split()
                if all(word in self.words_detected for word in required_words):
                    self.challenge_completed = True

    def get_metrics(self):
        return {
            "mode": self.mode,
            "focus_level": max(0, self.focus_score),
            "meditation_seconds": self.meditation_time / 30.0, # Asumiendo 30fps
            "speech_progress": f"{len(self.words_detected)}/{len(self.target_phrase.split()) if self.target_phrase else 0}",
            "challenge_success": self.challenge_completed
        }
