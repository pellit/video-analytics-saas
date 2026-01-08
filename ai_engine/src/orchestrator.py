import os
import cv2
import time
import json
import wave
import tempfile
import subprocess
import logging
from typing import Dict, Any, Optional, List
from .domain.models import FrameData
from .core.physics_engine import PhysicsEngine
from .evaluators.technical import TechnicalEvaluator
from .evaluators.physical import PhysicalEvaluator
from .evaluators.tactical import TacticalEvaluator
from .evaluators.mental import MentalEvaluator
from .evaluators.crossfit import CrossfitEvaluator
from .services.hit_detection_service_optimized import HitDetectionServiceOptimized

# Placeholder imports if they are not strictly needed for this file but expected by the user's design
# Assuming usage of existing services
from .models.nanodet_plus import NanoDetPlusDetector
from .services.face_service import FaceEmbeddingService
from .services.superres_service import SuperResolutionService

logger = logging.getLogger(__name__)

MODELS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../models"))

class ServiceContainer:
    def __init__(self):
        self.nanodet = None
        self.hit_service = None
        self.ball_detector = None
        self.pose_detector = None
        self.face_service = None
        self.superres = None
        # self.pose = None 

    def attach_hit_service(self, hit_service: HitDetectionServiceOptimized):
        """Allow reusing an already-initialized hit detection service (det + pose)."""
        self.hit_service = hit_service
        self.ball_detector = getattr(hit_service, "det", None)
        self.pose_detector = getattr(hit_service, "pose", None)

    def initialize(self):
        logger.info("🚀 Initializing Perception Services...")
        
        # 1. Detección Base (NanoDet o YOLO)
        try:
            # Assuming these classes are available and work as expected
            self.nanodet = NanoDetPlusDetector(device='cpu') # Fallback ligero
            # self.nanodet.load_model() # Check if load_model is needed or if init does it
            logger.info("✅ NanoDet-Plus ready.")
        except Exception as e:
            logger.warning(f"⚠️ NanoDet error: {e}")

        # 1b. Detectores YOLOv8 (pose + balón) compartidos con hit_detection_service_optimized
        if not (self.ball_detector and self.pose_detector):
            try:
                self.hit_service = HitDetectionServiceOptimized(enable_depth=False)
                self.ball_detector = self.hit_service.det
                self.pose_detector = self.hit_service.pose
                logger.info("✅ YOLOv8 det/pose ready for coach pipeline.")
            except Exception as e:
                logger.warning(f"⚠️ YOLOv8 det/pose unavailable: {e}")

        # 2. Servicios de Rostro (Para consistencia)
        try:
            self.face_service = FaceEmbeddingService(
                face_detect_model_path=os.path.join(MODELS_DIR, 'face_detection_yunet_2023mar.onnx'),
                face_recognition_model_path=os.path.join(MODELS_DIR, 'face_recognition_sface_2021dec.onnx')
            )
            logger.info("✅ Face Services ready.")
        except Exception as e:
            logger.warning(f"⚠️ Face Service error: {e}")

        # 3. Super Resolución
        try:
            self.superres = SuperResolutionService(
                model_dir=os.path.join(MODELS_DIR),
                default_model_path=os.path.join(MODELS_DIR, 'ESPCN_x4.pb')
            )
        except Exception as e:
             logger.warning(f"⚠️ SuperRes error: {e}")

class CoachOrchestrator:
    def __init__(self, mode: str, config: dict, services: ServiceContainer):
        self.mode = mode
        self.physics = PhysicsEngine()
        self.evaluators = []
        self.services = services
        
        # Configurar Evaluadores según el modo
        if mode == "soccer":
            self.evaluators.append(TechnicalEvaluator()) # Juggling, Regate, Pase
            self.evaluators.append(PhysicalEvaluator())  # Velocidad, Resistencia
            self.evaluators.append(TacticalEvaluator())  # Escaneo, Reacción
            self.evaluators.append(MentalEvaluator())    # Consistencia, Enfoque
            
        elif mode == "fitness":
            self.evaluators.append(PhysicalEvaluator()) # Sentadillas, Saltos (ampliar PhysicalEvaluator)
            self.evaluators.append(MentalEvaluator())   # Respiración, Quietud
            
        elif mode == "meditation":
            mental = MentalEvaluator()
            mental.set_mode_meditation()
            self.evaluators.append(mental)
            
        elif mode == "challenge_speech":
            mental = MentalEvaluator()
            mental.set_mode_speech_challenge(target_phrase=config.get("phrase", ""))
            self.evaluators.append(mental)
            
        elif mode == "crossfit":
            # Crossfit: Reps counting (Squats/Burpees) + Intensity (Physical)
            self.evaluators.append(CrossfitEvaluator(exercise_type="wod_mix"))
            self.evaluators.append(PhysicalEvaluator()) # Monitor endurance/speed
            
        elif mode == "hyrox":
            # Hyrox: Functional (Burpees, Wallballs) + Running focus
            self.evaluators.append(CrossfitEvaluator(exercise_type="hyrox_station"))
            self.evaluators.append(PhysicalEvaluator())

    def process_video(self, video_path: str, frame_stride: int = 2):
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        
        # Extracción de Audio (Simulada o Implementada con ffmpeg + Vosk)
        audio_data = self._extract_audio_text(video_path) 
        
        current_frame_count = 0
        
        while True:
            ret, frame = cap.read()
            if not ret: break
            
            if current_frame_count % frame_stride != 0:
                current_frame_count += 1
                continue
                
            timestamp = current_frame_count / fps

            # 1. PERCEPCIÓN (Obtener datos crudos)
            raw_det = None
            raw_pose = None

            if self.services.ball_detector:
                try:
                    dets = self.services.ball_detector.detect(frame)
                    if dets: raw_det = dets[0]
                except Exception as e:
                    logger.debug(f"Ball detector failed: {e}")
            elif self.services.nanodet:
                try:
                    dets = self.services.nanodet.detect(frame)
                    if dets: raw_det = dets[0]
                except Exception as e:
                    logger.debug(f"NanoDet failed: {e}")

            if self.services.pose_detector:
                try:
                    poses = self.services.pose_detector.detect(frame)
                    if poses: raw_pose = poses[0]
                except Exception as e:
                    logger.debug(f"Pose detector failed: {e}")
            
            # 2. FÍSICA (Limpiar y normalizar)
            # Simulamos inyección de datos de audio sincronizados
            current_audio = audio_data.get(int(timestamp), None) 
            
            frame_data = self.physics.process(
                raw_pose=raw_pose, 
                raw_ball=raw_det, 
                raw_audio=current_audio,
                floor_y=int(frame.shape[0]*0.9), # O lógica de segmentación
                timestamp=timestamp
            )
            
            # 3. EVALUACIÓN (Aplicar reglas FIFA/Fitness)
            for evaluator in self.evaluators:
                evaluator.process_frame(frame_data)
                
            current_frame_count += 1
            
        cap.release()
        return self._compile_results()

    def _extract_audio_text(self, video_path) -> Dict[int, Any]:
        """
        Extrae audio, lo pasa a texto (Vosk/Whisper) y devuelve un mapa {segundo: texto}.
        Aquí se intenta Vosk si está disponible; si no, retorna {}.
        """
        model_path = os.environ.get("VOSK_MODEL_PATH")
        if not model_path or not os.path.exists(model_path):
            logger.info("Vosk model path not configured; skipping audio transcript.")
            return {}

        tmp_wav = None
        try:
            tmp_wav = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            tmp_wav.close()
            
            cmd = [
                "ffmpeg",
                "-y",
                "-i", video_path,
                "-ac", "1",
                "-ar", "16000",
                "-f", "wav",
                tmp_wav.name,
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            from vosk import Model, KaldiRecognizer

            wf = wave.open(tmp_wav.name, "rb")
            model = Model(model_path)
            rec = KaldiRecognizer(model, wf.getframerate())

            transcript: Dict[int, Any] = {}
            while True:
                data = wf.readframes(4000)
                if len(data) == 0:
                    break
                if rec.AcceptWaveform(data):
                    res = json.loads(rec.Result())
                    text = res.get("text", "").strip()
                    if text:
                        sec = int(wf.tell() / wf.getframerate())
                        transcript[sec] = {"text": text, "is_speaking": True, "volume": 1.0}

            final = json.loads(rec.FinalResult())
            if final.get("text"):
                sec = int(wf.getnframes() / max(wf.getframerate(), 1))
                transcript.setdefault(sec, {"text": final["text"], "is_speaking": True, "volume": 1.0})

            return transcript
        except Exception as e:
            logger.info(f"Audio transcription skipped ({e})")
            return {}
        finally:
            if tmp_wav and os.path.exists(tmp_wav.name):
                os.remove(tmp_wav.name)

    def _compile_results(self):
        results = {}
        for evaluator in self.evaluators:
            name = evaluator.__class__.__name__.replace("Evaluator", "").lower()
            results[name] = evaluator.get_metrics()
        return results
