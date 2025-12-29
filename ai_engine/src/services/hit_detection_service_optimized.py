import cv2
import numpy as np
import os
import urllib.request
import time
import base64
from typing import Any, Callable, Dict, List, Optional, Tuple
from .video_io import read_frame_at

# ---------------------------
# Helpers
# ---------------------------
def smooth_signal(data_list, window_size=5):
    if len(data_list) < window_size:
        return data_list
    return np.convolve(data_list, np.ones(window_size) / window_size, mode="same").tolist()

def _clamp_int(v: int, lo: int, hi: int) -> int:
    return max(lo, min(v, hi))

def _safe_crop_bounds(x1, y1, x2, y2, w, h):
    x1 = _clamp_int(int(x1), 0, w - 1)
    y1 = _clamp_int(int(y1), 0, h - 1)
    x2 = _clamp_int(int(x2), 0, w)
    y2 = _clamp_int(int(y2), 0, h)
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2

# ==========================================
# 1. SISTEMA DE CALIBRACIÓN AUTÓNOMA
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
        if not self.samples:
            return
        median_px = float(np.median(self.samples))
        if median_px == 0:
            return

        scale_t5 = median_px / 22.0
        h_hyp = player_h_px / scale_t5

        if h_hyp > 155:
            self.selected_size_id = 5
        elif 135 < h_hyp <= 155:
            self.selected_size_id = 4
        else:
            self.selected_size_id = 3

        self.real_diameter_cm = self.SIZES[self.selected_size_id]
        raw_scale = median_px / self.real_diameter_cm
        self.px_per_cm = max(0.5, min(raw_scale, 10.0))
        self.is_calibrated = True

# ==========================================
# 2. MODELOS IA (WRAPPERS)
# ==========================================
class YoloBaseWrapper:
    def __init__(self, model_path: str, input_size: Tuple[int, int] = (416, 416), fp16: bool = True):
        self.model_path = model_path
        self.net = None
        self.input_size = input_size
        self.fp16 = fp16

    def load(self) -> bool:
        if not os.path.exists(self.model_path):
            print(f"❌ Modelo no encontrado en: {self.model_path}")
            return False
        try:
            self.net = cv2.dnn.readNet(self.model_path)
            # Backend CUDA obligatorio para rendimiento
            self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
            
            if self.fp16:
                self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA_FP16)
            else:
                self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
                
            print(f"✅ Modelo cargado: {os.path.basename(self.model_path)} | Size: {self.input_size} | FP16: {self.fp16}")
            return True
        except Exception as e:
            print(f"❌ Error cargando {self.model_path}: {e}")
            self.net = None
            return False

    def preprocess(self, img: np.ndarray) -> np.ndarray:
        return cv2.dnn.blobFromImage(
            img, 1 / 255.0, self.input_size, mean=(0, 0, 0), swapRB=True, crop=False
        )

class YoloDetWrapper(YoloBaseWrapper):
    def detect(self, img: np.ndarray, conf: float = 0.25):
        if self.net is None: return []

        h, w = img.shape[:2]
        self.net.setInput(self.preprocess(img))
        preds = np.squeeze(self.net.forward()).T

        if preds.ndim < 2 or preds.shape[1] <= 36: return []

        # YOLOv8 COCO: Index 32+4 = 36 es 'sports ball'
        scores = preds[:, 36] 
        keep = scores > conf
        
        if not np.any(keep): return []

        preds = preds[keep]
        scores = scores[keep]
        boxes = preds[:, :4].copy()
        
        # xywh a xyxy centrado
        boxes[:, 0] -= boxes[:, 2] / 2
        boxes[:, 1] -= boxes[:, 3] / 2

        indices = cv2.dnn.NMSBoxes(
            bboxes=boxes.tolist(), scores=scores.tolist(), score_threshold=conf, nms_threshold=0.45
        )
        
        if len(indices) == 0: return []

        sx, sy = w / self.input_size[0], h / self.input_size[1]
        res = []
        for i in indices.flatten():
            b = boxes[i]
            # [x, y, w, h, score]
            res.append([
                int(b[0] * sx), int(b[1] * sy), int(b[2] * sx), int(b[3] * sy), float(scores[i])
            ])
        
        # Retornamos la detección con mayor confianza
        return sorted(res, key=lambda x: x[4])[-1:]

class YoloPoseWrapper(YoloBaseWrapper):
    def detect(self, img: np.ndarray, conf: float = 0.5):
        if self.net is None: return []

        h, w = img.shape[:2]
        self.net.setInput(self.preprocess(img))
        preds = np.squeeze(self.net.forward()).T

        if preds.ndim < 2: return []

        # Index 4 es la confianza de "persona" en YOLOv8-Pose
        scores = preds[:, 4]
        keep = scores > conf
        
        if not np.any(keep): return []

        preds = preds[keep]
        scores = scores[keep]
        kpts_raw = preds[:, 5:]

        indices = cv2.dnn.NMSBoxes(
            bboxes=preds[:, :4].tolist(), scores=scores.tolist(), score_threshold=conf, nms_threshold=0.5
        )
        
        if len(indices) == 0: return []

        sx, sy = w / self.input_size[0], h / self.input_size[1]
        res = []
        
        for i in indices.flatten():
            pk = kpts_raw[i].reshape(-1, 3)
            kpts = [{"x": int(p[0] * sx), "y": int(p[1] * sy), "conf": float(p[2])} for p in pk]
            
            box = preds[i, :4]
            bbox = [
                int((box[0] - box[2] / 2) * sx),
                int((box[1] - box[3] / 2) * sy),
                int(box[2] * sx),
                int(box[3] * sy),
            ]
            area = bbox[2] * bbox[3]
            res.append({"kpts": kpts, "box": bbox, "area": area})
            
        # Retornamos la persona más grande (asumiendo jugador principal)
        return sorted(res, key=lambda x: x["area"])[-1:]

# ==========================================
# 3. SERVICIO OPTIMIZADO
# ==========================================
class HitDetectionServiceOptimized:
    def __init__(
        self,
        default_model_dirs: List[str] = None,
        segment_floor_fn: Optional[Callable] = None,
        face_compare_fn: Optional[Callable] = None,
        # CORRECCIÓN: Default 416 para coincidir con tu generación
        yolo_size: int = 416, 
        use_fp16: bool = True,
        enable_depth: bool = False,
        midas_size: int = 256
    ):
        self.models_dir = "/app/ai_engine/models"
        
        # Forzamos 416 si no viene en env, porque es lo que generaste
        env_size = os.getenv("YOLO_SIZE")
        self.yolo_size = int(env_size) if env_size else yolo_size

        self.paths = {
            "det": os.path.join(self.models_dir, f"yolov8n_{self.yolo_size}.onnx"),
            "pose": os.path.join(self.models_dir, "yolov8n-pose.onnx"), # Pose suele funcionar dinámico
            "midas": os.path.join(self.models_dir, "midas_v21_small.onnx"),
        }
        
        # URLs de respaldo (Solo si faltan archivos)
        self.urls = {
            "det": "https://github.com/pellit/video-analytics-saas/raw/main/ai_engine/yolov8n.onnx", # Fallback genérico
            "pose": "https://huggingface.co/Xenova/yolov8-pose-onnx/resolve/main/yolov8n-pose.onnx?download=true",
            "midas": "https://github.com/isl-org/MiDaS/releases/download/v2_1/model-small.onnx"
        }

        self.segment_floor_fn = segment_floor_fn
        self.face_compare_fn = face_compare_fn
        self.use_fp16 = use_fp16
        self.enable_depth = enable_depth
        self.midas_size = midas_size

        self._setup_models()
        self.calibrator = BallCalibrator()
        self.skeleton_links = [(0,5),(0,6),(5,7),(7,9),(6,8),(8,10),(5,11),(6,12),(11,12),(5,6),(11,13),(13,15),(12,14),(14,16)]

    def _setup_models(self):
        os.makedirs(self.models_dir, exist_ok=True)
        
        # Descarga de fallbacks
        for k, path in self.paths.items():
            if not os.path.exists(path) or os.path.getsize(path) < 1000:
                # Solo descargamos si es estrictamente necesario
                if k in self.urls:
                    try:
                        print(f"⬇️ Descargando modelo faltante: {k} -> {path}")
                        urllib.request.urlretrieve(self.urls[k], path)
                    except: pass

        # Inicialización de Wrappers
        # NOTA: Usamos yolo_size para input_size
        size = (self.yolo_size, self.yolo_size)
        
        self.det = YoloDetWrapper(self.paths["det"], input_size=size, fp16=self.use_fp16)
        
        # Pose: Intentamos cargar el ONNX. Si es el estándar dinámico, 416 le va bien.
        self.pose = YoloPoseWrapper(self.paths["pose"], input_size=size, fp16=self.use_fp16)
        
        self.det.load()
        self.pose.load()

        self.midas = None
        if self.enable_depth and os.path.exists(self.paths["midas"]):
            try:
                self.midas = cv2.dnn.readNet(self.paths["midas"])
                self.midas.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
                if self.use_fp16: self.midas.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA_FP16)
                else: self.midas.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
            except: pass

    def get_depth(self, frame: np.ndarray):
        if self.midas is None: return None
        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(frame, 1/255.0, (self.midas_size, self.midas_size), mean=(123.675, 116.28, 103.53), swapRB=True, crop=False)
        self.midas.setInput(blob)
        d = self.midas.forward()
        depth = cv2.resize(d[0, 0], (w, h))
        return cv2.normalize(depth, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)

    def _infer_floor_y(self, frame: np.ndarray) -> int:
        if self.segment_floor_fn:
            try:
                res = self.segment_floor_fn(frame)
                return int(res.get("floor_y", 0)) if isinstance(res, dict) else int(res)
            except: pass
        return int(frame.shape[0] * 0.9)

    def extract_trajectory(self, video_path, stride=3, max_frames=300):
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frames_meta = [] 
        processed = 0
        idx = 0
        floor_y = None
        
        while processed < max_frames:
            ret, frame = cap.read()
            if not ret: break
            if idx % stride != 0: 
                idx += 1; continue
            
            if processed == 5: floor_y = self._infer_floor_y(frame)

            ball = self.det.detect(frame)
            person = self.pose.detect(frame)
            
            # --- DEBUG LOGGING (Temporal para verificar detección) ---
            # if processed % 30 == 0:
            #     print(f"Frame {idx}: Ball={len(ball)}, Person={len(person)}")

            frame_data = {"idx": idx, "time": idx/fps, "ball": None, "feet": None, "floor_y": floor_y}

            if ball and person:
                b = ball[0]; p = person[0]
                # Profundidad desactivada por defecto para velocidad máxima, se usa 128
                depth = self.get_depth(frame) if self.enable_depth else None
                
                bx, by, bw, bh = b[:4]
                # Muestreo Z seguro
                if depth is not None:
                    cx = _clamp_int(bx+bw//2, 0, depth.shape[1]-1)
                    cy = _clamp_int(by+bh//2, 0, depth.shape[0]-1)
                    bz = depth[cy, cx]
                else: bz = 128
                
                frame_data["ball"] = {"x": bx+bw//2, "y": by+bh, "z": int(bz), "w": bw}
                
                f_l = p["kpts"][15]; f_r = p["kpts"][16] # Tobillos
                # Asumimos Z=128 si no hay depth
                frame_data["feet"] = {
                    "L": {"x": f_l["x"], "y": f_l["y"], "z": 128, "conf": f_l["conf"]},
                    "R": {"x": f_r["x"], "y": f_r["y"], "z": 128, "conf": f_r["conf"]}
                }
                frame_data["person_h"] = p["box"][3]
                frame_data["kpts"] = p["kpts"]
                frame_data["ball_box"] = b # Para visualizacion

            frames_meta.append(frame_data)
            processed += 1
            idx += 1
            
        cap.release()
        return frames_meta, [], [], fps

    def analyze_trajectory(self, frames_meta):
        # 1. Calibración
        widths, heights = [], []
        for f in frames_meta:
            if f["ball"] and f["feet"]:
                feet_y = (f["feet"]["L"]["y"] + f["feet"]["R"]["y"]) / 2
                if abs(f["ball"]["y"] - feet_y) < 150:
                    widths.append(f["ball"]["w"])
                    heights.append(f["person_h"])
        
        for w in widths: self.calibrator.add_sample(w)
        if heights: self.calibrator.finalize(np.median(heights))
        scale = self.calibrator.px_per_cm

        # 2. Suavizado
        raw_y = [(f["ball"]["y"] if f["ball"] else 0) for f in frames_meta]
        smooth_y = smooth_signal(raw_y, 5)

        events_log = []
        full_trajectory = []
        juggles = 0
        last_hit_frame = -100
        stats = {"total": 0, "left": 0, "right": 0, "simultaneous": 0}
        dribble_state = "Parado"

        for i, f in enumerate(frames_meta):
            if not f["ball"] or not f["feet"]: continue
            
            ball_y = smooth_y[i]
            prev_y = smooth_y[i-1] if i>0 else ball_y
            vel_y = ball_y - prev_y
            
            full_trajectory.append({"f": f["idx"], "x": f["ball"]["x"], "y": int(ball_y), "z": f["ball"]["z"]})
            
            floor = f["floor_y"] if f["floor_y"] else 1000
            height_cm = (floor - ball_y) / scale
            
            # LOGICA JUGGLE
            if height_cm > 15:
                # Contacto: Pelota sube (vel < -2)
                is_contact = vel_y < -2.0
                hit_L, hit_R = False, False
                
                # Check Pie Izq
                if f["feet"]["L"]["conf"] > 0.5:
                    dx = abs(f["feet"]["L"]["x"] - f["ball"]["x"]) / scale
                    dy = abs(f["feet"]["L"]["y"] - ball_y) / scale
                    if (is_contact and dx < 25 and dy < 30) or (dx < 15 and dy < 10): hit_L = True
                
                # Check Pie Der
                if f["feet"]["R"]["conf"] > 0.5:
                    dx = abs(f["feet"]["R"]["x"] - f["ball"]["x"]) / scale
                    dy = abs(f["feet"]["R"]["y"] - ball_y) / scale
                    if (is_contact and dx < 25 and dy < 30) or (dx < 15 and dy < 10): hit_R = True
                
                if (hit_L or hit_R) and (f["idx"] - last_hit_frame) > 10:
                    juggles += 1
                    last_hit_frame = f["idx"]
                    leg = "Simul" if (hit_L and hit_R) else ("Izq" if hit_L else "Der")
                    
                    if leg == "Simul": stats["simultaneous"] += 1
                    elif leg == "Izq": stats["left"] += 1
                    else: stats["right"] += 1
                    
                    stats["total"] = juggles
                    events_log.append({"idx": f["idx"], "type": "JUGGLE", "hit_leg": leg})
            
            # LOGICA DRIBBLE (Suelo)
            else:
                d_l = np.hypot(f["feet"]["L"]["x"]-f["ball"]["x"], f["feet"]["L"]["y"]-ball_y) / scale
                d_r = np.hypot(f["feet"]["R"]["x"]-f["ball"]["x"], f["feet"]["R"]["y"]-ball_y) / scale
                if min(d_l, d_r) < 60: dribble_state = "Control"

        return events_log, stats, dribble_state, full_trajectory

    def generate_visuals(self, video_path, events_log, frames_meta):
        return [] # Desactivado para velocidad

    def run_on_video(self, video_path, frame_stride=3, max_frames=300, hit_threshold=0.4, return_images=True):
        t0 = time.time()
        meta, _, _, fps = self.extract_trajectory(video_path, stride=frame_stride, max_frames=max_frames)
        logs, stats, end_state, traj = self.analyze_trajectory(meta)
        
        total_t = time.time() - t0
        last_leg = logs[-1]["hit_leg"] if logs else "N/A"
        
        return {
            "id": int(time.time()),
            "hit_images": [],
            "trajectory": traj,
            "meta": {
                "performance": {"total_time_s": round(total_t, 2), "frames_analyzed": len(meta)},
                "stats": {
                    "total_juggles": stats["total"],
                    "count_left": stats["left"],
                    "count_right": stats["right"],
                    "count_simultaneous": stats["simultaneous"],
                    "last_hit_leg": last_leg,
                    "final_state": end_state,
                    "ball_size": f"N {self.calibrator.selected_size_id}"
                },
                "face_verification": "N/A"
            }
        }