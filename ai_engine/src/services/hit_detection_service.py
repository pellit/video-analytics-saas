import cv2
import numpy as np
import os
import urllib.request
import time
import base64
from typing import Any, Dict, List

# --- WRAPPER FOR POSE ESTIMATION (YOLOv8-Pose) ---
class YoloPoseWrapper:
    def __init__(self, model_path, confidence_thres=0.5, iou_thres=0.5):
        self.model_path = model_path
        self.conf_thres = confidence_thres
        self.iou_thres = iou_thres
        self.net = None
        self.input_width = 640
        self.input_height = 640

    def load_model(self):
        print(f"[Pose] Loading YOLOv8-Pose: {self.model_path}")
        self.net = cv2.dnn.readNet(self.model_path)
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
        self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)

    def preprocess(self, img):
        self.img_h, self.img_w = img.shape[:2]
        blob = cv2.dnn.blobFromImage(img, 1/255.0, (self.input_width, self.input_height), swapRB=True, crop=False)
        return blob

    def postprocess(self, outputs):
        predictions = np.squeeze(outputs[0]).T
        scores = predictions[:, 4]
        keep_idxs = scores > self.conf_thres
        predictions = predictions[keep_idxs]
        scores = scores[keep_idxs]

        if len(scores) == 0: return []

        boxes = predictions[:, :4]
        boxes_xywh = boxes.copy()
        boxes_xywh[:, 0] = boxes[:, 0] - boxes[:, 2] / 2
        boxes_xywh[:, 1] = boxes[:, 1] - boxes[:, 3] / 2
        kpts = predictions[:, 5:]

        indices = cv2.dnn.NMSBoxes(boxes_xywh.tolist(), scores.tolist(), self.conf_thres, self.iou_thres)
        
        results = []
        scale_w = self.img_w / self.input_width
        scale_h = self.img_h / self.input_height

        for i in indices.flatten():
            box = boxes_xywh[i]
            x = int(box[0] * scale_w)
            y = int(box[1] * scale_h)
            w = int(box[2] * scale_w)
            h = int(box[3] * scale_h)
            
            person_kpts = kpts[i].reshape(-1, 3)
            kpts_scaled = []
            for kp in person_kpts:
                kx, ky, kconf = kp
                kpts_scaled.append({
                    "x": int(kx * scale_w),
                    "y": int(ky * scale_h),
                    "conf": float(kconf)
                })

            results.append({
                "class_id": 0,
                "confidence": float(scores[i]),
                "box": [x, y, w, h],
                "keypoints": kpts_scaled
            })
        return results

# --- MAIN SERVICE ---
class HitDetectionService:
    def __init__(self, default_model_dirs: List[str] = None):
        # Paths
        self.models_dir = "/app/ai_engine/models"
        self.nanodet_path = os.path.join(self.models_dir, "nanodet-plus-m_416.onnx")
        self.pose_path = os.path.join(self.models_dir, "yolov8n-pose.onnx")
        self.midas_path = os.path.join(self.models_dir, "midas_v21_small.onnx")

        # Models
        self.nanodet_net = None
        self.pose_wrapper = None
        self.midas_net = None
        
        # Download and Load
        self._check_and_download_models()
        self._load_models()

    def _download_file(self, url, path):
        if os.path.exists(path) and os.path.getsize(path) > 1000000:
            return # Already exists
        
        print(f"⏳ Downloading {os.path.basename(path)}...")
        try:
            opener = urllib.request.build_opener()
            opener.addheaders = [('User-Agent', 'Mozilla/5.0')]
            urllib.request.install_opener(opener)
            urllib.request.urlretrieve(url, path)
            print("✅ Download OK.")
        except Exception as e:
            print(f"❌ Failed to download {url}: {e}")

    def _check_and_download_models(self):
        os.makedirs(self.models_dir, exist_ok=True)
        
        # 1. NanoDet Mirror
        self._download_file(
            "https://github.com/hpc203/nanodet-plus-opencv/raw/main/nanodet-plus-m_416.onnx", 
            self.nanodet_path
        )

        # 2. YOLO Pose Mirrors (Try multiple)
        if not os.path.exists(self.pose_path):
            mirrors = [
                "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n-pose.onnx",
                "https://github.com/akanametov/yolo-face-detection/releases/download/v0.0.1/yolov8n-pose.onnx"
            ]
            for url in mirrors:
                self._download_file(url, self.pose_path)
                if os.path.exists(self.pose_path): break

        # 3. MiDaS (Usually downloaded by Dockerfile, but check here)
        self._download_file(
            "https://github.com/isl-org/MiDaS/releases/download/v2_1/model-small.onnx",
            self.midas_path
        )

    def _load_models(self):
        # 1. Load NanoDet
        print("[AI] Loading NanoDet (Ball)...")
        self.nanodet_net = cv2.dnn.readNet(self.nanodet_path)
        self.nanodet_net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
        self.nanodet_net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)

        # 2. Load Pose
        print("[AI] Loading YOLO-Pose (Person)...")
        self.pose_wrapper = YoloPoseWrapper(self.pose_path)
        self.pose_wrapper.load_model()

        # 3. Load MiDaS (Depth)
        print("[AI] Loading MiDaS (Depth)...")
        self.midas_net = cv2.dnn.readNet(self.midas_path)
        self.midas_net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
        self.midas_net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)

    def detect_ball(self, frame):
        # NanoDet Preprocess
        blob = cv2.dnn.blobFromImage(frame, 0.017429, (416,416), (103.53, 116.28, 123.675), False, False)
        self.nanodet_net.setInput(blob)
        outputs = self.nanodet_net.forward(self.nanodet_net.getUnconnectedOutLayersNames())
        
        # Quick Postprocess for Class 32 (Sports Ball)
        preds = outputs[0][0]
        h, w = frame.shape[:2]
        scale_w, scale_h = w/416, h/416
        balls = []
        for det in preds:
            scores = det[4:]
            cls = np.argmax(scores)
            if cls == 32 and scores[cls] > 0.35: 
                 cx, cy, bw, bh = det[:4]
                 x = int((cx - bw/2)*scale_w)
                 y = int((cy - bh/2)*scale_h)
                 balls.append([x, y, int(bw*scale_w), int(bh*scale_h)])
        return balls

    def get_depth_map(self, frame):
        # MiDaS Preprocess (256x256)
        img_h, img_w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(frame, 1/255.0, (256, 256), (123.675, 116.28, 103.53), True, False)
        self.midas_net.setInput(blob)
        depth = self.midas_net.forward()
        
        # Resize depth map to match original image
        depth = depth[0,0]
        depth = cv2.resize(depth, (img_w, img_h))
        # Normalize to 0-255 for easier logic (0=far, 255=close)
        depth = cv2.normalize(depth, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)
        return depth

    def analyze_hit_with_depth(self, pose_results, ball_boxes, depth_map):
        """
        Detects hit using 3D logic: X, Y (2D dist) + Z (Depth similarity)
        """
        hit_events = []
        if not ball_boxes or not pose_results: return hit_events

        # Take first ball
        bx, by, bw, bh = ball_boxes[0]
        ball_center = (bx + bw//2, by + bh//2)
        
        # Get Ball Depth (Average of center area)
        try:
            ball_z = depth_map[ball_center[1], ball_center[0]]
        except:
            return hit_events

        for person in pose_results:
            kpts = person['keypoints']
            
            # Keypoints: 9=LeftWrist, 10=RightWrist
            wrists = [('Right', kpts[10]), ('Left', kpts[9])]
            
            for side, wrist in wrists:
                if wrist['conf'] < 0.5: continue
                
                wx, wy = wrist['x'], wrist['y']
                
                # 1. Calculate 2D Distance (Pixels)
                dist_2d = np.linalg.norm(np.array([wx, wy]) - np.array(ball_center))
                
                # 2. Get Wrist Depth
                try:
                    wrist_z = depth_map[wy, wx]
                except: continue

                # 3. Calculate Depth Difference
                dist_z = abs(int(ball_z) - int(wrist_z))
                
                # --- HIT LOGIC ---
                # 2D dist < 80px AND Depth diff < 20 units
                if dist_2d < 80 and dist_z < 30:
                    hit_events.append(f"Hit {side} Hand")

        return hit_events

    def run_on_video(self, video_path, frame_stride=3, max_frames=300, hit_threshold=0.4, return_images=False):
        cap = cv2.VideoCapture(video_path)
        frame_idx = 0
        processed = 0
        hits_detected = 0
        images_b64 = []

        start_time = time.time()

        while processed < max_frames:
            ret, frame = cap.read()
            if not ret: break

            if frame_idx % frame_stride != 0:
                frame_idx += 1
                continue

            # 1. Run AI Models
            balls = self.detect_ball(frame)
            
            # Only run Pose/Depth if ball is detected (Optimization)
            events = []
            if len(balls) > 0:
                pose_blob = self.pose_wrapper.preprocess(frame)
                self.pose_wrapper.net.setInput(pose_blob)
                pose_out = self.pose_wrapper.net.forward()
                people = self.pose_wrapper.postprocess(pose_out)
                
                depth_map = self.get_depth_map(frame)
                
                events = self.analyze_hit_with_depth(people, balls, depth_map)

            is_hit = len(events) > 0
            if is_hit: hits_detected += 1

            # Visualization
            if return_images and is_hit:
                vis_frame = frame.copy()
                # Draw Ball
                for b in balls:
                    cv2.rectangle(vis_frame, (b[0], b[1]), (b[0]+b[2], b[1]+b[3]), (0,0,255), 2)
                # Draw Events
                cv2.putText(vis_frame, f"{events[0]}", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                
                # Encode
                _, buffer = cv2.imencode('.jpg', vis_frame)
                img_b64 = base64.b64encode(buffer).decode('utf-8')
                images_b64.append({"frame": frame_idx, "event": events[0], "image": img_b64})

            processed += 1
            frame_idx += 1

        cap.release()
        total_time = time.time() - start_time
        
        return {
            "hits_detected": hits_detected,
            "performance": {"fps": round(processed/total_time, 2)},
            "hit_images": images_b64
        }