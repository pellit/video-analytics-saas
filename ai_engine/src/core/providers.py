import cv2
import time
from abc import ABC, abstractmethod
from typing import Optional

from ..domain.models import FrameData
from .physics_engine import PhysicsEngine
from ..services.smart_loader import SmartModelLoader


class IDataProvider(ABC):
    @abstractmethod
    def get_next_frame(self) -> Optional[FrameData]:
        pass

    @abstractmethod
    def release(self):
        pass


class CameraProvider(IDataProvider):
    def __init__(self, video_source, physics_engine: PhysicsEngine, models_dir="/app/ai_engine/models"):
        self.cap = cv2.VideoCapture(video_source)
        self.physics = physics_engine
        self.frame_count = 0

        # Intentar cargar modelos con SmartModelLoader (si están disponibles)
        try:
            self.det_loader = SmartModelLoader(f"{models_dir}/{'yolov8n_640'}", task='detect', target_imgsz=640)
        except Exception:
            self.det_loader = None

        try:
            self.pose_loader = SmartModelLoader(f"{models_dir}/{'yolov8s-pose_640'}", task='pose', target_imgsz=640)
        except Exception:
            self.pose_loader = None

        self.audio_buffer = None

    def _run_model(self, loader, frame):
        if loader is None:
            return None
        # SmartModelLoader puede exponer .model (Ultralytics) o usar predict()
        try:
            if hasattr(loader, 'model') and callable(loader.model):
                results = loader.model(frame, verbose=False, conf=0.4)
                return results[0]
            else:
                # Fallback al wrapper predict (devuelve imagen anotada)
                _ = loader.predict(frame, conf_thres=0.4)
                return None
        except Exception:
            return None

    def get_next_frame(self) -> Optional[FrameData]:
        ret, frame = self.cap.read()
        if not ret:
            return None

        timestamp = time.time()
        self.frame_count += 1

        raw_det = self._run_model(self.det_loader, frame)
        raw_pose = self._run_model(self.pose_loader, frame)

        # Extraer balón (si existe) en formato simple con atributo 'bbox'
        raw_ball_obj = None
        if raw_det is not None:
            try:
                for box in getattr(raw_det, 'boxes', []):
                    cls_id = int(getattr(box, 'cls', -1))
                    if cls_id == 32:
                        coords = box.xyxy[0].cpu().numpy()
                        x1, y1, x2, y2 = coords
                        raw_ball_obj = type('obj', (object,), {'bbox': [x1, y1, x2, y2]})
                        break
            except Exception:
                raw_ball_obj = None

        # Formatear pose
        raw_pose_dict = None
        if raw_pose is not None:
            try:
                kpts_data = getattr(raw_pose, 'keypoints', None)
                if kpts_data is not None and hasattr(kpts_data, 'data') and len(kpts_data.data) > 0:
                    kpts = kpts_data.data[0].cpu().numpy()
                    formatted_kpts = []
                    for kp in kpts:
                        formatted_kpts.append({'x': float(kp[0]), 'y': float(kp[1]), 'conf': float(kp[2])})

                    box_xy = getattr(raw_pose, 'boxes', None)
                    if box_xy is not None and len(getattr(box_xy, 'xyxy', []))>0:
                        px1, py1, px2, py2 = box_xy.xyxy[0].cpu().numpy()
                        raw_pose_dict = {"kpts": formatted_kpts, "box": [float(px1), float(py1), float(px2), float(py2)]}
                    else:
                        raw_pose_dict = {"kpts": formatted_kpts}
            except Exception:
                raw_pose_dict = None

        frame_data = self.physics.process(
            raw_pose=raw_pose_dict,
            raw_ball=raw_ball_obj,
            raw_audio=self.audio_buffer,
            floor_y=int(frame.shape[0]),
            timestamp=timestamp
        )

        return frame_data

    def release(self):
        try:
            self.cap.release()
        except Exception:
            pass


# VirtualProvider could be implemented for unit tests (not included here)


import json


class VirtualProvider(IDataProvider):
    def __init__(self, json_file_path: str, physics_engine: PhysicsEngine, loop: bool = False):
        """
        Lee datos pre-grabados de un JSON y simula un stream en tiempo real.
        El JSON debe ser una lista de frames con los campos: `frame`, `floor_y`, `ball` (bbox o null), `pose` (dict con 'kpts' y 'box').
        """
        self.physics = physics_engine
        self.data = []
        self.current_idx = 0
        self.loop = loop

        try:
            with open(json_file_path, 'r') as f:
                self.data = json.load(f)
            print(f"✅ [Virtual] {len(self.data)} frames cargados desde {json_file_path}")
        except Exception as e:
            print(f"❌ [Virtual] Error cargando JSON {json_file_path}: {e}")
            self.data = []

    def get_next_frame(self) -> Optional[FrameData]:
        if self.current_idx >= len(self.data):
            if self.loop and len(self.data) > 0:
                self.current_idx = 0
            else:
                return None

        frame_raw = self.data[self.current_idx]
        self.current_idx += 1

        raw_ball_obj = None
        if frame_raw.get("ball"):
            raw_ball_obj = type('obj', (object,), {'bbox': frame_raw["ball"]})

        raw_pose_dict = None
        if frame_raw.get("pose"):
            raw_pose_dict = frame_raw["pose"]

        raw_audio = None

        frame_data = self.physics.process(
            raw_pose=raw_pose_dict,
            raw_ball=raw_ball_obj,
            raw_audio=raw_audio,
            floor_y=frame_raw.get("floor_y", 720),
            timestamp=frame_raw.get("timestamp", time.time())
        )

        # Simular pequeña latencia para no correr todo instantáneamente
        time.sleep(0.03)

        return frame_data

    def release(self):
        self.data = []
        print("[Virtual] Simulación finalizada.")
