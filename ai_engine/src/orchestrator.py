import os
import cv2
import time
import json
import logging
import numpy as np
from typing import Dict, Any, Optional, List
from .domain.models import FrameData
from .core.physics_engine import PhysicsEngine
from .evaluators.technical import TechnicalEvaluator
from .evaluators.physical import PhysicalEvaluator
from .evaluators.tactical import TacticalEvaluator
from .evaluators.mental import MentalEvaluator
from .services.hit_detection_service_optimized import HitDetectionServiceOptimized
# Imports de placeholders para que funcione la carga de servicios
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

    def attach_hit_service(self, hit_service: HitDetectionServiceOptimized):
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
        
        # --- Inicializar Evaluadores ---
        self.tech_eval = TechnicalEvaluator()
        self.phys_eval = PhysicalEvaluator()
        self.tact_eval = TacticalEvaluator()
        self.mental_eval = MentalEvaluator()
        
        # Agregamos siempre los básicos para tener stats completos
        self.evaluators.extend([self.tech_eval, self.phys_eval, self.tact_eval, self.mental_eval])
        
        if mode == "meditation":
            self.mental_eval.set_mode_meditation()
        elif mode == "challenge_speech":
            self.mental_eval.set_mode_speech_challenge(target_phrase=config.get("phrase", ""))

        # --- Acumuladores de Salida ---
        self.trajectory_3d = [] # Lista para guardar {frame, x, y, z}
        self.hit_images = []    # Lista para guardar imágenes base64

    def process_session(self, data_provider):
        """
        Nuevo bucle que consume un `IDataProvider` genérico.
        El `data_provider` ya debe devolver `FrameData` con la física aplicada.
        """
        frames_analyzed = 0
        start_time = time.time()

        try:
            while True:
                frame_data = data_provider.get_next_frame()
                if frame_data is None:
                    break

                # Guardar trayectoria
                if frame_data.ball:
                    self.trajectory_3d.append({
                        "t": frame_data.timestamp,
                        "x": int(frame_data.ball.position.x),
                        "y": int(frame_data.ball.position.y),
                        "z": int(frame_data.ball.position.z)
                    })

                # Evaluación
                for evaluator in self.evaluators:
                    try:
                        evaluator.process_frame(frame_data)
                    except Exception:
                        pass

                frames_analyzed += 1

        except Exception as e:
            logger.error(f"Error crítico en sesión: {e}")
        finally:
            try:
                data_provider.release()
            except Exception:
                pass

        duration = time.time() - start_time
        return self._compile_final_response(duration, 0, frames_analyzed)

    def process_video(self, video_path: str, frame_stride: int = 2):
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        frame_count_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration = frame_count_total / fps if fps else 0
        
        audio_data = {} # TODO: Integrar extracción real si es necesario
        
        current_frame_count = 0
        frames_analyzed = 0
        
        while True:
            ret, frame = cap.read()
            if not ret: break
            
            if current_frame_count % frame_stride != 0:
                current_frame_count += 1
                continue
                
            timestamp = current_frame_count / fps

            # 1. PERCEPCIÓN

            raw_det = None
            raw_pose = None

            if self.services.ball_detector:
                try:
                    dets = self.services.ball_detector.detect(frame)
                    if dets: 
                        raw_det = dets[0] # Ahora es un DetectionObject, no una lista
                except Exception as e: 
                    pass
            
            if self.services.pose_detector:
                try:
                    poses = self.services.pose_detector.detect(frame)
                    if poses: raw_pose = poses[0]
                except: pass
            
            # 2. FÍSICA
            current_audio = audio_data.get(int(timestamp), None)
            frame_data = self.physics.process(
                raw_pose=raw_pose, 
                raw_ball=raw_det, 
                raw_audio=current_audio,
                floor_y=int(frame.shape[0]*0.9),
                timestamp=timestamp
            )
            
            # 3. GUARDAR TRAYECTORIA (Requisito Crítico)
            if frame_data.ball:
                self.trajectory_3d.append({
                    "frame": current_frame_count,
                    "x": int(frame_data.ball.position.x),
                    "y": int(frame_data.ball.position.y),
                    "z": int(frame_data.ball.position.z)
                })

            # 4. EVALUACIÓN
            for evaluator in self.evaluators:
                evaluator.process_frame(frame_data)
                
            # TODO: Aquí podrías agregar lógica para guardar hit_images si hay evento
                
            current_frame_count += 1
            frames_analyzed += 1
            
        cap.release()
        
        # Compilar resultados finales con la estructura exacta solicitada
        return self._compile_final_response(duration, frame_count_total, frames_analyzed)

    def _compile_final_response(self, duration, total_frames, analyzed_frames):
        # Extraer métricas de los evaluadores específicos
        tech_metrics = self.tech_eval.get_metrics()
        mental_metrics = self.mental_eval.get_metrics()
        
        # Construir el objeto STATS plano que espera el frontend
        stats_object = {
            "total_juggles": tech_metrics.get("total_juggles", 0),
            "count_left": tech_metrics.get("count_left", 0),
            "count_right": tech_metrics.get("count_right", 0),
            "count_simultaneous": tech_metrics.get("count_simultaneous", 0),
            "last_hit_leg": tech_metrics.get("last_hit_leg", "N/A"),
            "final_state": tech_metrics.get("final_state", "Parado"),
            "ball_size": f"N {self.physics.calibrator.selected_size_id}"
        }

        # Estructura FINAL compatible con tu sistema legacy
        return {
            "success": True,
            "video_duration_s": round(duration, 2),
            "frames_total": total_frames,
            "frames_analyzed": analyzed_frames,
            "id": int(time.time()),
            
            # LOS CAMPOS QUE FALTABAN:
            "trajectory": self.trajectory_3d,
            "hit_images": self.hit_images, # Deberías poblar esto si return_images=True
            
            "meta": {
                "performance": {
                    "total_time_s": 0, # Se llena en API
                    "frames_analyzed": analyzed_frames
                },
                "stats": stats_object,
                
                # Datos adicionales del nuevo sistema
                "face_verification": "N/A", 
                "face_consistency": mental_metrics.get("face_consistency", "N/A"),
                "detailed_evaluation": {
                    "technical": tech_metrics,
                    "physical": self.phys_eval.get_metrics(),
                    "tactical": self.tact_eval.get_metrics(),
                    "mental": mental_metrics
                }
            }
        }