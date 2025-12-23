import cv2
import numpy as np
import os
import urllib.request
import time
import base64
from typing import Any, Callable, Dict, List, Optional, Tuple

def smooth_signal(data_list, window_size=5):
    """Suaviza una lista de números usando media móvil"""
    if len(data_list) < window_size: return data_list
    return np.convolve(data_list, np.ones(window_size)/window_size, mode='same').tolist()

# ==========================================
# 1. CALIBRADOR (Reutilizado)
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
        if 10 < width_px < 200: self.samples.append(width_px)

    def finalize(self, player_h_px):
        if not self.samples: return
        median_px = np.median(self.samples)
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
# 2. WRAPPERS IA (YOLO + Pose + MiDaS)
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
    def detect(self, img, conf=0.15):
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
            res.append({"kpts": kpts, "box": bbox})
        return sorted(res, key=lambda x: (x["box"][2]*x["box"][3]))[-1:] 

# ==========================================
# 3. SERVICIO DE MOVIMIENTO (OPTIMIZADO)
# ==========================================
class MoveDetectionServiceOptimized:
    def __init__(
        self,
        default_model_dirs: List[str] = None,
        segment_floor_fn: Optional[Callable[[np.ndarray], Optional[int]]] = None,
        face_compare_fn: Optional[Callable[[str, str], Any]] = None
    ):
        self.models_dir = "/app/ai_engine/models"
        self.paths = {
            "det": os.path.join(self.models_dir, "yolov8n.onnx"),
            "pose": os.path.join(self.models_dir, "yolov8n-pose.onnx"),
            "midas": os.path.join(self.models_dir, "midas_v21_small.onnx")
        }
        self.urls = {
            "det": "https://huggingface.co/Bingsu/yolov8n_onnx/resolve/main/yolov8n.onnx",
            "pose": "https://huggingface.co/Xenova/yolov8-pose-onnx/resolve/main/yolov8n-pose.onnx?download=true",
            "midas": "https://github.com/isl-org/MiDaS/releases/download/v2_1/model-small.onnx"
        }
        
        self.segment_floor_fn = segment_floor_fn
        self.face_compare_fn = face_compare_fn
        
        self._setup_models()
        self.calibrator = BallCalibrator()

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

    def _infer_floor_y(self, frame: np.ndarray) -> Optional[int]:
        if self.segment_floor_fn:
            try:
                res = self.segment_floor_fn(frame)
                return int(res.get("floor_y", 0)) if isinstance(res, dict) else int(res)
            except: pass
        h = frame.shape[0]
        return int(h * 0.9) # Fallback

    # ---------------------------------------------------------
    # FASE 1: EXTRACCIÓN (Batch)
    # ---------------------------------------------------------
    def extract_trajectory(self, video_path, stride=3, max_frames=300):
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        frames_meta = [] 
        processed = 0
        idx = 0
        floor_y = None
        
        while processed < max_frames:
            ret, frame = cap.read()
            if not ret: break
            if idx % stride != 0: 
                idx += 1; continue
            
            if processed == 10: floor_y = self._infer_floor_y(frame)

            ball = self.det.detect(frame)
            person = self.pose.detect(frame)
            
            # Solo guardamos lo necesario para reconstrucción
            frame_data = {
                "idx": idx, 
                "ball": None, 
                "feet": None,
                "floor_y": floor_y
            }

            if ball and person:
                b = ball[0]; p = person[0]
                depth = self.get_depth(frame)
                
                # Pelota: X, Y (Bottom), Z, Ancho
                bx, by, bw, bh = b[:4]
                bz = depth[by+bh//2, bx+bw//2] if depth is not None else 128
                frame_data["ball"] = {"x": bx+bw//2, "y": by+bh, "z": int(bz), "w": bw}
                
                # Pies: X, Y, Z
                f_l, f_r = p["kpts"][15], p["kpts"][16]
                fz_l = depth[f_l['y'], f_l['x']] if depth is not None else 128
                fz_r = depth[f_r['y'], f_r['x']] if depth is not None else 128
                
                frame_data["feet"] = {
                    "L": {"x": f_l['x'], "y": f_l['y'], "z": int(fz_l), "conf": f_l['conf']},
                    "R": {"x": f_r['x'], "y": f_r['y'], "z": int(fz_r), "conf": f_r['conf']}
                }
                frame_data["person_h"] = p["box"][3]
                frame_data["ball_box"] = b # Para visualizacion

            frames_meta.append(frame_data)
            processed += 1
            idx += 1
            
        cap.release()
        return frames_meta

    # ---------------------------------------------------------
    # FASE 2: ANÁLISIS DE CONDUCCIÓN (Top-Down Logic)
    # ---------------------------------------------------------
    def analyze_dribbling(self, frames_meta):
        # 1. Calibración
        widths, heights = [], []
        for f in frames_meta:
            if f["ball"] and f["feet"]:
                # Tomar muestras solo si está cerca del piso
                if abs(f["ball"]["y"] - (f["feet"]["L"]["y"]+f["feet"]["R"]["y"])/2) < 100:
                    widths.append(f["ball"]["w"])
                    heights.append(f["person_h"])
        
        for w in widths: self.calibrator.add_sample(w)
        if heights: self.calibrator.finalize(np.median(heights))
        scale = self.calibrator.px_per_cm if self.calibrator.is_calibrated else 2.0

        # 2. Suavizado de Trayectorias para Vista de Planta (XZ)
        raw_x = []; raw_z = []
        for f in frames_meta:
            if f["ball"]:
                raw_x.append(f["ball"]["x"])
                raw_z.append(f["ball"]["z"])
            else:
                # Mantener valor anterior si se pierde (simple fill)
                raw_x.append(raw_x[-1] if raw_x else 0)
                raw_z.append(raw_z[-1] if raw_z else 0)
        
        smooth_x = smooth_signal(raw_x, 5)
        smooth_z = smooth_signal(raw_z, 5)

        # 3. Detección de Eventos (Toques en el suelo)
        events_log = []
        plant_trajectory = [] # Lista de puntos para el mapa
        
        touches_L, touches_R = 0, 0
        last_touch_frame = -20
        last_touch_leg = ""

        for i, f in enumerate(frames_meta):
            if not f["ball"] or not f["feet"]: continue
            
            # Coordenadas suavizadas
            bx, bz = smooth_x[i], smooth_z[i]
            by = f["ball"]["y"] # Y vertical no se suaviza tanto para detectar piso
            
            # Guardar punto para mapa (Normalizado 0-100 para frontend)
            # Nota: Esto es relativo al frame, no coordenadas de cancha real
            plant_trajectory.append({
                "frame": f["idx"],
                "x": int(bx),
                "z": int(bz), # Profundidad (0-255)
                "is_touch": False
            })

            # Check Altura: ¿Está en el suelo?
            floor = f["floor_y"] if f["floor_y"] else max(f["feet"]["L"]["y"], f["feet"]["R"]["y"])
            height_cm = (floor - by) / scale
            
            if height_cm <= 15: # Solo analizamos si está en el suelo
                
                # Check Velocidad en plano XZ (Aceleración = Toque)
                if i > 0:
                    prev_x, prev_z = smooth_x[i-1], smooth_z[i-1]
                    speed_sq = (bx - prev_x)**2 + (bz - prev_z)**2 # Velocidad cuadrada
                else: speed_sq = 0
                
                is_moving = speed_sq > 5.0 # Se mueve algo
                
                for leg, foot in [("Izq", f["feet"]["L"]), ("Der", f["feet"]["R"])]:
                    if foot["conf"] < 0.5: continue
                    
                    # Distancia 3D (X, Z) ignorando Y (porque ya validamos suelo)
                    dx = abs(foot["x"] - bx) / scale
                    dz = abs(foot["z"] - bz) # Z raw units
                    
                    # Distancia euclídea en plano XZ (aprox)
                    dist_ground = np.sqrt(dx**2 + (dz/5.0)**2) # dz se escala heurísticamente
                    
                    # DETECCIÓN DE TOQUE:
                    # 1. Distancia muy corta (< 15cm)
                    # 2. Debounce temporal
                    if dist_ground < 15:
                        if (f["idx"] - last_touch_frame) > 10:
                            if leg == "Izq": touches_L += 1
                            else: touches_R += 1
                            
                            last_touch_frame = f["idx"]
                            last_touch_leg = leg
                            
                            events_log.append({
                                "idx": f["idx"],
                                "type": f"Toque ({leg})",
                                "leg": leg,
                                "x_map": int(bx),
                                "z_map": int(bz)
                            })
                            # Marcar punto en trayectoria
                            plant_trajectory[-1]["is_touch"] = True
                            plant_trajectory[-1]["touch_leg"] = leg

        stats = {
            "total_touches": touches_L + touches_R,
            "touches_left": touches_L,
            "touches_right": touches_R
        }
        return events_log, stats, plant_trajectory

    # ---------------------------------------------------------
    # FASE 3: VISUALIZACIÓN (Ojo de Pájaro)
    # ---------------------------------------------------------
    def generate_visuals(self, video_path, events_log, frames_meta, trajectory):
        event_map = {e["idx"]: e for e in events_log}
        
        # Puntos clave para renderizar (cada 5 frames + eventos)
        target_indices = set(e["idx"] for e in events_log)
        for f in frames_meta:
            if f["idx"] % 5 == 0: target_indices.add(f["idx"])
            
        cap = cv2.VideoCapture(video_path)
        images_out = []
        curr_frame = 0
        
        # Mapa estático de trayectoria acumulada
        path_history = []
        
        while True:
            ret, frame = cap.read()
            if not ret: break
            
            # Buscar datos de trayectoria para este frame
            curr_point = next((p for p in trajectory if p["frame"] == curr_frame), None)
            if curr_point:
                path_history.append(curr_point)

            if curr_frame in target_indices:
                meta = next((m for m in frames_meta if m["idx"] == curr_frame), None)
                if meta:
                    evt = event_map.get(curr_frame, {})
                    txt = evt.get("type", "")
                    
                    vis = self._draw_birds_eye_panel(frame, path_history, meta, txt)
                    
                    _, b = cv2.imencode('.jpg', vis)
                    b64 = base64.b64encode(b).decode('utf-8')
                    images_out.append({"image_id": str(curr_frame), "image_base64": f"data:image/jpeg;base64,{b64}"})
                    
                    if len(images_out) >= 60: break # Limite
            
            curr_frame += 1
        cap.release()
        return images_out

    def _draw_birds_eye_panel(self, frame, path_history, meta, event_txt):
        h, w = frame.shape[:2]
        panel_w = 320
        panel = np.zeros((h, panel_w, 3), dtype=np.uint8)
        
        # Fondo Verde (Cancha)
        panel[:] = (34, 139, 34) 
        # Líneas de campo
        cv2.rectangle(panel, (10, 10), (panel_w-10, h-10), (200, 200, 200), 2)
        cv2.line(panel, (panel_w//2, 10), (panel_w//2, h-10), (200, 200, 200), 1)
        cv2.circle(panel, (panel_w//2, h//2), 30, (200, 200, 200), 1)

        # Función de Mapeo: 
        # X imagen -> X panel (invertido si cámara espejo)
        # Z profundidad (0=lejos, 255=cerca) -> Y panel (arriba=lejos, abajo=cerca)
        def map_xz(x_img, z_depth):
            px = 20 + int(x_img / w * (panel_w - 40))
            # Z: 0(lejos) -> 0(top panel). 255(cerca) -> h(bottom panel)
            py = 20 + int(z_depth / 255.0 * (h - 40))
            return (px, py)

        # 1. Dibujar Trayectoria (Línea Amarilla)
        if len(path_history) > 1:
            pts = []
            for p in path_history:
                pts.append(map_xz(p["x"], p["z"]))
            cv2.polylines(panel, [np.array(pts)], False, (0, 255, 255), 2)

        # 2. Dibujar Puntos de Contacto (Histórico)
        for p in path_history:
            if p.get("is_touch"):
                pt = map_xz(p["x"], p["z"])
                color = (0, 0, 255) if p.get("touch_leg") == "Der" else (255, 0, 0) # Rojo Der, Azul Izq
                cv2.circle(panel, pt, 4, color, -1)

        # 3. Posición Actual (Pelota grande)
        if path_history:
            last = path_history[-1]
            cur_pt = map_xz(last["x"], last["z"])
            cv2.circle(panel, cur_pt, 8, (255, 255, 255), -1)
            cv2.circle(panel, cur_pt, 8, (0,0,0), 1)

        # 4. Texto Evento
        if event_txt:
            cv2.rectangle(panel, (0, h-60), (panel_w, h), (0,0,0), -1)
            cv2.putText(panel, event_txt, (10, h-20), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        # Título
        cv2.putText(panel, "VISTA PLANTA (XZ)", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)
        
        # Dibujar bbox en frame original
        if meta and meta["ball_box"] is not None:
            bx, by, bw, bh = meta["ball_box"][:4]
            cv2.rectangle(frame, (bx, by), (bx+bw, by+bh), (0, 255, 0), 2)

        return np.hstack((frame, panel))

    # ---------------------------------------------------------
    # MAIN EXECUTION
    # ---------------------------------------------------------
    def run_on_video(self, video_path, frame_stride=3, max_frames=300, hit_threshold=0.4, return_images=True):
        t0 = time.time()
        
        # 1. Extracción
        meta = self.extract_trajectory(video_path, stride=frame_stride, max_frames=max_frames)
        
        # 2. Análisis
        logs, stats, trajectory = self.analyze_dribbling(meta)
        
        # 3. Visualización
        hit_imgs = []
        if return_images:
            hit_imgs = self.generate_visuals(video_path, logs, meta, trajectory)

        total_t = time.time() - t0
        
        # Preparar trayectoria para JSON (solo campos necesarios)
        clean_traj = [{"f": t["frame"], "x": t["x"], "z": t["z"], "touch": t["is_touch"]} for t in trajectory]

        return {
            "id": int(time.time()),
            "hit_images": hit_imgs,
            "trajectory_plant": clean_traj, # Datos para frontend
            "meta": {
                "performance": {
                    "total_time_s": round(total_t, 2),
                    "frames_analyzed": len(meta)
                },
                "stats": {
                    "total_touches": stats["total_touches"],
                    "touches_left": stats["touches_left"],
                    "touches_right": stats["touches_right"],
                    "ball_size_inferred": f"N {self.calibrator.selected_size_id}"
                }
            }
        }