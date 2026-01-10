import json
import cv2
import sys
import os
from ai_engine.src.services.smart_loader import SmartModelLoader


def record_to_json(video_path, output_json):
    cap = cv2.VideoCapture(video_path)

    det_model = None
    pose_model = None
    try:
        det_model = SmartModelLoader(os.path.join('ai_engine','models','yolov8n_640'), task='detect')
    except Exception as e:
        print(f"[Recorder] Warning: det_model load failed: {e}")
    try:
        pose_model = SmartModelLoader(os.path.join('ai_engine','models','yolov8s-pose_640'), task='pose')
    except Exception as e:
        print(f"[Recorder] Warning: pose_model load failed: {e}")

    recorded_data = []
    frame_idx = 0

    print("🔴 Iniciando grabación de datos...")

    while True:
        ret, frame = cap.read()
        if not ret: break

        raw_det = None
        raw_pose = None
        try:
            if det_model and hasattr(det_model, 'model'):
                raw_det = det_model.model(frame, verbose=False, conf=0.4)[0]
        except Exception as e:
            raw_det = None
        try:
            if pose_model and hasattr(pose_model, 'model'):
                raw_pose = pose_model.model(frame, verbose=False, conf=0.5)[0]
        except Exception as e:
            raw_pose = None

        # Extraer Balón
        ball_bbox = None
        if raw_det is not None:
            try:
                for box in getattr(raw_det, 'boxes', []):
                    if int(getattr(box, 'cls', -1)) == 32:
                        ball_bbox = box.xyxy[0].cpu().numpy().tolist()
                        break
            except Exception:
                ball_bbox = None

        # Extraer Pose
        pose_data = None
        if raw_pose is not None:
            try:
                if getattr(raw_pose, 'keypoints', None) is not None and len(raw_pose.keypoints.data) > 0:
                    kpts = raw_pose.keypoints.data[0].cpu().numpy()
                    bbox = raw_pose.boxes.xyxy[0].cpu().numpy().tolist()
                    kpts_list = []
                    for kp in kpts:
                        kpts_list.append({'x': float(kp[0]), 'y': float(kp[1]), 'conf': float(kp[2])})
                    pose_data = {
                        "kpts": kpts_list,
                        "box": bbox
                    }
            except Exception:
                pose_data = None

        frame_record = {
            "frame": frame_idx,
            "floor_y": int(frame.shape[0]),
            "ball": ball_bbox,
            "pose": pose_data
        }
        recorded_data.append(frame_record)
        frame_idx += 1

        if frame_idx % 30 == 0:
            print(f"Grabados {frame_idx} frames...")

    cap.release()

    with open(output_json, 'w') as f:
        json.dump(recorded_data, f)

    print(f"✅ Grabación guardada en {output_json}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python tools/record_session.py video_input.mp4 output_data.json")
        sys.exit(1)
    record_to_json(sys.argv[1], sys.argv[2])
