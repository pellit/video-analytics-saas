import cv2
import numpy as np
import os
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

# --- Clase de Intercambio de Datos ---
class DetectionObject:
    """Estandariza la salida para que PhysicsEngine la entienda"""
    def __init__(self, class_name, score, bbox, track_id=None):
        self.class_name = class_name
        self.confidence = score
        self.bbox = bbox # [x1, y1, x2, y2]
        self.track_id = track_id

# ==========================================
# 1. SISTEMA DE CALIBRACIÓN
# ==========================================
class BallCalibrator:
    def __init__(self):
        self.SIZES = {3: 18.0, 4: 20.0, 5: 22.0}
        self.samples = [] 
        self.is_calibrated = False
        self.selected_size_id = 5
        self.real_diameter_cm = 22.0
        self.px_per_cm = 2.0 

    def add_sample(self, width_px):
        if 10 < width_px < 200: 
            self.samples.append(width_px)

    def finalize(self, player_h_px):
        if not self.samples: return
        median_px = float(np.median(self.samples))
        if median_px == 0: return

        scale_t5 = median_px / 22.0
        h_hyp = player_h_px / scale_t5
        
        if h_hyp > 155: self.selected_size_id = 5
        elif 135 < h_hyp <= 155: self.selected_size_id = 4
        else: self.selected_size_id = 3
            
        self.real_diameter_cm = self.SIZES[self.selected_size_id]
        raw_scale = median_px / self.real_diameter_cm
        self.px_per_cm = max(0.5, min(raw_scale, 10.0))
        self.is_calibrated = True

# ==========================================
# 2. MODELOS IA (WRAPPERS CORREGIDOS)
# ==========================================
class YoloBaseWrapper:
    def __init__(self, model_path: str, input_size: Tuple[int, int] = (640, 640), fp16: bool = True):
        self.model_path = model_path
        self.net = None
        self.input_size = input_size
        self.fp16 = fp16

    def load(self) -> bool:
        if not os.path.exists(self.model_path):
            print(f"❌ Modelo no encontrado: {self.model_path}")
            return False
        try:
            self.net = cv2.dnn.readNet(self.model_path)
            self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
            if self.fp16: self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA_FP16)
            else: self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
            print(f"✅ Cargado: {os.path.basename(self.model_path)}")
            return True
        except Exception as e:
            print(f"❌ Error carga: {e}")
            return False

    def preprocess(self, img: np.ndarray) -> np.ndarray:
        return cv2.dnn.blobFromImage(img, 1/255.0, self.input_size, swapRB=True, crop=False)

class YoloDetWrapper(YoloBaseWrapper):
    def detect(self, img: np.ndarray, conf: float = 0.15):
        if not self.net: return []
        h, w = img.shape[:2]
        self.net.setInput(self.preprocess(img))
        preds = np.squeeze(self.net.forward()).T
        
        if preds.ndim < 2 or preds.shape[1] <= 36: return []
        
        # Class 32 ('sports ball') en COCO
        scores = preds[:, 36] 
        keep = scores > conf
        if not np.any(keep): return []
        
        preds = preds[keep]
        scores = scores[keep]
        boxes = preds[:, :4].copy()
        
        # xywh a xyxy (para NMS)
        boxes[:, 0] -= boxes[:, 2]/2
        boxes[:, 1] -= boxes[:, 3]/2
        
        indices = cv2.dnn.NMSBoxes(boxes.tolist(), scores.tolist(), conf, 0.45)
        if len(indices) == 0: return []
        
        sx, sy = w / self.input_size[0], h / self.input_size[1]
        
        # MODIFICACIÓN CLAVE: Retornar lista de objetos DetectionObject
        results = []
        for i in indices.flatten():
            b = boxes[i]
            # Convertir a coordenadas de imagen original
            x1 = int(b[0] * sx)
            y1 = int(b[1] * sy)
            x2 = int((b[0] + b[2]) * sx) # x + w
            y2 = int((b[1] + b[3]) * sy) # y + h
            
            # Crear objeto compatible con PhysicsEngine
            obj = DetectionObject(
                class_name="ball",
                score=float(scores[i]),
                bbox=[x1, y1, x2, y2]
            )
            results.append(obj)
            
        # Retornar el de mayor confianza
        return sorted(results, key=lambda x: x.confidence)[-1:]

class YoloPoseWrapper(YoloBaseWrapper):
    def detect(self, img: np.ndarray, conf: float = 0.4):
        if not self.net: return []
        h, w = img.shape[:2]
        self.net.setInput(self.preprocess(img))
        preds = np.squeeze(self.net.forward()).T
        
        if preds.ndim < 2: return []
        scores = preds[:, 4]
        keep = scores > conf
        if not np.any(keep): return []
        
        preds = preds[keep]
        scores = scores[keep]
        kpts_raw = preds[:, 5:]
        
        indices = cv2.dnn.NMSBoxes(preds[:, :4].tolist(), scores.tolist(), conf, 0.5)
        if len(indices) == 0: return []
        
        sx, sy = w / self.input_size[0], h / self.input_size[1]
        results = []
        
        for i in indices.flatten():
            pk = kpts_raw[i].reshape(-1, 3)
            kpts = [{"x": int(p[0]*sx), "y": int(p[1]*sy), "conf": float(p[2])} for p in pk]
            
            # BBox del jugador
            box = preds[i, :4]
            x1 = int((box[0]-box[2]/2)*sx)
            y1 = int((box[1]-box[3]/2)*sy)
            x2 = int((box[0]+box[2]/2)*sx)
            y2 = int((box[1]+box[3]/2)*sy)
            
            # MODIFICACIÓN: Retornar diccionario enriquecido
            # (Pose suele ser un dict porque tiene kpts, pero agregamos bbox standard)
            pose_obj = {
                "kpts": kpts,
                "box": [x1, y1, x2, y2], # Formato [x1, y1, x2, y2]
                "score": float(scores[i])
            }
            results.append(pose_obj)
            
        # Retornar la persona más grande (asumiendo bbox area)
        return sorted(results, key=lambda p: (p["box"][2]-p["box"][0])*(p["box"][3]-p["box"][1]))[-1:]

# ==========================================
# 3. SERVICIO OPTIMIZADO
# ==========================================
class HitDetectionServiceOptimized:
    def __init__(self, default_model_dirs=None, segment_floor_fn=None, face_compare_fn=None,
                 yolo_size=640, use_fp16=True, enable_depth=False, midas_size=256):
        
        self.models_dir = "/app/ai_engine/models"
        self.yolo_size = yolo_size

        self.paths = {
            "det": os.path.join(self.models_dir, "yolov8n.onnx"),
            "pose": os.path.join(self.models_dir, "yolov8n-pose.onnx"), 
            "midas": os.path.join(self.models_dir, "midas_v21_small.onnx"),
        }
        
        self.segment_floor_fn = segment_floor_fn
        self.face_compare_fn = face_compare_fn
        self.use_fp16 = use_fp16
        self.enable_depth = enable_depth
        self.midas_size = midas_size
        
        self._setup_models()
        self.calibrator = BallCalibrator()

    def _setup_models(self):
        os.makedirs(self.models_dir, exist_ok=True)
        size = (self.yolo_size, self.yolo_size)
        self.det = YoloDetWrapper(self.paths["det"], input_size=size, fp16=self.use_fp16)
        self.pose = YoloPoseWrapper(self.paths["pose"], input_size=size, fp16=self.use_fp16)
        self.det.load(); self.pose.load()