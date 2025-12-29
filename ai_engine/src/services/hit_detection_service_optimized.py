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
    """Suaviza una lista de números usando media móvil."""
    if len(data_list) < window_size:
        return data_list
    return np.convolve(data_list, np.ones(window_size) / window_size, mode="same").tolist()


def _clamp_int(v: int, lo: int, hi: int) -> int:
    return lo if v < lo else hi if v > hi else v


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
    """
    Optimizado:
    - input_size configurable (Nano: 320/416).
    - FP16 preferido si está disponible.
    """
    def __init__(self, model_path: str, input_size: Tuple[int, int] = (320, 320), fp16: bool = True):
        self.model_path = model_path
        self.net = None
        self.input_size = input_size
        self.fp16 = fp16

    def load(self) -> bool:
        if not os.path.exists(self.model_path):
            return False
        try:
            self.net = cv2.dnn.readNet(self.model_path)
            self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)

            if self.fp16 and hasattr(cv2.dnn, "DNN_TARGET_CUDA_FP16"):
                self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA_FP16)
            else:
                self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
            return True
        except Exception:
            self.net = None
            return False

    def preprocess(self, img: np.ndarray) -> np.ndarray:
        # swapRB=True y mean=0 para YOLO ONNX típico
        return cv2.dnn.blobFromImage(
            img,
            scalefactor=1 / 255.0,
            size=self.input_size,
            mean=(0, 0, 0),
            swapRB=True,
            crop=False
        )


class YoloDetWrapper(YoloBaseWrapper):
    """
    Tu YOLOv8n ONNX típicamente produce (84, N) o (N, 84) según export.
    Tu lógica usa: preds = squeeze().T y lee score en índice (32+4).
    Mantengo tu parsing pero optimizo:
    - Menos .tolist()
    - Escalado según input_size real (no hardcode 640)
    """
    def detect(self, img: np.ndarray, conf: float = 0.15):
        if self.net is None:
            return []

        h, w = img.shape[:2]
        in_w, in_h = self.input_size[0], self.input_size[1]

        self.net.setInput(self.preprocess(img))
        out = self.net.forward()
        preds = np.squeeze(out).T

        # Validaciones rápidas
        if preds.ndim < 2 or preds.shape[1] <= 36:
            return []

        # score según tu índice (mantengo)
        scores = preds[:, 32 + 4]
        keep = scores > conf
        if not np.any(keep):
            return []

        preds = preds[keep]
        scores = scores[keep]

        boxes = preds[:, :4].copy()
        # xywh -> xyxy (pero guardamos como x,y,w,h para tu salida)
        boxes[:, 0] -= boxes[:, 2] / 2
        boxes[:, 1] -= boxes[:, 3] / 2

        # NMSBoxes requiere listas; minimizamos conversiones
        indices = cv2.dnn.NMSBoxes(
            bboxes=boxes[:, :4].tolist(),
            scores=scores.tolist(),
            score_threshold=conf,
            nms_threshold=0.5
        )
        if indices is None or len(indices) == 0:
            return []

        # Escalado a tamaño original
        sx, sy = w / float(in_w), h / float(in_h)

        best = None
        for i in indices.flatten():
            b = boxes[i]
            bx = int(b[0] * sx)
            by = int(b[1] * sy)
            bw = int(b[2] * sx)
            bh = int(b[3] * sy)
            sc = float(scores[i])
            if best is None or sc > best[4]:
                best = [bx, by, bw, bh, sc]

        return [best] if best is not None else []


class YoloPoseWrapper(YoloBaseWrapper):
    """
    Mantengo tu lógica, optimizo:
    - usa input_size real para scale
    - evita construir listas innecesarias
    """
    def detect(self, img: np.ndarray, conf: float = 0.5):
        if self.net is None:
            return []

        h, w = img.shape[:2]
        in_w, in_h = self.input_size[0], self.input_size[1]

        self.net.setInput(self.preprocess(img))
        out = self.net.forward()
        preds = np.squeeze(out).T

        if preds.ndim < 2:
            return []

        scores = preds[:, 4]
        keep = scores > conf
        if not np.any(keep):
            return []

        preds_kept = preds[keep]
        scores_kept = scores[keep]
        kpts_raw = preds_kept[:, 5:]

        indices = cv2.dnn.NMSBoxes(
            bboxes=preds_kept[:, :4].tolist(),
            scores=scores_kept.tolist(),
            score_threshold=conf,
            nms_threshold=0.5
        )
        if indices is None or len(indices) == 0:
            return []

        sx, sy = w / float(in_w), h / float(in_h)

        best = None
        best_area = -1
        for i in indices.flatten():
            pk = kpts_raw[i].reshape(-1, 3)
            kpts = [{"x": int(p[0] * sx), "y": int(p[1] * sy), "conf": float(p[2])} for p in pk]

            box = preds_kept[i, :4]
            bbox = [
                int((box[0] - box[2] / 2) * sx),
                int((box[1] - box[3] / 2) * sy),
                int(box[2] * sx),
                int(box[3] * sy),
            ]
            area = bbox[2] * bbox[3]
            if area > best_area:
                best_area = area
                best = {"kpts": kpts, "box": bbox, "area": area}

        return [best] if best is not None else []


# ==========================================
# 3. SERVICIO OPTIMIZADO
# ==========================================
class HitDetectionServiceOptimized:
    def __init__(
        self,
        default_model_dirs: List[str] = None,
        segment_floor_fn: Optional[Callable[[np.ndarray], Optional[int]]] = None,
        face_compare_fn: Optional[Callable[[str, str], Any]] = None,
        # NUEVO: tuning para Nano
        yolo_size: int = 320,              # 320 o 416 recomendado en Nano
        use_fp16: bool = True,
        enable_depth: bool = False,        # MiDaS es caro: por defecto OFF
        depth_every_n: int = 5,            # si enable_depth=True, computa cada N frames
        midas_size: int = 256              # 256 ok; si querés más FPS: 192
    ):
        self.models_dir = "/app/ai_engine/models"
        self.paths = {
            "det": os.path.join(self.models_dir, "yolov8n.onnx"),
            "pose": os.path.join(self.models_dir, "yolov8n-pose.onnx"),
            "midas": os.path.join(self.models_dir, "midas_v21_small.onnx"),
        }
        self.urls = {
            "det": "https://huggingface.co/Bingsu/yolov8n_onnx/resolve/main/yolov8n.onnx",
            "pose": "https://huggingface.co/Xenova/yolov8-pose-onnx/resolve/main/yolov8n-pose.onnx?download=true",
            "midas": "https://github.com/isl-org/MiDaS/releases/download/v2_1/model-small.onnx",
        }

        self.segment_floor_fn = segment_floor_fn
        self.face_compare_fn = face_compare_fn

        # Tuning
        self.yolo_size = int(yolo_size)
        self.use_fp16 = bool(use_fp16)
        self.enable_depth = bool(enable_depth)
        self.depth_every_n = max(1, int(depth_every_n))
        self.midas_size = int(midas_size)

        self._setup_models()
        self.calibrator = BallCalibrator()

        self.skeleton_links = [
            (0, 5), (0, 6), (5, 7), (7, 9), (6, 8), (8, 10),
            (5, 11), (6, 12), (11, 12), (5, 6), (11, 13), (13, 15), (12, 14), (14, 16)
        ]

    def _setup_models(self):
        os.makedirs(self.models_dir, exist_ok=True)
        for k, path in self.paths.items():
            if not os.path.exists(path) or os.path.getsize(path) < 1000:
                try:
                    urllib.request.urlretrieve(self.urls[k], path)
                except Exception:
                    pass

        size = (self.yolo_size, self.yolo_size)
        self.det = YoloDetWrapper(self.paths["det"], input_size=size, fp16=self.use_fp16)
        self.pose = YoloPoseWrapper(self.paths["pose"], input_size=size, fp16=self.use_fp16)
        self.det.load()
        self.pose.load()

        self.midas = None
        if self.enable_depth and os.path.exists(self.paths["midas"]):
            try:
                self.midas = cv2.dnn.readNet(self.paths["midas"])
                self.midas.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
                if self.use_fp16 and hasattr(cv2.dnn, "DNN_TARGET_CUDA_FP16"):
                    self.midas.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA_FP16)
                else:
                    self.midas.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
            except Exception:
                self.midas = None

    def get_depth(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """
        Optimizaciones:
        - tamaño fijo midas_size (default 256)
        - FP16 target (si está)
        - evita normalizaciones más caras cuando no se necesita (pero mantenemos tu salida uint8)
        """
        if self.midas is None:
            return None

        h, w = frame.shape[:2]
        s = self.midas_size

        blob = cv2.dnn.blobFromImage(
            frame,
            scalefactor=1 / 255.0,
            size=(s, s),
            mean=(123.675, 116.28, 103.53),
            swapRB=True,
            crop=False
        )
        self.midas.setInput(blob)
        d = self.midas.forward()  # shape ~ (1,1,s,s)

        depth_small = d[0, 0]
        depth = cv2.resize(depth_small, (w, h), interpolation=cv2.INTER_LINEAR)
        depth_u8 = cv2.normalize(depth, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)
        return depth_u8

    def _infer_floor_y(self, frame: np.ndarray) -> Optional[int]:
        if self.segment_floor_fn:
            try:
                result = self.segment_floor_fn(frame)
                if isinstance(result, dict):
                    return int(result.get("floor_y", 0))
                if result:
                    return int(result)
            except Exception:
                pass

        h, w = frame.shape[:2]
        roi_start = int(h * 0.5)
        gray = cv2.cvtColor(frame[roi_start:, :], cv2.COLOR_BGR2GRAY)
        sobel = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        scores = np.mean(np.abs(sobel), axis=1)
        if scores.size > 0:
            return roi_start + int(np.argmax(scores))
        return int(h * 0.9)

    def _extract_face_b64(self, frame: np.ndarray, kpts: List[Dict[str, Any]]):
        pts = [kpts[i] for i in range(5) if kpts[i]["conf"] > 0.4]
        if len(pts) < 3:
            return None

        xs = [p["x"] for p in pts]
        ys = [p["y"] for p in pts]
        h, w = frame.shape[:2]

        bounds = _safe_crop_bounds(min(xs) - 40, min(ys) - 80, max(xs) + 40, max(ys) + 40, w, h)
        if not bounds:
            return None
        x1, y1, x2, y2 = bounds
        if (x2 - x1) <= 20:
            return None

        ok, b = cv2.imencode(".jpg", frame[y1:y2, x1:x2])
        if not ok:
            return None
        return base64.b64encode(b).decode("utf-8")

    def _build_sample_indices(self, frame_count: int, sample_interval_pct: int) -> List[int]:
        if frame_count <= 0:
            return []
        interval = max(1, min(int(sample_interval_pct), 100))
        percents = list(range(0, 101, interval))
        if percents[-1] != 100:
            percents.append(100)

        indices: List[int] = []
        last_idx = None
        for pct in percents:
            idx = int(round((frame_count - 1) * (pct / 100.0)))
            idx = max(0, min(idx, frame_count - 1))
            if last_idx is None or idx != last_idx:
                indices.append(idx)
                last_idx = idx
        return indices

    def _encode_frame_b64(self, frame: np.ndarray) -> Optional[str]:
        if frame is None:
            return None
        ok, buf = cv2.imencode(".jpg", frame)
        if not ok:
            return None
        return base64.b64encode(buf).decode("utf-8")

    def _evaluate_face_consistency(self, video_path: str, sample_interval_pct: int = 20) -> Dict[str, Any]:
        if not self.face_compare_fn:
            return {"consistent": False, "sample_interval_pct": sample_interval_pct, "samples": [], "note": "face_compare_fn_unavailable"}

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return {"consistent": False, "sample_interval_pct": sample_interval_pct, "samples": [], "note": "video_unavailable"}

        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        cap.release()
        if frame_count <= 0:
            return {"consistent": False, "sample_interval_pct": sample_interval_pct, "samples": [], "note": "frame_count_unavailable"}

        indices = self._build_sample_indices(frame_count, sample_interval_pct)
        samples: List[Dict[str, Any]] = []
        reference_b64: Optional[str] = None

        for idx in indices:
            frame = read_frame_at(video_path, int(idx))
            sample: Dict[str, Any] = {"frame": int(idx), "success": False}
            if frame is None:
                sample["error"] = "frame_unavailable"
                samples.append(sample)
                continue

            b64 = self._encode_frame_b64(frame)
            if not b64:
                sample["error"] = "encode_failed"
                samples.append(sample)
                continue

            if reference_b64 is None:
                try:
                    ref_res = self.face_compare_fn(b64, b64)
                except Exception:
                    sample["error"] = "face_not_detected"
                    samples.append(sample)
                    continue

                sample["success"] = True
                sample["reference"] = True
                if isinstance(ref_res, dict):
                    if "similarity" in ref_res:
                        sample["similarity"] = ref_res["similarity"]
                    if "threshold" in ref_res:
                        sample["threshold"] = ref_res["threshold"]
                    sample["match"] = bool(ref_res.get("match", True))
                else:
                    sample["match"] = True

                reference_b64 = b64
                samples.append(sample)
                continue

            try:
                cmp_res = self.face_compare_fn(reference_b64, b64)
            except Exception:
                sample["error"] = "compare_failed"
                samples.append(sample)
                continue

            sample["success"] = True
            if isinstance(cmp_res, dict):
                sample["match"] = bool(cmp_res.get("match", False))
                if "similarity" in cmp_res:
                    sample["similarity"] = cmp_res["similarity"]
                if "threshold" in cmp_res:
                    sample["threshold"] = cmp_res["threshold"]
            else:
                sample["match"] = bool(cmp_res)
            samples.append(sample)

        successful_samples = [s for s in samples if s.get("success")]
        consistent = bool(successful_samples) and all(
            s.get("match", True) for s in successful_samples if not s.get("reference")
        )

        return {
            "consistent": consistent,
            "sample_interval_pct": sample_interval_pct,
            "frame_count": frame_count,
            "samples": samples,
            "successful_samples": len(successful_samples),
        }

    def extract_trajectory(self, video_path, stride=3, max_frames=300):
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return [], [], [], 0.0

        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0

        frames_meta = []
        processed = 0
        idx = 0
        faces_start, faces_mid = [], []
        floor_y = None

        # Para no recalcular depth más de la cuenta:
        last_depth = None
        last_depth_idx = -999999

        while processed < max_frames:
            ret, frame = cap.read()
            if not ret:
                break

            if idx % stride != 0:
                idx += 1
                continue

            if processed == 10:
                floor_y = self._infer_floor_y(frame)

            ball = self.det.detect(frame)
            person = self.pose.detect(frame)

            frame_data = {
                "idx": idx,
                "time": (idx / fps) if fps else 0,
                "ball": None,
                "feet": None,
                "floor_y": floor_y,
            }

            if ball and person:
                b = ball[0]
                p = person[0]

                # Depth solo si está habilitado y cada N frames (cache simple)
                depth = None
                if self.enable_depth and self.midas is not None:
                    if (processed - last_depth_idx) >= self.depth_every_n:
                        last_depth = self.get_depth(frame)
                        last_depth_idx = processed
                    depth = last_depth

                bx, by, bw, bh = b[:4]

                # coordenadas seguras para muestreo depth
                if depth is not None:
                    cx = _clamp_int(bx + bw // 2, 0, depth.shape[1] - 1)
                    cy = _clamp_int(by + bh // 2, 0, depth.shape[0] - 1)
                    bz = int(depth[cy, cx])
                else:
                    bz = 128

                frame_data["ball"] = {"x": bx + bw // 2, "y": by + bh, "z": int(bz), "w": bw}

                f_l, f_r = p["kpts"][15], p["kpts"][16]
                if depth is not None:
                    xl = _clamp_int(f_l["x"], 0, depth.shape[1] - 1)
                    yl = _clamp_int(f_l["y"], 0, depth.shape[0] - 1)
                    xr = _clamp_int(f_r["x"], 0, depth.shape[1] - 1)
                    yr = _clamp_int(f_r["y"], 0, depth.shape[0] - 1)
                    fz_l = int(depth[yl, xl])
                    fz_r = int(depth[yr, xr])
                else:
                    fz_l = 128
                    fz_r = 128

                frame_data["feet"] = {
                    "L": {"x": f_l["x"], "y": f_l["y"], "z": int(fz_l), "conf": f_l["conf"]},
                    "R": {"x": f_r["x"], "y": f_r["y"], "z": int(fz_r), "conf": f_r["conf"]},
                }
                frame_data["person_h"] = p["box"][3]
                frame_data["kpts"] = p["kpts"]
                frame_data["ball_box"] = b

                if processed < 50 and len(faces_start) < 4:
                    f = self._extract_face_b64(frame, p["kpts"])
                    if f:
                        faces_start.append(f)
                elif processed > (max_frames / 2) and len(faces_mid) < 4:
                    f = self._extract_face_b64(frame, p["kpts"])
                    if f:
                        faces_mid.append(f)

            frames_meta.append(frame_data)
            processed += 1
            idx += 1

        cap.release()
        return frames_meta, faces_start, faces_mid, fps

    def analyze_trajectory(self, frames_meta):
        valid_widths = []
        player_heights = []

        for f in frames_meta:
            if f["ball"] and f["feet"]:
                feet_y = (f["feet"]["L"]["y"] + f["feet"]["R"]["y"]) / 2
                if abs(f["ball"]["y"] - feet_y) < 150:
                    valid_widths.append(f["ball"]["w"])
                    player_heights.append(f.get("person_h", 0))

        for w in valid_widths:
            self.calibrator.add_sample(w)
        if player_heights:
            self.calibrator.finalize(float(np.median(player_heights)))

        scale = self.calibrator.px_per_cm if self.calibrator.is_calibrated else 2.0

        raw_y = []
        last_val = 0
        for f in frames_meta:
            val = f["ball"]["y"] if f["ball"] else last_val
            raw_y.append(val)
            last_val = val

        smooth_y = smooth_signal(raw_y, window_size=5)

        events_log = []
        full_trajectory = []

        juggles = 0
        last_hit_frame_idx = -100
        dribble_state = "Parado"

        stats_counters = {"total": 0, "left": 0, "right": 0, "simultaneous": 0}

        for i, f in enumerate(frames_meta):
            if not f["ball"] or not f["feet"]:
                continue

            ball_y = float(smooth_y[i])
            prev_y = float(smooth_y[i - 1]) if i > 0 else ball_y
            velocity_y = ball_y - prev_y

            # 3D trajectory
            full_trajectory.append({
                "frame": int(f["idx"]),
                "x": int(f["ball"]["x"]),
                "y": int(ball_y),
                "z": int(f["ball"]["z"]),
            })

            floor = f["floor_y"] if f.get("floor_y") else max(f["feet"]["L"]["y"], f["feet"]["R"]["y"])
            height_cm = (float(floor) - ball_y) / float(scale)

            # JUGGLING
            if height_cm > 15:
                is_contact = (velocity_y < -2.0)

                hit_L = False
                hit_R = False

                if f["feet"]["L"]["conf"] > 0.5:
                    dx = abs(f["feet"]["L"]["x"] - f["ball"]["x"]) / scale
                    dy = abs(f["feet"]["L"]["y"] - ball_y) / scale
                    dz = abs(f["feet"]["L"]["z"] - f["ball"]["z"])
                    if ((is_contact and dx < 25 and dy < 30) or (dx < 15 and dy < 10)) and dz < 50:
                        hit_L = True

                if f["feet"]["R"]["conf"] > 0.5:
                    dx = abs(f["feet"]["R"]["x"] - f["ball"]["x"]) / scale
                    dy = abs(f["feet"]["R"]["y"] - ball_y) / scale
                    dz = abs(f["feet"]["R"]["z"] - f["ball"]["z"])
                    if ((is_contact and dx < 25 and dy < 30) or (dx < 15 and dy < 10)) and dz < 50:
                        hit_R = True

                if (hit_L or hit_R) and (f["idx"] - last_hit_frame_idx) > 12:
                    juggles += 1
                    last_hit_frame_idx = f["idx"]

                    if hit_L and hit_R:
                        hit_type = "Simultaneo"
                        stats_counters["simultaneous"] += 1
                        leg_label = "Simul"
                    elif hit_L:
                        hit_type = "Izq"
                        stats_counters["left"] += 1
                        leg_label = "Izq"
                    else:
                        hit_type = "Der"
                        stats_counters["right"] += 1
                        leg_label = "Der"

                    stats_counters["total"] = juggles

                    events_log.append({
                        "idx": f["idx"],
                        "type": f"JUGGLE! ({hit_type})",
                        "count": juggles,
                        "hit_leg": leg_label
                    })

            # DRIBBLE
            else:
                d_l = np.hypot((f["feet"]["L"]["x"] - f["ball"]["x"]), (f["feet"]["L"]["y"] - ball_y)) / scale
                d_r = np.hypot((f["feet"]["R"]["x"] - f["ball"]["x"]), (f["feet"]["R"]["y"] - ball_y)) / scale

                if min(d_l, d_r) < 60:
                    cx = (f["feet"]["L"]["x"] + f["feet"]["R"]["x"]) / 2
                    if f["ball"]["x"] > cx + 15:
                        dribble_state = "Derecha >>"
                    elif f["ball"]["x"] < cx - 15:
                        dribble_state = "<< Izquierda"
                    else:
                        dribble_state = "Control"

                    if i % 15 == 0:
                        events_log.append({"idx": f["idx"], "type": dribble_state, "count": juggles})

        return events_log, stats_counters, dribble_state, full_trajectory

    def generate_visuals(self, video_path, events_log, frames_meta):
        # Optimización clave: dict para lookup O(1)
        meta_map = {m["idx"]: m for m in frames_meta}
        event_map = {e["idx"]: e for e in events_log}

        target_indices = set(event_map.keys())
        for f in frames_meta:
            if f["idx"] % 30 == 0:
                target_indices.add(f["idx"])

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return []

        images_out = []
        curr_frame = 0

        # Depth: si está habilitado, lo cacheamos en el loop (evita recalcular innecesario)
        last_depth = None
        last_depth_frame = -999999

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if curr_frame in target_indices:
                meta = meta_map.get(curr_frame)
                if meta and meta.get("ball"):
                    evt = event_map.get(curr_frame, {})
                    txt = evt.get("type", "")
                    cnt = evt.get("count", meta.get("last_count", 0))
                    is_hit = "JUGGLE" in txt
                    hit_leg = evt.get("hit_leg", "")

                    depth_map = None
                    if self.enable_depth and self.midas is not None:
                        if (curr_frame - last_depth_frame) >= (self.depth_every_n * 3):
                            last_depth = self.get_depth(frame)
                            last_depth_frame = curr_frame
                        depth_map = last_depth

                    vis = self._draw_panel(frame, meta, depth_map, txt, cnt, is_hit, hit_leg)

                    ok, b = cv2.imencode(".jpg", vis)
                    if ok:
                        b64 = base64.b64encode(b).decode("utf-8")
                        images_out.append({"image_id": str(curr_frame), "image_base64": f"data:image/jpeg;base64,{b64}"})

                    if len(images_out) >= 60:
                        break

            curr_frame += 1

        cap.release()
        return images_out

    def _draw_panel(self, frame, meta, depth_map, event_txt, count, is_hit, hit_leg):
        h, w = frame.shape[:2]
        panel = np.zeros((h, 320, 3), dtype=np.uint8)
        panel[:] = (30, 30, 30)

        ball = meta["ball"]
        kpts = meta.get("kpts", [])

        def to_p(x, y):
            return (20 + int(x / w * 280), 20 + int(y / h * (h - 40)))

        c_bone, c_head = (100, 100, 100), (200, 200, 255)
        c_joint, c_hit = (0, 200, 0), (0, 255, 255)
        base_ball_color = c_hit if is_hit else (0, 140, 255)

        for a, b in self.skeleton_links:
            ka, kb = kpts[a], kpts[b]
            if ka["conf"] > 0.4 and kb["conf"] > 0.4:
                pa, pb = to_p(ka["x"], ka["y"]), to_p(kb["x"], kb["y"])
                col, thick = c_bone, 2
                if is_hit:
                    check_L = (hit_leg in ["Izq", "Simul"]) and (a in [11, 13, 15] and b in [11, 13, 15])
                    check_R = (hit_leg in ["Der", "Simul"]) and (a in [12, 14, 16] and b in [12, 14, 16])
                    if check_L or check_R:
                        col, thick = c_hit, 3
                cv2.line(panel, pa, pb, col, thick)

        for i, kp in enumerate(kpts):
            if kp["conf"] > 0.4:
                z_val = 128
                if depth_map is not None:
                    yy = _clamp_int(kp["y"], 0, depth_map.shape[0] - 1)
                    xx = _clamp_int(kp["x"], 0, depth_map.shape[1] - 1)
                    z_val = int(depth_map[yy, xx])

                radius = max(3, int((z_val / 255.0) * 9))
                color = c_joint
                if i <= 4:
                    color = c_head
                    radius += 2

                if is_hit:
                    if (hit_leg in ["Izq", "Simul"]) and i in [13, 15]:
                        color = c_hit
                        radius += 3
                    if (hit_leg in ["Der", "Simul"]) and i in [14, 16]:
                        color = c_hit
                        radius += 3

                cv2.circle(panel, to_p(kp["x"], kp["y"]), radius, color, -1)

        bc = to_p(ball["x"], ball["y"] - ball["w"] // 2)
        scale_factor = 280.0 / w
        real_radius_panel = max(4, int((ball["w"] / 2) * scale_factor))

        overlay = panel.copy()
        cv2.circle(overlay, bc, real_radius_panel, base_ball_color, -1)
        cv2.addWeighted(overlay, 0.5, panel, 0.5, 0, panel)
        cv2.circle(panel, bc, real_radius_panel, base_ball_color, 3)

        cv2.putText(panel, f"Juggl: {count}", (10, 450), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        if event_txt:
            cv2.putText(panel, event_txt, (10, 490), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        ball_info = f"N {self.calibrator.selected_size_id} ({self.calibrator.real_diameter_cm}cm)"
        cv2.putText(panel, f"Ball: {ball_info}", (10, 520), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
        return np.hstack((frame, panel))

    def run_on_video(
        self,
        video_path,
        frame_stride=3,
        max_frames=300,
        hit_threshold=0.4,
        return_images=True,
        face_sample_interval_pct=20
    ):
        t0 = time.time()

        meta, f_start, f_mid, fps = self.extract_trajectory(video_path, stride=frame_stride, max_frames=max_frames)
        logs, stats_data, end_state, trajectory_3d = self.analyze_trajectory(meta)

        hit_imgs = []
        if return_images:
            hit_imgs = self.generate_visuals(video_path, logs, meta)

        face_res = "N/A"
        if self.face_compare_fn and f_start and f_mid:
            try:
                face_res = self.face_compare_fn(f_start[0], f_mid[0])
            except Exception:
                pass

        face_consistency = "N/A"
        if self.face_compare_fn:
            try:
                face_consistency = self._evaluate_face_consistency(video_path, sample_interval_pct=face_sample_interval_pct)
            except Exception:
                pass

        total_t = time.time() - t0

        last_leg = "N/A"
        for e in reversed(logs):
            if "JUGGLE" in e["type"]:
                last_leg = e.get("hit_leg", "N/A")
                break

        return {
            "id": int(time.time()),
            "hit_images": hit_imgs,
            "trajectory": trajectory_3d,
            "meta": {
                "performance": {"total_time_s": round(total_t, 2), "frames_analyzed": len(meta)},
                "stats": {
                    "total_juggles": stats_data["total"],
                    "count_left": stats_data["left"],
                    "count_right": stats_data["right"],
                    "count_simultaneous": stats_data["simultaneous"],
                    "last_hit_leg": last_leg,
                    "final_state": end_state,
                    "ball_size": f"N {self.calibrator.selected_size_id}",
                },
                "face_verification": face_res,
                "face_consistency": face_consistency,
            },
        }
