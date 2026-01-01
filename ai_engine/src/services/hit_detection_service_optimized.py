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
# 2. MODELOS IA (WRAPPERS 416 OPTIMIZADOS)
# ==========================================
class YoloBaseWrapper:
    def __init__(self, model_path: str, input_size: Tuple[int, int] = (416, 416), fp16: bool = True):
        self.model_path = model_path
        self.net = None
        self.input_size = input_size
        self.fp16 = fp16

    def load(self) -> bool:
        if not os.path.exists(self.model_path):
            print(f"❌ Modelo no encontrado: {self.model_path}")
            return False
        try:
            # Detectar si es TensorRT Engine o ONNX
            if self.model_path.endswith(".engine"):
                print(f"🚀 Cargando Motor TensorRT: {os.path.basename(self.model_path)}")
                self.net = cv2.dnn.readNetFromModelOptimizer(self.model_path) if hasattr(cv2.dnn, "readNetFromModelOptimizer") else cv2.dnn.readNet(self.model_path)
                self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
                self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
            else:
                self.net = cv2.dnn.readNet(self.model_path)
                self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
                if self.fp16: self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA_FP16)
                else: self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
                
            print(f"✅ Cargado: {os.path.basename(self.model_path)} | Size: {self.input_size}")
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
        
        scores = preds[:, 36] 
        keep = scores > conf
        if not np.any(keep): return []
        
        preds, scores = preds[keep], scores[keep]
        boxes = preds[:, :4].copy()
        boxes[:, 0] -= boxes[:, 2]/2
        boxes[:, 1] -= boxes[:, 3]/2
        
        indices = cv2.dnn.NMSBoxes(boxes.tolist(), scores.tolist(), conf, 0.45)
        if len(indices) == 0: return []
        
        sx, sy = w / self.input_size[0], h / self.input_size[1]
        res = []
        for i in indices.flatten():
            b = boxes[i]
            res.append([int(b[0]*sx), int(b[1]*sy), int(b[2]*sx), int(b[3]*sy), float(scores[i])])
        return sorted(res, key=lambda x: x[4])[-1:]

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
        
        preds, scores = preds[keep], scores[keep]
        kpts_raw = preds[:, 5:]
        
        indices = cv2.dnn.NMSBoxes(preds[:, :4].tolist(), scores.tolist(), conf, 0.5)
        if len(indices) == 0: return []
        
        sx, sy = w / self.input_size[0], h / self.input_size[1]
        res = []
        for i in indices.flatten():
            pk = kpts_raw[i].reshape(-1, 3)
            kpts = [{"x": int(p[0]*sx), "y": int(p[1]*sy), "conf": float(p[2])} for p in pk]
            box = preds[i, :4]
            bbox = [int((box[0]-box[2]/2)*sx), int((box[1]-box[3]/2)*sy), int(box[2]*sx), int(box[3]*sy)]
            area = bbox[2]*bbox[3]
            res.append({"kpts": kpts, "box": bbox, "area": area})
        return sorted(res, key=lambda x: x["area"])[-1:]

# ==========================================
# 3. SERVICIO OPTIMIZADO + VISUALES + FACE CHECK
# ==========================================
class HitDetectionServiceOptimized:
    def __init__(self, default_model_dirs=None, segment_floor_fn=None, face_compare_fn=None,
                 yolo_size=416, use_fp16=True, enable_depth=False, midas_size=256):
        
        self.models_dir = "/app/ai_engine/models"
        env_size = os.getenv("YOLO_SIZE")
        self.yolo_size = int(env_size) if env_size else yolo_size

        # Definimos nombres base
        det_base = f"yolov8n_{self.yolo_size}"
        pose_base = f"yolov8n-pose_{self.yolo_size}"
        
        # 1. Determinar rutas (Prioridad: Engine > ONNX)
        self.paths = {
            "det": self._get_best_model(det_base),
            "pose": self._get_best_model(pose_base),
            "midas": os.path.join(self.models_dir, "midas_v21_small.onnx"),
        }
        
        self.urls = {
            "det": "https://github.com/pellit/video-analytics-saas/raw/main/ai_engine/yolov8n.onnx",
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

    def _get_best_model(self, base_name):
        """Busca primero .engine, si no existe retorna ruta .onnx"""
        engine_path = os.path.join(self.models_dir, f"{base_name}.engine")
        onnx_path = os.path.join(self.models_dir, f"{base_name}.onnx")
        
        if os.path.exists(engine_path):
            return engine_path
        return onnx_path

    def _setup_models(self):
        os.makedirs(self.models_dir, exist_ok=True)
        
        for k, path in self.paths.items():
            # Si el path (sea engine u onnx) no existe, intentamos recuperar el ONNX
            if not os.path.exists(path):
                # Si era un engine y no está, hacemos fallback a ONNX para descargarlo
                if path.endswith(".engine"):
                    fallback_path = path.replace(".engine", ".onnx")
                    # Si tampoco está el ONNX, descargamos
                    if not os.path.exists(fallback_path) and k in self.urls:
                        try: 
                            print(f"⬇️ Descargando modelo base (fallback): {k}")
                            urllib.request.urlretrieve(self.urls[k], fallback_path)
                            self.paths[k] = fallback_path # Actualizamos a usar ONNX
                        except: pass
                # Si era ONNX y no está, descargamos
                elif k in self.urls:
                    try: urllib.request.urlretrieve(self.urls[k], path)
                    except: pass
        
        size = (self.yolo_size, self.yolo_size)
        self.det = YoloDetWrapper(self.paths["det"], input_size=size, fp16=self.use_fp16)
        self.pose = YoloPoseWrapper(self.paths["pose"], input_size=size, fp16=self.use_fp16)
        self.det.load(); self.pose.load()
        
        self.midas = None
        if self.enable_depth and os.path.exists(self.paths["midas"]):
            try:
                self.midas = cv2.dnn.readNet(self.paths["midas"])
                self.midas.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
                if self.use_fp16: self.midas.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA_FP16)
                else: self.midas.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
            except: pass

    def get_depth(self, frame):
        if not self.midas: return None
        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(frame, 1/255.0, (self.midas_size, self.midas_size), mean=(123.675, 116.28, 103.53), swapRB=True, crop=False)
        self.midas.setInput(blob)
        d = self.midas.forward()
        return cv2.normalize(cv2.resize(d[0,0], (w, h)), None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)

    # --- CARA & HELPERS ---
    def _extract_face_b64(self, frame, kpts):
        pts = [kpts[i] for i in range(5) if kpts[i]['conf']>0.4]
        if len(pts)<3: return None
        xs, ys = [p['x'] for p in pts], [p['y'] for p in pts]
        x1, y1 = max(0, min(xs)-40), max(0, min(ys)-80)
        x2, y2 = min(frame.shape[1], max(xs)+40), min(frame.shape[0], max(ys)+40)
        if x2-x1>20:
            _, b = cv2.imencode('.jpg', frame[y1:y2, x1:x2])
            return base64.b64encode(b).decode('utf-8')
        return None

    def _build_sample_indices(self, frame_count: int, sample_interval_pct: int) -> List[int]:
        if frame_count <= 0: return []
        interval = max(1, min(sample_interval_pct, 100))
        percents = list(range(0, 101, interval))
        if percents[-1] != 100: percents.append(100)
        indices = []
        for pct in percents:
            idx = int(round((frame_count - 1) * (pct / 100.0)))
            indices.append(max(0, min(idx, frame_count - 1)))
        return sorted(list(set(indices)))

    def _encode_frame_b64(self, frame: np.ndarray) -> Optional[str]:
        if frame is None: return None
        ok, buf = cv2.imencode('.jpg', frame)
        return base64.b64encode(buf).decode('utf-8') if ok else None

    def _evaluate_face_consistency(self, video_path: str, sample_interval_pct: int = 20) -> Dict[str, Any]:
        if not self.face_compare_fn:
            return {"consistent": False, "note": "face_compare_fn_unavailable"}

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened(): return {"consistent": False}
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        cap.release()
        
        indices = self._build_sample_indices(frame_count, sample_interval_pct)
        samples = []
        reference_b64 = None

        for idx in indices:
            frame = read_frame_at(video_path, int(idx))
            if frame is None: continue
            b64 = self._encode_frame_b64(frame)
            if not b64: continue

            if reference_b64 is None:
                reference_b64 = b64
                samples.append({"frame": idx, "match": True, "reference": True})
            else:
                try:
                    res = self.face_compare_fn(reference_b64, b64)
                    match = res.get("match", False) if isinstance(res, dict) else bool(res)
                    samples.append({"frame": idx, "match": match})
                except:
                    samples.append({"frame": idx, "match": False, "error": "compare_fail"})

        consistent = (len(samples) > 1) and all(s["match"] for s in samples if not s.get("reference"))
        return {"consistent": consistent, "samples": samples}

    def extract_trajectory(self, video_path, stride=3, max_frames=300):
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frames_meta = [] 
        processed = 0
        idx = 0
        faces_start, faces_mid = [], []
        
        while processed < max_frames:
            ret, frame = cap.read()
            if not ret: break
            if idx % stride != 0: 
                idx += 1; continue
            
            ball = self.det.detect(frame)
            person = self.pose.detect(frame)
            
            frame_data = {"idx": idx, "time": idx/fps, "ball": None, "feet": None, "floor_y": int(frame.shape[0]*0.9)}

            if ball and person:
                b = ball[0]; p = person[0]
                depth = self.get_depth(frame) if self.enable_depth else None
                
                bx, by, bw, bh = b[:4]
                bz = 128
                if depth is not None:
                    cx = _clamp_int(bx+bw//2, 0, depth.shape[1]-1)
                    cy = _clamp_int(by+bh//2, 0, depth.shape[0]-1)
                    bz = depth[cy, cx]
                
                frame_data["ball"] = {"x": bx+bw//2, "y": by+bh, "z": int(bz), "w": bw}
                
                f_l = p["kpts"][15]; f_r = p["kpts"][16]
                frame_data["feet"] = {
                    "L": {"x": f_l["x"], "y": f_l["y"], "z": 128, "conf": f_l["conf"]},
                    "R": {"x": f_r["x"], "y": f_r["y"], "z": 128, "conf": f_r["conf"]}
                }
                frame_data["person_h"] = p["box"][3]
                frame_data["kpts"] = p["kpts"]
                frame_data["ball_box"] = b

                if processed < 50 and len(faces_start) < 3:
                    f = self._extract_face_b64(frame, p["kpts"])
                    if f: faces_start.append(f)
                elif processed > (max_frames/2) and len(faces_mid) < 3:
                    f = self._extract_face_b64(frame, p["kpts"])
                    if f: faces_mid.append(f)

            frames_meta.append(frame_data)
            processed += 1
            idx += 1
            
        cap.release()
        return frames_meta, faces_start, faces_mid, fps

    def analyze_trajectory(self, frames_meta):
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
            
            floor = f["floor_y"]
            height_cm = (floor - ball_y) / scale
            
            if height_cm > 15:
                is_contact = vel_y < -2.0
                hit_L = False
                hit_R = False
                
                if f["feet"]["L"]["conf"] > 0.5:
                    dx = abs(f["feet"]["L"]["x"] - f["ball"]["x"]) / scale
                    dy = abs(f["feet"]["L"]["y"] - ball_y) / scale
                    if (is_contact and dx < 25 and dy < 30) or (dx < 15 and dy < 10): hit_L = True
                
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
            else:
                d_l = np.hypot(f["feet"]["L"]["x"]-f["ball"]["x"], f["feet"]["L"]["y"]-ball_y) / scale
                d_r = np.hypot(f["feet"]["R"]["x"]-f["ball"]["x"], f["feet"]["R"]["y"]-ball_y) / scale
                if min(d_l, d_r) < 60: dribble_state = "Control"

        return events_log, stats, dribble_state, full_trajectory

    def generate_visuals(self, video_path, events_log, frames_meta):
        event_map = {e["idx"]: e for e in events_log}
        target_indices = set(e["idx"] for e in events_log)
        for f in frames_meta:
            if f["idx"] % 30 == 0: target_indices.add(f["idx"])
            
        cap = cv2.VideoCapture(video_path)
        images_out = []
        curr_frame = 0
        
        while True:
            ret, frame = cap.read()
            if not ret: break
            
            if curr_frame in target_indices:
                meta = next((m for m in frames_meta if m["idx"] == curr_frame), None)
                if meta and meta["ball"]:
                    evt = event_map.get(curr_frame, {})
                    txt = evt.get("type", "")
                    cnt = evt.get("count", meta.get("last_count", 0))
                    is_hit = "JUGGLE" in txt
                    hit_leg = evt.get("hit_leg", "")
                    
                    depth_map = self.get_depth(frame) if self.enable_depth else None
                    vis = self._draw_panel(frame, meta, depth_map, txt, cnt, is_hit, hit_leg)
                    
                    _, b = cv2.imencode('.jpg', vis)
                    b64 = base64.b64encode(b).decode('utf-8')
                    images_out.append({"image_id": str(curr_frame), "image_base64": f"data:image/jpeg;base64,{b64}"})
                    if len(images_out) >= 60: break
            curr_frame += 1
        cap.release()
        return images_out

    def _draw_panel(self, frame, meta, depth_map, event_txt, count, is_hit, hit_leg):
        h, w = frame.shape[:2]
        panel = np.zeros((h, 320, 3), dtype=np.uint8); panel[:] = (30,30,30)
        ball = meta["ball"]
        kpts = meta["kpts"]
        
        def to_p(x, y): return (20 + int(x/w*280), 20 + int(y/h*(h-40)))
        
        c_bone, c_hit = (100, 100, 100), (0, 255, 255)
        base_ball_color = c_hit if is_hit else (0, 140, 255) 

        for a, b in self.skeleton_links:
            ka, kb = kpts[a], kpts[b]
            if ka['conf'] > 0.4 and kb['conf'] > 0.4:
                pa, pb = to_p(ka['x'], ka['y']), to_p(kb['x'], kb['y'])
                col, thick = c_bone, 2
                if is_hit:
                    check_L = (hit_leg in ["Izq", "Simul"]) and (a in [11,13,15] and b in [11,13,15])
                    check_R = (hit_leg in ["Der", "Simul"]) and (a in [12,14,16] and b in [12,14,16])
                    if check_L or check_R: col, thick = c_hit, 3
                cv2.line(panel, pa, pb, col, thick)

        for i, kp in enumerate(kpts):
            if kp['conf'] > 0.4:
                cv2.circle(panel, to_p(kp['x'], kp['y']), 3, (0,200,0), -1)

        bc = to_p(ball["x"], ball["y"] - ball["w"]//2)
        cv2.circle(panel, bc, 6, base_ball_color, -1)

        cv2.putText(panel, f"Juggl: {count}", (10, 450), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2)
        if event_txt: cv2.putText(panel, event_txt, (10, 490), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)
        
        return np.hstack((frame, panel))

    def run_on_video(self, video_path, frame_stride=3, max_frames=300, hit_threshold=0.4, return_images=True, face_sample_interval_pct=20):
        t0 = time.time()
        meta, f_start, f_mid, fps = self.extract_trajectory(video_path, stride=frame_stride, max_frames=max_frames)
        logs, stats, end_state, traj = self.analyze_trajectory(meta)
        
        hit_imgs = []
        if return_images: hit_imgs = self.generate_visuals(video_path, logs, meta)
            
        face_res = "N/A"
        if self.face_compare_fn and f_start and f_mid:
            try: face_res = self.face_compare_fn(f_start[0], f_mid[0])
            except: pass

        face_consistency = "N/A"
        if self.face_compare_fn:
            try: face_consistency = self._evaluate_face_consistency(video_path, sample_interval_pct=face_sample_interval_pct)
            except: pass

        total_t = time.time() - t0
        last_leg = logs[-1]["hit_leg"] if logs else "N/A"
        
        return {
            "id": int(time.time()),
            "hit_images": hit_imgs,
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
                "face_verification": face_res,
                "face_consistency": face_consistency,
                "models_used": {
                    "detection": os.path.basename(self.paths["det"]),
                    "pose": os.path.basename(self.paths["pose"])
                }
            }
        }