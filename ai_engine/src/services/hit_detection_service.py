import cv2
import numpy as np
import os
import urllib.request
import time
import base64
from typing import Any, Callable, Dict, List, Optional

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
        self.px_per_cm = 1.0

    def add_sample(self, ball_width_px, is_near_feet):
        if is_near_feet and ball_width_px > 8:
            self.samples.append(ball_width_px)

    def finalize_calibration(self, player_height_px):
        if not self.samples: return False
        median_ball_px = np.median(self.samples)
        scale_if_size_5 = median_ball_px / 22.0
        height_if_size_5 = player_height_px / scale_if_size_5
        
        if height_if_size_5 > 155: self.selected_size_id = 5
        elif 135 < height_if_size_5 <= 155: self.selected_size_id = 4
        else: self.selected_size_id = 3
            
        self.real_diameter_cm = self.SIZES[self.selected_size_id]
        self.px_per_cm = median_ball_px / self.real_diameter_cm
        self.is_calibrated = True
        return True

# ==========================================
# 2. CLASES IA (YOLO)
# ==========================================
class YoloBaseWrapper:
    def __init__(self, model_path, conf_thres=0.4, iou_thres=0.5):
        self.model_path = model_path
        self.conf_thres = conf_thres
        self.iou_thres = iou_thres
        self.net = None
        self.input_size = (640, 640)

    def load_model(self, name="YOLO"):
        if not os.path.exists(self.model_path) or os.path.getsize(self.model_path) < 1000: return False
        try:
            self.net = cv2.dnn.readNet(self.model_path)
            self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
            self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
            self.net.setInput(np.zeros((1, 3, 640, 640), dtype=np.float32))
            self.net.forward()
            print(f"[{name}] ✅ GPU Ready.")
            return True
        except: return False

    def preprocess(self, img):
        return cv2.dnn.blobFromImage(img, 1/255.0, self.input_size, swapRB=True, crop=False)

class YoloDetWrapper(YoloBaseWrapper):
    def detect_ball(self, blob, img_w, img_h):
        if self.net is None: return []
        self.net.setInput(blob)
        outputs = self.net.forward()
        preds = np.squeeze(outputs[0]).T
        if preds.shape[1] > 36:
            scores = preds[:, 32+4] 
            keep = scores > self.conf_thres
            preds = preds[keep]
            scores = scores[keep]
        else: return []
        if len(scores) == 0: return []
        boxes = preds[:, :4]
        boxes[:, 0] -= boxes[:, 2] / 2
        boxes[:, 1] -= boxes[:, 3] / 2
        indices = cv2.dnn.NMSBoxes(boxes.tolist(), scores.tolist(), self.conf_thres, self.iou_thres)
        balls = []
        sx, sy = img_w / self.input_size[0], img_h / self.input_size[1]
        for i in indices.flatten():
            b = boxes[i]
            balls.append([int(b[0]*sx), int(b[1]*sy), int(b[2]*sx), int(b[3]*sy), float(scores[i])])
        return balls

class YoloPoseWrapper(YoloBaseWrapper):
    def detect_pose(self, blob, img_w, img_h):
        if self.net is None: return []
        self.net.setInput(blob)
        outputs = self.net.forward()
        preds = np.squeeze(outputs[0]).T
        scores = preds[:, 4]
        keep = scores > self.conf_thres
        preds = preds[keep]
        scores = scores[keep]
        if len(scores) == 0: return []
        kpts = preds[:, 5:]
        indices = cv2.dnn.NMSBoxes(preds[:, :4].tolist(), scores.tolist(), self.conf_thres, self.iou_thres)
        people = []
        sx, sy = img_w / self.input_size[0], img_h / self.input_size[1]
        for i in indices.flatten():
            pk = kpts[i].reshape(-1, 3)
            scaled = [{"x": int(p[0]*sx), "y": int(p[1]*sy), "conf": float(p[2])} for p in pk]
            box = preds[i, :4]
            box_scaled = [int((box[0]-box[2]/2)*sx), int((box[1]-box[3]/2)*sy), int(box[2]*sx), int(box[3]*sy)]
            people.append({"keypoints": scaled, "box": box_scaled})
        return people

# ==========================================
# 2. SERVICIO INTELIGENTE
# ==========================================
class HitDetectionService:
    def __init__(
        self,
        default_model_dirs: List[str] = None,
        segment_floor_fn: Optional[Callable[[np.ndarray], Optional[int]]] = None,
        face_compare_fn: Optional[Callable[[str, str], Any]] = None,
    ):
        self.models_dir = "/app/ai_engine/models"
        self.det_path = os.path.join(self.models_dir, "yolov8n.onnx")       
        self.pose_path = os.path.join(self.models_dir, "yolov8n-pose.onnx")  
        self.midas_path = os.path.join(self.models_dir, "midas_v21_small.onnx") 

        self.segment_floor_fn = segment_floor_fn
        self.face_compare_fn = face_compare_fn

        self.det_url = "https://github.com/pellit/video-analytics-saas/raw/796d243e692b5b18f0344b033a152dcdd6326f36/ai_engine/yolov8n.onnx"
        self.pose_url = "https://huggingface.co/Xenova/yolov8-pose-onnx/resolve/main/yolov8n-pose.onnx?download=true"
        self.midas_url = "https://github.com/isl-org/MiDaS/releases/download/v2_1/model-small.onnx"

        self._check_and_download_models()
        
        self.det_model = YoloDetWrapper(self.det_path, conf_thres=0.25)
        self.det_model.load_model("BALL")
        self.pose_model = YoloPoseWrapper(self.pose_path, conf_thres=0.5)
        self.pose_model.load_model("POSE")
        
        self.midas_net = None
        if os.path.exists(self.midas_path):
            try:
                self.midas_net = cv2.dnn.readNet(self.midas_path)
                self.midas_net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
                self.midas_net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
            except: pass

        # Estado
        self.juggles_count = 0        
        self.dribble_state = "Calibrando..." 
        self.prev_ball_y = None   
        self.ball_velocity_y = 0  
        self.last_hit_frame = -100 
        self.last_hit_leg = "" # NUEVO: Guarda qué pierna golpeó
        
        self.faces_start, self.faces_middle = [], []
        self.detected_floor_y = None 
        
        self.calibrator = BallCalibrator()
        self.player_height_m = 0.0
        
        # Definición del Esqueleto para dibujo (Pares de Keypoints)
        # 11:CaderaI, 12:CaderaD, 13:RodillaI, 14:RodillaD, 15:TobilloI, 16:TobilloD, 5:HombroI, 6:HombroD
        self.skeleton_links = [
            (5, 11), (6, 12), # Torso
            (11, 13), (13, 15), # Pierna Izq
            (12, 14), (14, 16), # Pierna Der
            (11, 12), (5, 6) # Conexiones horizontales
        ]

    def _check_and_download_models(self):
        os.makedirs(self.models_dir, exist_ok=True)
        downloads = [(self.det_url, self.det_path), (self.pose_url, self.pose_path), (self.midas_url, self.midas_path)]
        for url, path in downloads:
            if not os.path.exists(path) or os.path.getsize(path) < 100000:
                try: urllib.request.urlretrieve(url, path)
                except: pass

    def get_depth_map(self, frame):
        if self.midas_net is None: return None
        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(frame, 1/255.0, (256, 256), (123.675, 116.28, 103.53), True, False)
        self.midas_net.setInput(blob)
        depth = self.midas_net.forward()
        return cv2.normalize(cv2.resize(depth[0,0], (w, h)), None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)

    def extract_face(self, frame, kpts):
        pts = [kpts[i] for i in range(5) if kpts[i]['conf'] > 0.4]
        if len(pts) < 3: return None
        xs, ys = [p['x'] for p in pts], [p['y'] for p in pts]
        pad = 40
        x1, y1 = max(0, min(xs)-pad), max(0, min(ys)-pad*2)
        x2, y2 = min(frame.shape[1], max(xs)+pad), min(frame.shape[0], max(ys)+pad)
        if x2-x1 < 20: return None
        _, buf = cv2.imencode('.jpg', frame[y1:y2, x1:x2])
        return base64.b64encode(buf).decode('utf-8')

    def check_orientation(self, kpts):
        nose = kpts[0]
        eyes = (kpts[1]['conf'] > 0.5 and kpts[2]['conf'] > 0.5)
        ears = (kpts[3]['conf'] > 0.5 and kpts[4]['conf'] > 0.5)
        if nose['conf'] > 0.6 and eyes: return "Frente"
        elif not nose['conf'] > 0.4 and ears: return "Espalda"
        return "Lado"

    def analyze_football(self, ball_box, person_box, person_kpts, depth_map, frame_idx):
        bx, by, bw, bh = ball_box[:4]
        ball_cx = bx + bw//2
        ball_bottom_y = by + bh 
        
        # === CALIBRACIÓN ===
        feet_kpts = [person_kpts[15], person_kpts[16]]
        valid_feet_kpts = [f for f in feet_kpts if f['conf'] > 0.5]
        
        if valid_feet_kpts:
            feet_y_avg = sum([f['y'] for f in valid_feet_kpts]) / len(valid_feet_kpts)
            is_near_feet = abs(ball_bottom_y - feet_y_avg) < 100 
            
            if not self.calibrator.is_calibrated and is_near_feet:
                self.calibrator.add_sample(bw, True)
            if frame_idx == 30 and not self.calibrator.is_calibrated:
                self.calibrator.finalize_calibration(person_box[3]) 

        scale = self.calibrator.px_per_cm if self.calibrator.is_calibrated else 2.0 
        if self.calibrator.is_calibrated:
            self.player_height_m = (person_box[3] / scale) / 100.0

        # === LÓGICA DE JUEGO REFINADA ===
        try: ball_z = depth_map[by+bh//2, bx+bw//2]
        except: return "", "Indefinido"

        orientation = self.check_orientation(person_kpts)
        if not valid_feet_kpts: return "", orientation

        if self.detected_floor_y: ground_y = self.detected_floor_y
        else: ground_y = max([f['y'] for f in valid_feet_kpts])

        curr_vel = 0
        if self.prev_ball_y is not None: curr_vel = ball_bottom_y - self.prev_ball_y
        is_moving_up = (curr_vel < -2)
        self.prev_ball_y = ball_bottom_y
        
        event = ""
        ball_height_cm = (ground_y - ball_bottom_y) / scale

        # --- JUGGLING: Detección de Pierna ---
        if ball_height_cm > 15:
            if is_moving_up:
                # Iteramos sobre pies etiquetados
                feet_data = [
                    {"kpt": person_kpts[15], "label": "Izq"},
                    {"kpt": person_kpts[16], "label": "Der"}
                ]
                
                for foot_obj in feet_data:
                    foot = foot_obj["kpt"]
                    if foot['conf'] <= 0.5: continue

                    dist_x_cm = abs(foot['x'] - ball_cx) / scale
                    dist_y_cm = abs(foot['y'] - ball_bottom_y) / scale
                    try: foot_z = depth_map[foot['y'], foot['x']]
                    except: foot_z = 0
                    dist_z = abs(int(ball_z) - int(foot_z))

                    if dist_x_cm < 30 and dist_y_cm < 30 and dist_z < 60:
                        if (frame_idx - self.last_hit_frame) > 8:
                            self.juggles_count += 1
                            self.last_hit_frame = frame_idx
                            self.last_hit_leg = foot_obj["label"] # Guardamos pierna
                            event = f"JUGGLE! (Pie {self.last_hit_leg})"
                            break # Importante: Salir tras detectar el primer golpe válido

        # --- DRIBBLE ---
        elif ball_height_cm <= 15:
            closest_cm = 999
            for f in valid_feet_kpts:
                d_px = np.sqrt((f['x']-ball_cx)**2 + (f['y']-ball_bottom_y)**2)
                d_cm = d_px / scale
                if d_cm < closest_cm: closest_cm = d_cm
            
            if closest_cm < 60:
                cx = (feet_kpts[0]['x'] + feet_kpts[1]['x']) / 2
                side = ""
                if orientation == "Frente":
                    if ball_cx > cx + 10: side = "Izquierda (M)"
                    elif ball_cx < cx - 10: side = "Derecha (M)"
                else:
                    if ball_cx > cx + 10: side = "Derecha"
                    elif ball_cx < cx - 10: side = "Izquierda"
                self.dribble_state = f"Control {side}"
                event = self.dribble_state

        return event, orientation

    def draw_stickman_panel(self, frame, kpts, ball_box, depth_map, is_hit_frame):
        """
        Dibuja un 'muñequito' wireframe usando Z para simular 3D (tamaño).
        Resalta la pierna de golpe si is_hit_frame es True.
        """
        h_frame, w_frame = frame.shape[:2]
        panel_w, panel_h = 320, h_frame
        panel = np.zeros((panel_h, panel_w, 3), dtype=np.uint8)
        panel[:] = (30, 30, 30)
        
        # Mapeo simple: Frame Coords -> Panel Coords
        def map_to_panel(x, y):
            return (20 + int(x / w_frame * (panel_w - 40)), 
                    20 + int(y / h_frame * (panel_h - 40)))

        # Colores
        c_bone = (100, 100, 100)
        c_joint = (0, 200, 0)
        c_ball = (0, 140, 255)
        c_hit = (255, 255, 0) # Cyan para golpe

        # 1. DIBUJAR ESQUELETO (Wireframe)
        for idx_a, idx_b in self.skeleton_links:
            ka, kb = kpts[idx_a], kpts[idx_b]
            if ka['conf'] > 0.4 and kb['conf'] > 0.4:
                pa = map_to_panel(ka['x'], ka['y'])
                pb = map_to_panel(kb['x'], kb['y'])
                
                # Color especial si es la pierna de golpe
                is_hit_leg = False
                if is_hit_frame and self.last_hit_leg:
                    if self.last_hit_leg == "Izq" and (13 in (idx_a, idx_b) or 15 in (idx_a, idx_b)): is_hit_leg = True
                    if self.last_hit_leg == "Der" and (14 in (idx_a, idx_b) or 16 in (idx_a, idx_b)): is_hit_leg = True
                
                line_color = c_hit if is_hit_leg else c_bone
                thickness = 3 if is_hit_leg else 2
                cv2.line(panel, pa, pb, line_color, thickness)

        # 2. DIBUJAR ARTICULACIONES (Círculos con 'profundidad')
        # Usamos Z para el radio: más cerca (Z mayor) = más grande
        joints_to_draw = [11, 12, 13, 14, 15, 16, 5, 6, 0] # Caderas, Rodillas, Tobillos, Hombros, Nariz
        for idx in joints_to_draw:
            kp = kpts[idx]
            if kp['conf'] > 0.4:
                try: z_val = int(depth_map[kp['y'], kp['x']])
                except: z_val = 128
                radius = max(3, int((z_val / 255.0) * 8)) # Radio entre 3 y 8
                
                joint_color = c_joint
                # Resaltar tobillo de golpe
                if is_hit_frame and ((self.last_hit_leg == "Izq" and idx == 15) or (self.last_hit_leg == "Der" and idx == 16)):
                     joint_color = c_hit
                     radius += 3

                cv2.circle(panel, map_to_panel(kp['x'], kp['y']), radius, joint_color, -1)

        # 3. DIBUJAR PELOTA
        bx, by, bw, bh = ball_box[:4]
        bcx, bcy = bx+bw//2, by+bh//2
        try: bz = int(depth_map[bcy, bcx])
        except: bz = 128
        ball_radius = max(5, int((bz / 255.0) * 12))
        ball_color = c_hit if is_hit_frame else c_ball
        cv2.circle(panel, map_to_panel(bcx, bcy), ball_radius, ball_color, -1)

        # 4. TEXTOS INFO
        cv2.putText(panel, "VISUALIZADOR 3D", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)
        
        color_calib = (0, 255, 0) if self.calibrator.is_calibrated else (0, 0, 255)
        txt_size = f"N {self.calibrator.selected_size_id} ({self.calibrator.real_diameter_cm}cm)"
        cv2.putText(panel, f"Ball: {txt_size}", (10, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color_calib, 1)
        cv2.putText(panel, f"Playr: {self.player_height_m:.2f}m", (10, 480), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200,200,200), 1)
        cv2.putText(panel, f"Juggles: {self.juggles_count}", (10, 520), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0,255,255), 2)

        return np.hstack((frame, panel))


    def _infer_floor_y(self, frame: np.ndarray) -> Optional[int]:
        if self.segment_floor_fn:
            try:
                result = self.segment_floor_fn(frame)
                if isinstance(result, dict):
                    floor_val = result.get("floor_y")
                else:
                    floor_val = result
                if floor_val is not None:
                    return int(floor_val)
            except Exception as exc:
                print(f"[HitDetection] segment_floor_fn failure: {exc}")
        return self._heuristic_floor_estimate(frame)

    @staticmethod
    def _heuristic_floor_estimate(frame: np.ndarray) -> Optional[int]:
        h, w = frame.shape[:2]
        if h == 0 or w == 0:
            return None
        roi_start = int(h * 0.4)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        roi = gray[roi_start:, :]
        if roi.size == 0:
            return None
        blur = cv2.GaussianBlur(roi, (5, 5), 0)
        sobel = cv2.Sobel(blur, cv2.CV_32F, 0, 1, ksize=3)
        row_scores = np.mean(np.abs(sobel), axis=1)
        if row_scores.size == 0:
            return None
        idx = int(np.argmax(row_scores))
        floor_y = min(h - 1, roi_start + idx)
        return floor_y


    def run_on_video(self, video_path, frame_stride=3, max_frames=300, hit_threshold=0.4, return_images=True):
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        dur_s = total_frames / fps if fps > 0 else 0
        
        frame_idx = 0
        processed = 0
        images_output = []
        start_t = time.time()
        self.faces_start, self.faces_middle = [], []
        
        while processed < max_frames:
            ret, frame = cap.read()
            if not ret: break
            if frame_idx % frame_stride != 0:
                frame_idx += 1
                continue
            
            h, w = frame.shape[:2]
            
            if processed == 10:
                floor_guess = self._infer_floor_y(frame)
                if floor_guess is not None:
                    self.detected_floor_y = int(floor_guess)

            det_blob = self.det_model.preprocess(frame)
            pose_blob = self.pose_model.preprocess(frame)
            balls = self.det_model.detect_ball(det_blob, w, h)
            people = self.pose_model.detect_pose(pose_blob, w, h)
            
            event = ""
            vis_frame = frame.copy()
            is_hit_frame = False

            if len(balls) > 0 and len(people) > 0:
                ball = sorted(balls, key=lambda x: x[4])[-1]
                person = sorted(people, key=lambda x: (x['box'][2]*x['box'][3]))[-1]
                depth_map = self.get_depth_map(frame)
                
                if depth_map is not None:
                    event, orientation = self.analyze_football(ball, person['box'], person['keypoints'], depth_map, frame_idx)
                    
                    if "JUGGLE!" in event: is_hit_frame = True

                    if orientation == "Frente":
                        if processed < 50 and len(self.faces_start) < 4:
                            f = self.extract_face(frame, person['keypoints'])
                            if f: self.faces_start.append(f)
                        if processed > (max_frames//2) and len(self.faces_middle) < 4:
                            f = self.extract_face(frame, person['keypoints'])
                            if f: self.faces_middle.append(f)

                    if return_images:
                        # Usamos el nuevo visualizador de stickman
                        vis_frame = self.draw_stickman_panel(vis_frame, person['keypoints'], ball, depth_map, is_hit_frame)
                
                if not return_images:
                    cv2.rectangle(vis_frame, (ball[0], ball[1]), (ball[0]+ball[2], ball[1]+ball[3]), (0,0,255), 2)
            
            is_important = (event != "" and "Control" not in event and event != "Parado")
            is_sample = (processed % 15 == 0)
            
            if return_images:
                if (is_important) or (is_sample and len(images_output) < 30):
                    if not event and not is_important:
                        cv2.putText(vis_frame, f"Count: {self.juggles_count}", (30,50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2)
                    _, buf = cv2.imencode('.jpg', vis_frame)
                    b64 = base64.b64encode(buf).decode('utf-8')
                    images_output.append({"image_id": str(frame_idx), "image_base64": f"data:image/jpeg;base64,{b64}"})

            processed += 1
            frame_idx += 1

        cap.release()
        face_res: Any = "N/A"
        if self.face_compare_fn and self.faces_start and self.faces_middle:
            try:
                face_res = self.face_compare_fn(self.faces_start[0], self.faces_middle[0])
            except Exception as exc:
                face_res = {"success": False, "error": str(exc)}

        total_t = time.time() - start_t
        
        return {
            "id": int(time.time()),
            "hit_images": images_output,
            "meta": {
                "performance": {
                    "total_time_s": round(total_t, 2),
                    "frames_processed": processed
                },
                "stats": {
                    "total_juggles": self.juggles_count,
                    "last_hit_leg": self.last_hit_leg if self.juggles_count > 0 else "N/A", # INFO NUEVA EN JSON
                    "final_state": self.dribble_state,
                    "inferred_ball_size": f"Size {self.calibrator.selected_size_id} ({self.calibrator.real_diameter_cm}cm)",
                    "inferred_player_height_m": round(self.player_height_m, 2)
                },
                "face_verification": face_res
            }
        }
