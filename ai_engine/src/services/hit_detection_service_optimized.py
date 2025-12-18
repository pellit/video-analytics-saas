import cv2
import numpy as np
import os
import urllib.request
import time
import base64
from collections import deque
from typing import Any, Callable, Dict, List, Optional, Tuple

def smooth_signal(data_list, window_size=5):
    """Suaviza una lista de números usando media móvil"""
    if len(data_list) < window_size: return data_list
    return np.convolve(data_list, np.ones(window_size)/window_size, mode='same').tolist()

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
        self.px_per_cm = 2.0 # Valor safe

    def add_sample(self, width_px):
        # El filtrado de "cerca de los pies" se hace antes de llamar a esta función
        if 10 < width_px < 200: 
            self.samples.append(width_px)

    def finalize(self, player_h_px):
        if not self.samples: return
        median_px = np.median(self.samples)
        if median_px == 0: return

        # Hipótesis Talla 5
        scale_t5 = median_px / 22.0
        h_hyp = player_h_px / scale_t5
        
        if h_hyp > 155: self.selected_size_id = 5
        elif 135 < h_hyp <= 155: self.selected_size_id = 4
        else: self.selected_size_id = 3
            
        self.real_diameter_cm = self.SIZES[self.selected_size_id]
        raw_scale = median_px / self.real_diameter_cm
        self.px_per_cm = max(0.5, min(raw_scale, 10.0)) # Clamp seguridad
        self.is_calibrated = True

# ==========================================
# 2. MODELOS IA (WRAPPERS)
# ==========================================
class YoloBaseWrapper:
    def __init__(self, model_path):
        self.model_path = model_path
        self.net = None
        self.input_size = (640, 640)
    
    def load(self):
        if not os.path.exists(self.model_path): return False
        try:
            self.net = cv2.dnn.readNet(self.model_path)
            self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
            self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
            return True
        except: return False

    def preprocess(self, img):
        return cv2.dnn.blobFromImage(img, 1/255.0, self.input_size, swapRB=True, crop=False)

class YoloDetWrapper(YoloBaseWrapper):
    def detect(self, img, conf=0.15): # Umbral bajo para batch processing
        if not self.net: return []
        h, w = img.shape[:2]
        self.net.setInput(self.preprocess(img))
        preds = np.squeeze(self.net.forward()).T
        
        if preds.ndim < 2 or preds.shape[1] <= 36: return []
        
        scores = preds[:, 32+4] 
        keep = scores > conf
        preds, scores = preds[keep], scores[keep]
        if len(scores) == 0: return []
        
        boxes = preds[:, :4]
        boxes[:, 0] -= boxes[:, 2]/2
        boxes[:, 1] -= boxes[:, 3]/2
        
        indices = cv2.dnn.NMSBoxes(boxes.tolist(), scores.tolist(), conf, 0.5)
        sx, sy = w/640, h/640
        res = []
        for i in indices.flatten():
            b = boxes[i]
            res.append([int(b[0]*sx), int(b[1]*sy), int(b[2]*sx), int(b[3]*sy), float(scores[i])])
        return sorted(res, key=lambda x: x[4])[-1:] 

class YoloPoseWrapper(YoloBaseWrapper):
    def detect(self, img, conf=0.5):
        if not self.net: return []
        h, w = img.shape[:2]
        self.net.setInput(self.preprocess(img))
        preds = np.squeeze(self.net.forward()).T
        
        if preds.ndim < 2: return []
        scores = preds[:, 4]
        keep = scores > conf
        preds = preds[keep]
        if len(preds) == 0: return []
        
        kpts_raw = preds[:, 5:]
        indices = cv2.dnn.NMSBoxes(preds[:, :4].tolist(), scores[keep].tolist(), conf, 0.5)
        
        sx, sy = w/640, h/640
        res = []
        for i in indices.flatten():
            pk = kpts_raw[i].reshape(-1, 3)
            kpts = [{"x": int(p[0]*sx), "y": int(p[1]*sy), "conf": float(p[2])} for p in pk]
            box = preds[i, :4]
            bbox = [int((box[0]-box[2]/2)*sx), int((box[1]-box[3]/2)*sy), int(box[2]*sx), int(box[3]*sy)]
            area = bbox[2] * bbox[3]
            res.append({"kpts": kpts, "box": bbox, "area": area})
        return sorted(res, key=lambda x: x["area"])[-1:] 

# ==========================================
# 3. SERVICIO OPTIMIZADO (2 PASOS - SIN API INTERNA)
# ==========================================
class HitDetectionServiceOptimized:
    def __init__(
        self,
        default_model_dirs: List[str] = None, # Mantener firma compatible
        segment_floor_fn: Optional[Callable[[np.ndarray], Optional[int]]] = None,
        face_compare_fn: Optional[Callable[[str, str], Any]] = None
    ):
        self.models_dir = "/app/ai_engine/models"
        self.paths = {
            "det": os.path.join(self.models_dir, "yolov8n.onnx"),
            "pose": os.path.join(self.models_dir, "yolov8n-pose.onnx"),
            "midas": os.path.join(self.models_dir, "midas_v21_small.onnx")
        }
        # Enlaces HF
        self.urls = {
            "det": "https://github.com/pellit/video-analytics-saas/raw/796d243e692b5b18f0344b033a152dcdd6326f36/ai_engine/yolov8n.onnx",
            "pose": "https://huggingface.co/Xenova/yolov8-pose-onnx/resolve/main/yolov8n-pose.onnx?download=true",
            "midas": "https://github.com/isl-org/MiDaS/releases/download/v2_1/model-small.onnx"
        }
        
        # Funciones inyectadas
        self.segment_floor_fn = segment_floor_fn
        self.face_compare_fn = face_compare_fn
        
        self._setup_models()
        self.calibrator = BallCalibrator()
        
        # Esqueleto visualización
        self.skeleton_links = [
            (5, 11), (6, 12), (11, 13), (13, 15), 
            (12, 14), (14, 16), (11, 12), (5, 6)
        ]

    def _setup_models(self):
        os.makedirs(self.models_dir, exist_ok=True)
        for k, path in self.paths.items():
            if not os.path.exists(path) or os.path.getsize(path) < 1000:
                try: urllib.request.urlretrieve(self.urls[k], path)
                except: pass
        
        self.det = YoloDetWrapper(self.paths["det"])
        self.pose = YoloPoseWrapper(self.paths["pose"])
        self.det.load(); self.pose.load()
        
        self.midas = None
        if os.path.exists(self.paths["midas"]):
            try:
                self.midas = cv2.dnn.readNet(self.paths["midas"])
                self.midas.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
                self.midas.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
            except: pass

    def get_depth(self, frame):
        if not self.midas: return None
        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(frame, 1/255.0, (256, 256), (123.675, 116.28, 103.53), True, False)
        self.midas.setInput(blob)
        d = self.midas.forward()
        return cv2.normalize(cv2.resize(d[0,0], (w, h)), None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)

    # ---------------------------------------------------------
    # HELPERS DE INYECCIÓN
    # ---------------------------------------------------------
    def _infer_floor_y(self, frame: np.ndarray) -> Optional[int]:
        """Intenta usar la función inyectada, o cae en heurística"""
        if self.segment_floor_fn:
            try:
                result = self.segment_floor_fn(frame)
                if isinstance(result, dict): return int(result.get("floor_y", 0))
                if result: return int(result)
            except: pass
        
        # Heurística simple (Sobel horizontal en mitad inferior)
        h, w = frame.shape[:2]
        roi_start = int(h * 0.5)
        gray = cv2.cvtColor(frame[roi_start:, :], cv2.COLOR_BGR2GRAY)
        sobel = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        scores = np.mean(np.abs(sobel), axis=1)
        if scores.size > 0:
            return roi_start + int(np.argmax(scores))
        return int(h * 0.9)

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

    # ---------------------------------------------------------
    # FASE 1: EXTRACCIÓN (Batch)
    # ---------------------------------------------------------
    def extract_trajectory(self, video_path, stride=3, max_frames=300):
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        frames_meta = [] 
        
        processed = 0
        idx = 0
        
        faces_start, faces_mid = [], []
        floor_y = None
        
        while processed < max_frames:
            ret, frame = cap.read()
            if not ret: break
            if idx % stride != 0: 
                idx += 1; continue
            
            # Detectar piso una vez al principio
            if processed == 10:
                floor_y = self._infer_floor_y(frame)

            ball = self.det.detect(frame)
            person = self.pose.detect(frame)
            
            frame_data = {
                "idx": idx, 
                "time": idx/fps if fps else 0,
                "ball": None, 
                "feet": None,
                "floor_y": floor_y
            }

            if ball and person:
                b = ball[0]
                p = person[0] 
                
                depth = self.get_depth(frame)
                
                bx, by, bw, bh = b[:4]
                bz = depth[by+bh//2, bx+bw//2] if depth is not None else 128
                frame_data["ball"] = {"x": bx+bw//2, "y": by+bh, "z": int(bz), "w": bw} # y = bottom
                
                f_l, f_r = p["kpts"][15], p["kpts"][16]
                fz_l = depth[f_l['y'], f_l['x']] if depth is not None else 128
                fz_r = depth[f_r['y'], f_r['x']] if depth is not None else 128
                
                frame_data["feet"] = {
                    "L": {"x": f_l['x'], "y": f_l['y'], "z": int(fz_l), "conf": f_l['conf']},
                    "R": {"x": f_r['x'], "y": f_r['y'], "z": int(fz_r), "conf": f_r['conf']}
                }
                frame_data["person_h"] = p["box"][3]
                frame_data["kpts"] = p["kpts"] 
                frame_data["ball_box"] = b 
                
                # Recolectar caras
                if processed < 50 and len(faces_start) < 4:
                    f = self._extract_face_b64(frame, p["kpts"])
                    if f: faces_start.append(f)
                elif processed > (max_frames/2) and len(faces_mid) < 4:
                    f = self._extract_face_b64(frame, p["kpts"])
                    if f: faces_mid.append(f)

            frames_meta.append(frame_data)
            processed += 1
            idx += 1
            
        cap.release()
        return frames_meta, faces_start, faces_mid, fps

    # ---------------------------------------------------------
    # FASE 2: ANÁLISIS (Batch Logic)
    # ---------------------------------------------------------
    def analyze_trajectory(self, frames_meta):
        # 1. Calibración Global
        valid_widths = []
        player_heights = []
        
        for f in frames_meta:
            if f["ball"] and f["feet"]:
                feet_y = (f["feet"]["L"]["y"] + f["feet"]["R"]["y"]) / 2
                # Pelota cerca del suelo (plano pies)
                if abs(f["ball"]["y"] - feet_y) < 150:
                    valid_widths.append(f["ball"]["w"])
                    player_heights.append(f["person_h"])
        
        # --- FIX: add_sample ahora solo toma 1 argumento ---
        for w in valid_widths: self.calibrator.add_sample(w)
        
        if player_heights:
             self.calibrator.finalize(np.median(player_heights))
        
        scale = self.calibrator.px_per_cm if self.calibrator.is_calibrated else 2.0
        
        # 2. Suavizado
        raw_y = []
        last_val = 0
        for f in frames_meta:
            val = f["ball"]["y"] if f["ball"] else last_val
            raw_y.append(val)
            last_val = val
        
        smooth_y = smooth_signal(raw_y, window_size=5)

        # 3. Detección Eventos
        events_log = []
        juggles = 0
        last_hit_frame_idx = -100
        dribble_state = "Parado"

        for i, f in enumerate(frames_meta):
            if not f["ball"] or not f["feet"]: continue
            
            ball_y = smooth_y[i]
            prev_y = smooth_y[i-1] if i > 0 else ball_y
            velocity_y = ball_y - prev_y 
            
            floor = f["floor_y"] if f["floor_y"] else max(f["feet"]["L"]["y"], f["feet"]["R"]["y"])
            height_cm = (floor - ball_y) / scale
            
            # --- JUGGLING ---
            if height_cm > 15:
                # Condición relajada: Sube O está estable cerca del pie
                is_contact = (velocity_y < -1.5) # Golpe fuerte
                
                for leg_label, foot in [("Izq", f["feet"]["L"]), ("Der", f["feet"]["R"])]:
                    if foot["conf"] < 0.5: continue
                    
                    dx = abs(foot["x"] - f["ball"]["x"]) / scale
                    dy = abs(foot["y"] - ball_y) / scale
                    dz = abs(foot["z"] - f["ball"]["z"])
                    
                    # Golpe fuerte (sube rápido)
                    hit_strong = is_contact and dx < 35 and dy < 35
                    # Control suave (muy pegada)
                    hit_soft = dx < 20 and dy < 20
                    
                    if (hit_strong or hit_soft) and dz < 70:
                        if (f["idx"] - last_hit_frame_idx) > 8:
                            juggles += 1
                            last_hit_frame_idx = f["idx"]
                            events_log.append({
                                "idx": f["idx"], 
                                "type": f"JUGGLE! ({leg_label})", 
                                "count": juggles,
                                "hit_leg": leg_label
                            })
                            break
            
            # --- DRIBBLE ---
            elif height_cm <= 15:
                d_l = np.sqrt((f["feet"]["L"]["x"]-f["ball"]["x"])**2 + (f["feet"]["L"]["y"]-ball_y)**2) / scale
                d_r = np.sqrt((f["feet"]["R"]["x"]-f["ball"]["x"])**2 + (f["feet"]["R"]["y"]-ball_y)**2) / scale
                
                if min(d_l, d_r) < 70:
                    cx = (f["feet"]["L"]["x"] + f["feet"]["R"]["x"]) / 2
                    if f["ball"]["x"] > cx + 15: dribble_state = "Derecha >>"
                    elif f["ball"]["x"] < cx - 15: dribble_state = "<< Izquierda"
                    else: dribble_state = "Control"
                    
                    if i % 15 == 0:
                        events_log.append({"idx": f["idx"], "type": dribble_state, "count": juggles})

        return events_log, juggles, dribble_state

    # ---------------------------------------------------------
    # FASE 3: GENERACIÓN VISUAL
    # ---------------------------------------------------------
    def generate_visuals(self, video_path, events_log, frames_meta):
        event_map = {e["idx"]: e for e in events_log}
        
        target_indices = set(e["idx"] for e in events_log)
        # Muestreo regular cada 30 frames para contexto
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
                    
                    vis = self._draw_panel(frame, meta, txt, cnt, is_hit, hit_leg)
                    
                    _, b = cv2.imencode('.jpg', vis)
                    b64 = base64.b64encode(b).decode('utf-8')
                    images_out.append({"image_id": str(curr_frame), "image_base64": f"data:image/jpeg;base64,{b64}"})
                    
                    if len(images_out) >= 60: break
            
            curr_frame += 1
        
        cap.release()
        return images_out

    def _draw_panel(self, frame, meta, event_txt, count, is_hit, hit_leg):
        h, w = frame.shape[:2]
        panel = np.zeros((h, 320, 3), dtype=np.uint8); panel[:] = (30,30,30)
        
        ball = meta["ball"]
        kpts = meta["kpts"]
        
        # Mapeo
        def to_p(x, y): return (20 + int(x/w*280), 20 + int(y/h*(h-40)))
        
        c_bone = (100,100,100)
        c_hit = (255,255,0)
        
        # Stickman
        for a, b in self.skeleton_links:
            ka, kb = kpts[a], kpts[b]
            if ka['conf']>0.4 and kb['conf']>0.4:
                # Color hit leg
                col = c_bone
                if is_hit:
                    if hit_leg=="Izq" and (a in [13,15] or b in [13,15]): col = c_hit
                    if hit_leg=="Der" and (a in [14,16] or b in [14,16]): col = c_hit
                cv2.line(panel, to_p(ka['x'],ka['y']), to_p(kb['x'],kb['y']), col, 2)
        
        # Bola
        bc = to_p(ball["x"], ball["y"] - ball["w"]//2) # centro
        cv2.circle(panel, bc, 6, c_hit if is_hit else (0,140,255), -1)
        
        # Textos
        cv2.putText(panel, f"Juggl: {count}", (10, 450), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2)
        if event_txt:
            cv2.putText(panel, event_txt, (10, 490), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)
        
        ball_info = f"N {self.calibrator.selected_size_id} ({self.calibrator.real_diameter_cm}cm)"
        cv2.putText(panel, f"Ball: {ball_info}", (10, 520), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150,150,150), 1)
        
        return np.hstack((frame, panel))

    # ---------------------------------------------------------
    # RUN
    # ---------------------------------------------------------
    def run_on_video(self, video_path, frame_stride=3, max_frames=300, hit_threshold=0.4, return_images=True):
        t0 = time.time()
        
        # 1. Extracción
        meta, f_start, f_mid, fps = self.extract_trajectory(video_path, stride=frame_stride, max_frames=max_frames)
        
        # 2. Análisis
        logs, juggles, end_state = self.analyze_trajectory(meta)
        
        # 3. Visuals
        hit_imgs = []
        if return_images:
            hit_imgs = self.generate_visuals(video_path, logs, meta)
            
        # 4. Face Compare
        face_res = "N/A"
        if self.face_compare_fn and f_start and f_mid:
            try: face_res = self.face_compare_fn(f_start[0], f_mid[0])
            except: pass

        total_t = time.time() - t0
        
        # Info última pierna
        last_leg = "N/A"
        for e in reversed(logs):
            if "JUGGLE" in e["type"]:
                last_leg = e.get("hit_leg", "N/A")
                break

        return {
            "id": int(time.time()),
            "hit_images": hit_imgs,
            "meta": {
                "performance": {
                    "total_time_s": round(total_t, 2),
                    "frames_analyzed": len(meta)
                },
                "stats": {
                    "total_juggles": juggles,
                    "last_hit_leg": last_leg,
                    "final_state": end_state,
                    "ball_size": f"N {self.calibrator.selected_size_id}"
                },
                "face_verification": face_res
            }
        }