import cv2
import numpy as np
import os
import urllib.request
import time
import base64
from typing import Any, Callable, Dict, List, Optional, Tuple

def smooth_signal(data_list, window_size=5):
    if len(data_list) < window_size: return data_list
    return np.convolve(data_list, np.ones(window_size)/window_size, mode='same').tolist()

# ==========================================
# 1. UTILIDADES Y CALIBRACIÓN
# ==========================================
class BallCalibrator:
    def __init__(self):
        self.samples = []
        self.is_calibrated = False
        self.px_per_cm = 2.0
        self.ball_size_cm = 22.0

    def add_sample(self, width_px):
        if 10 < width_px < 200: self.samples.append(width_px)

    def finalize(self, player_h_px):
        if not self.samples: return
        median_px = np.median(self.samples)
        if median_px == 0: return
        
        # Inferencia Talla
        scale_t5 = median_px / 22.0
        h_est = player_h_px / scale_t5
        
        if h_est > 155: self.ball_size_cm = 22.0 # N5
        elif 135 < h_est <= 155: self.ball_size_cm = 20.0 # N4
        else: self.ball_size_cm = 18.0 # N3
            
        self.px_per_cm = max(0.5, min(median_px / self.ball_size_cm, 10.0))
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
        boxes[:, 0] -= boxes[:, 2]/2; boxes[:, 1] -= boxes[:, 3]/2
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
            res.append({"kpts": kpts, "box": bbox, "area": bbox[2]*bbox[3]})
        # Ordenar por área descendente (Persona más grande primero)
        return sorted(res, key=lambda x: x["area"], reverse=True)

# ==========================================
# 3. SERVICIO GENERAL (ANALIZADOR DE RETOS)
# ==========================================
class GeneralActionService:
    def __init__(
        self,
        default_model_dirs: List[str] = None,
        segment_floor_fn: Optional[Callable] = None,
        face_compare_fn: Optional[Callable] = None
    ):
        self.models_dir = "/app/ai_engine/models"
        self.paths = {
            "det": os.path.join(self.models_dir, "yolov8n.onnx"),
            "pose": os.path.join(self.models_dir, "yolov8n-pose.onnx"),
            "midas": os.path.join(self.models_dir, "midas_v21_small.onnx")
        }
        self.urls = {
            "det": "https://github.com/pellit/video-analytics-saas/raw/796d243e692b5b18f0344b033a152dcdd6326f36/ai_engine/yolov8n.onnx",
            "pose": "https://huggingface.co/Xenova/yolov8-pose-onnx/resolve/main/yolov8n-pose.onnx?download=true",
            "midas": "https://github.com/isl-org/MiDaS/releases/download/v2_1/model-small.onnx"
        }
        
        self.segment_floor_fn = segment_floor_fn
        self.face_compare_fn = face_compare_fn
        self._setup_models()
        self.calibrator = BallCalibrator()
        
        # Links Esqueleto
        self.skeleton = [
            (0,5),(0,6),(5,7),(7,9),(6,8),(8,10),(5,11),(6,12),(11,12),(5,6),(11,13),(13,15),(12,14),(14,16)
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
        return cv2.normalize(cv2.resize(self.midas.forward()[0,0], (w, h)), None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)

    def _infer_floor_y(self, frame):
        if self.segment_floor_fn:
            try:
                res = self.segment_floor_fn(frame)
                return int(res.get("floor_y", 0)) if isinstance(res, dict) else int(res)
            except: pass
        return int(frame.shape[0] * 0.9)

    # ---------------------------------------------------------
    # FASE 1: EXTRACCIÓN (Detectar todo)
    # ---------------------------------------------------------
    def extract_metadata(self, video_path, stride=3, max_frames=300):
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        frames_meta = [] 
        processed = 0
        idx = 0
        floor_y = None
        
        while processed < max_frames:
            ret, frame = cap.read()
            if not ret: break
            if idx % stride != 0: idx += 1; continue
            
            if processed == 10: floor_y = self._infer_floor_y(frame)

            ball = self.det.detect(frame)
            people = self.pose.detect(frame) # Devuelve lista ordenada por tamaño
            
            # Verificación Persona Única
            is_single_person = True
            main_person = None
            if len(people) > 0:
                main_person = people[0]
                if len(people) > 1:
                    # Si la segunda persona es > 60% del tamaño de la primera, alerta
                    if people[1]["area"] > (main_person["area"] * 0.6):
                        is_single_person = False

            frame_data = {
                "idx": idx, "time": idx/fps if fps else 0,
                "ball": None, "person": None, "floor_y": floor_y,
                "is_single_person": is_single_person
            }

            if ball and main_person:
                b = ball[0]; p = main_person
                depth = self.get_depth(frame)
                
                # Datos Pelota
                bx, by, bw, bh = b[:4]
                bz = depth[by+bh//2, bx+bw//2] if depth is not None else 128
                frame_data["ball"] = {"x": bx+bw//2, "y": by+bh, "z": int(bz), "w": bw, "box": b}
                
                # Datos Persona Completa (Keypoints)
                # 0:Nariz, 5,6:Hombros, 11,12:Caderas, 13,14:Rodillas, 15,16:Tobillos
                kpts_dict = {}
                for i, kp in enumerate(p["kpts"]):
                    kz = depth[kp['y'], kp['x']] if depth is not None else 128
                    kpts_dict[i] = {"x": kp['x'], "y": kp['y'], "z": int(kz), "conf": kp['conf']}
                
                frame_data["person"] = {
                    "kpts": kpts_dict, 
                    "h_px": p["box"][3],
                    "box": p["box"]
                }

            frames_meta.append(frame_data)
            processed += 1
            idx += 1
            
        cap.release()
        return frames_meta

    # ---------------------------------------------------------
    # FASE 2: CEREBRO ANALÍTICO (El gran integrador)
    # ---------------------------------------------------------
    def analyze_actions(self, frames_meta):
        # 1. Calibración
        widths, heights = [], []
        for f in frames_meta:
            if f["ball"] and f["person"]:
                feet_y = (f["person"]["kpts"][15]["y"] + f["person"]["kpts"][16]["y"]) / 2
                if abs(f["ball"]["y"] - feet_y) < 150:
                    widths.append(f["ball"]["w"])
                    heights.append(f["person"]["h_px"])
        
        for w in widths: self.calibrator.add_sample(w)
        if heights: self.calibrator.finalize(np.median(heights))
        scale = self.calibrator.px_per_cm

        # 2. Suavizado
        raw_y = [(f["ball"]["y"] if f["ball"] else 0) for f in frames_meta]
        smooth_y = smooth_signal(raw_y, 5)

        # 3. Variables de Seguimiento
        events_log = []
        trajectory_3d = []
        
        # Estados
        orientation_history = []
        turn_count = 0
        juggles = 0
        is_dribbling = False
        last_hit_time = -100
        
        # Contadores detallados
        stats = {
            "juggles": {"Head": 0, "Chest": 0, "Knee": 0, "Foot_L": 0, "Foot_R": 0},
            "jumps": 0,
            "turns": 0,
            "multiple_people_warning": False
        }

        for i, f in enumerate(frames_meta):
            if not f["is_single_person"]: stats["multiple_people_warning"] = True
            if not f["ball"] or not f["person"]: continue
            
            # --- A. ANÁLISIS POSTURA ---
            # Nariz(0), Orejas(3,4)
            nose = f["person"]["kpts"][0]
            ear_l, ear_r = f["person"]["kpts"][3], f["person"]["kpts"][4]
            
            current_orient = "Indefinido"
            if nose["conf"] > 0.6: current_orient = "Frente"
            elif ear_l["conf"] > 0.5 and ear_r["conf"] > 0.5 and nose["conf"] < 0.4: current_orient = "Espalda"
            else: current_orient = "Perfil"
            
            # Detección de GIRO (Secuencia Frente -> Perfil -> Espalda)
            if len(orientation_history) > 5:
                if orientation_history[-1] != current_orient:
                    # Lógica simple de cambio de estado
                    # (En prod se usa máquina de estados más compleja)
                    if current_orient == "Espalda" and "Frente" in orientation_history[-10:]:
                        pass # Medio giro
            orientation_history.append(current_orient)

            # --- B. ANÁLISIS DE SALTO ---
            # Si ambos tobillos suben > 20cm del suelo detectado
            floor = f["floor_y"]
            ankles_y = (f["person"]["kpts"][15]["y"] + f["person"]["kpts"][16]["y"]) / 2
            jump_height = (floor - ankles_y) / scale
            is_jumping = jump_height > 20
            # (Contar flancos de subida para no sumar cada frame)
            
            # --- C. ANÁLISIS DE PELOTA (Juggling vs Dribbling) ---
            ball_y = smooth_y[i]
            vel_y = ball_y - (smooth_y[i-1] if i>0 else ball_y)
            height_cm = (floor - ball_y) / scale
            
            ball_x = f["ball"]["x"]
            ball_z = f["ball"]["z"]
            
            trajectory_3d.append({"f": f["idx"], "x": int(ball_x), "y": int(ball_y), "z": int(ball_z)})

            if height_cm <= 15:
                # *** SUELO (DRIBBLING) ***
                is_dribbling = True
                # Lógica de conducción (similar a move_service)
                # Aquí podríamos detectar "Pisada", "Cambio de pie", etc.
                
            else:
                # *** AIRE (JUGGLING / CONTROL) ***
                is_dribbling = False
                
                # DETECCIÓN DE GOLPE (Cualquier parte del cuerpo)
                # Solo si la pelota sube o está controlada
                if vel_y < -1.5 or (vel_y < 0.5 and vel_y > -0.5):
                    
                    hit_part = None
                    
                    # 1. CABEZA
                    head_y = f["person"]["kpts"][0]["y"]
                    if abs(ball_y - head_y)/scale < 25 and abs(ball_x - f["person"]["kpts"][0]["x"])/scale < 20:
                        hit_part = "Head"

                    # 2. PECHO (Punto medio hombros)
                    chest_y = (f["person"]["kpts"][5]["y"] + f["person"]["kpts"][6]["y"]) / 2
                    if not hit_part and abs(ball_y - chest_y)/scale < 25 and abs(ball_x - f["person"]["kpts"][5]["x"])/scale < 25:
                        hit_part = "Chest"

                    # 3. RODILLAS (Muslo)
                    if not hit_part:
                        for side, idx in [("L", 13), ("R", 14)]:
                            kn = f["person"]["kpts"][idx]
                            if abs(ball_y - kn["y"])/scale < 20 and abs(ball_x - kn["x"])/scale < 20:
                                hit_part = "Knee" # Simplificamos lado

                    # 4. PIES
                    if not hit_part:
                        for side, idx in [("Foot_L", 15), ("Foot_R", 16)]:
                            ft = f["person"]["kpts"][idx]
                            if abs(ball_y - ft["y"])/scale < 30 and abs(ball_x - ft["x"])/scale < 25:
                                hit_part = side

                    # REGISTRAR EVENTO
                    if hit_part and (f["idx"] - last_hit_time) > 10:
                        juggles += 1
                        stats["juggles"][hit_part] += 1
                        last_hit_time = f["idx"]
                        events_log.append({
                            "idx": f["idx"],
                            "type": f"HIT: {hit_part}",
                            "part": hit_part,
                            "pose": current_orient
                        })

        return events_log, stats, trajectory_3d

    # ---------------------------------------------------------
    # FASE 3: DASHBOARD VISUAL (Stickman + Map + Stats)
    # ---------------------------------------------------------
    def generate_dashboard(self, video_path, logs, frames_meta, stats):
        event_map = {e["idx"]: e for e in logs}
        target_indices = set(e["idx"] for e in logs)
        for f in frames_meta:
            if f["idx"] % 30 == 0: target_indices.add(f["idx"]) # Sampleo
            
        cap = cv2.VideoCapture(video_path)
        images_out = []
        curr = 0
        
        while True:
            ret, frame = cap.read()
            if not ret: break
            
            if curr in target_indices:
                meta = next((m for m in frames_meta if m["idx"] == curr), None)
                if meta and meta["ball"] and meta["person"]:
                    
                    evt = event_map.get(curr, {})
                    txt = evt.get("type", "")
                    
                    # Panel compuesto
                    vis = self._draw_complex_panel(frame, meta, txt, stats)
                    
                    _, b = cv2.imencode('.jpg', vis)
                    b64 = base64.b64encode(b).decode('utf-8')
                    images_out.append({"image_id": str(curr), "image_base64": f"data:image/jpeg;base64,{b64}"})
                    if len(images_out) >= 60: break
            curr += 1
        cap.release()
        return images_out

    def _draw_complex_panel(self, frame, meta, event_txt, global_stats):
        h, w = frame.shape[:2]
        panel = np.zeros((h, 320, 3), dtype=np.uint8); panel[:] = (20,20,20)
        
        # --- SECCIÓN 1: STICKMAN (Arriba) ---
        # Reutilizamos lógica de dibujo pero más pequeño
        stick_h = int(h * 0.6)
        
        # Mapeo Stickman
        def to_s(x, y): 
            return (20 + int(x/w*280), 20 + int(y/h*(stick_h-40)))
        
        kpts = meta["person"]["kpts"]
        ball = meta["ball"]
        
        # Dibujar Esqueleto
        for a, b in self.skeleton:
            if kpts[a]['conf']>0.4 and kpts[b]['conf']>0.4:
                cv2.line(panel, to_s(kpts[a]['x'], kpts[a]['y']), to_s(kpts[b]['x'], kpts[b]['y']), (100,100,100), 2)
        
        # Pelota
        bc = to_s(ball["x"], ball["y"] - ball["w"]//2)
        cv2.circle(panel, bc, 6, (0,255,255) if event_txt else (0,140,255), -1)

        # --- SECCIÓN 2: PLANTA (Medio) ---
        map_y = stick_h + 10
        map_h = int(h * 0.25)
        cv2.rectangle(panel, (20, map_y), (300, map_y+map_h), (34,139,34), -1) # Cancha verde
        
        # Punto Pelota en Mapa
        mx = 20 + int(ball["x"]/w * 280)
        mz = map_y + int(ball["z"]/255.0 * map_h)
        cv2.circle(panel, (mx, mz), 5, (255,255,255), -1)

        # --- SECCIÓN 3: ESTADÍSTICAS (Abajo) ---
        stats_y = map_y + map_h + 20
        font = cv2.FONT_HERSHEY_SIMPLEX
        
        cv2.putText(panel, f"TOTAL HITS: {sum(global_stats['juggles'].values())}", (10, stats_y), font, 0.7, (0,255,255), 2)
        
        # Barras de progreso por parte del cuerpo
        parts = ["Foot_L", "Foot_R", "Head", "Knee", "Chest"]
        for i, part in enumerate(parts):
            count = global_stats['juggles'][part]
            txt = f"{part}: {count}"
            y_pos = stats_y + 25 + (i*20)
            if y_pos < h:
                cv2.putText(panel, txt, (10, y_pos), font, 0.5, (200,200,200), 1)

        if event_txt:
            cv2.putText(panel, event_txt, (10, 30), font, 0.8, (0,0,255), 2)

        return np.hstack((frame, panel))

    # ---------------------------------------------------------
    # MAIN
    # ---------------------------------------------------------
    def run_on_video(self, video_path, frame_stride=3, max_frames=300, return_images=True):
        t0 = time.time()
        # 1. Extracción
        meta = self.extract_metadata(video_path, stride=frame_stride, max_frames=max_frames)
        # 2. Análisis
        logs, stats, traj = self.analyze_actions(meta)
        # 3. Visual
        imgs = []
        if return_images: imgs = self.generate_dashboard(video_path, logs, meta, stats)
        
        return {
            "id": int(time.time()),
            "hit_images": imgs,
            "trajectory": traj,
            "meta": {
                "performance": {"total_time": round(time.time()-t0, 2)},
                "stats": stats,
                "ball_calib": f"Size {self.calibrator.ball_size_cm}cm"
            }
        }