import base64
import math
import os
from typing import List, Dict, Any, Optional, Callable

import cv2
import numpy as np
from fastapi import HTTPException

try:
    import jetson.inference
    import jetson.utils
    JETSON_AVAILABLE = True
except ImportError:
    JETSON_AVAILABLE = False

from .jetson_env import JETSON_NETWORKS_DIR

pose_net = None
depth_net = None


def load_depthnet(model_name: str):
    global depth_net
    if depth_net is None:
        if not JETSON_AVAILABLE:
            raise HTTPException(503, "jetson-inference is not available on this device")
        try:
            depth_net = jetson.inference.depthNet(model_name)
        except Exception as exc:
            hint = JETSON_NETWORKS_DIR or "networks/"
            raise HTTPException(503, f"depthNet failed to load '{model_name}'. Revisa {hint}: {exc}")
    return depth_net


def load_posenet(model_name: str):
    global pose_net
    if pose_net is None:
        if not JETSON_AVAILABLE:
            raise HTTPException(503, "jetson-inference is not available on this device")
        try:
            pose_net = jetson.inference.poseNet(model_name)
        except Exception as exc:
            hint = JETSON_NETWORKS_DIR or "networks/"
            raise HTTPException(503, f"poseNet failed to load '{model_name}'. Revisa {hint}: {exc}")
    return pose_net


def _estimate_depth_for_bbox(depth_map: np.ndarray, bbox: List[int]) -> Optional[float]:
    if depth_map is None or depth_map.size == 0:
        return None
    x1, y1, x2, y2 = bbox
    x1 = max(0, int(x1))
    y1 = max(0, int(y1))
    x2 = min(depth_map.shape[1], int(x2))
    y2 = min(depth_map.shape[0], int(y2))
    if x2 <= x1 or y2 <= y1:
        return None
    region = depth_map[y1:y2, x1:x2]
    if region.size == 0:
        return None
    return float(np.mean(region))


def _compute_contact_labels(
    ball_center: Optional[tuple],
    poses,
    pose_model,
    max_distance_px: int = 40
) -> List[Dict[str, Any]]:
    def _kp_conf(keypoint) -> float:
        return float(
            getattr(
                keypoint,
                "confidence",
                getattr(keypoint, "Confidence", 0.0)
            )
        )

    contacts = []
    if ball_center is None or poses is None or pose_model is None:
        return contacts
    bx, by = ball_center
    for pose in poses:
        for keypoint in pose.Keypoints:
            confidence = _kp_conf(keypoint)
            if confidence < 0.2:
                continue
            dist = math.hypot(bx - keypoint.x, by - keypoint.y)
            if dist <= max_distance_px:
                label = pose_model.GetKeypointName(keypoint.ID)
                contacts.append({
                    "label": label,
                    "distance_px": round(dist, 2),
                    "confidence": confidence
                })
    return contacts


def run_depthnet_video(
    video_path: str,
    frame_stride: int,
    max_frames: int,
    preview_frames: int,
    depth_model_name: str,
    cuda_from_bgr: Callable
):
    net = load_depthnet(depth_model_name)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise HTTPException(400, "Unable to open uploaded video")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    if width <= 0 or height <= 0:
        cap.release()
        raise HTTPException(400, "Invalid video dimensions")

    frame_idx = 0
    processed = 0
    summaries = []
    previews = []

    while processed < max_frames:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_stride != 0:
            frame_idx += 1
            continue

        cuda_img = cuda_from_bgr(frame)

        if not hasattr(run_depthnet_video, 'overlay'):
            run_depthnet_video.overlay = jetson.utils.cudaAllocMapped(
                width=cuda_img.width,
                height=cuda_img.height,
                format=cuda_img.format
            )

        net.Process(cuda_img)
        net.Visualize(run_depthnet_video.overlay)

        depth_img = run_depthnet_video.overlay
        depth_np = jetson.utils.cudaToNumpy(depth_img, width, height, 1).squeeze()

        summaries.append({
            "frame": frame_idx,
            "mean_depth": float(np.mean(depth_np)),
            "min_depth": float(np.min(depth_np)),
            "max_depth": float(np.max(depth_np)),
        })

        if len(previews) < preview_frames:
            normalized = cv2.normalize(depth_np, None, 0, 255, cv2.NORM_MINMAX)
            normalized = np.clip(normalized, 0, 255).astype(np.uint8)
            normalized = np.ascontiguousarray(normalized)
            heatmap = cv2.applyColorMap(normalized, cv2.COLORMAP_PLASMA)
            _, buffer = cv2.imencode('.jpg', heatmap, [cv2.IMWRITE_JPEG_QUALITY, 85])
            previews.append({
                "frame": frame_idx,
                "preview_base64": "data:image/jpeg;base64," + base64.b64encode(buffer).decode()
            })

        processed += 1
        frame_idx += 1

    cap.release()

    return {
        "frames_analyzed": processed,
        "summaries": summaries,
        "previews": previews
    }


def analyze_depth_pose_video(
    video_path: str,
    frame_stride: int,
    max_frames: int,
    detection_confidence: float,
    contact_distance_px: int,
    detection_fn: Callable,
    depth_model_name: str,
    pose_model_name: str,
    cuda_from_bgr: Callable
):
    depthnet = load_depthnet(depth_model_name)
    pose_model = load_posenet(pose_model_name)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise HTTPException(400, "Unable to open uploaded video")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    if width <= 0 or height <= 0:
        cap.release()
        raise HTTPException(400, "Invalid video dimensions")

    frame_idx = 0
    processed = 0
    person_depth_series = []
    ball_depth_series = []
    events = []

    while processed < max_frames:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % frame_stride != 0:
            frame_idx += 1
            continue

        detection_result = detection_fn(frame, detection_confidence, 0.4)
        detections = detection_result.get("detections", [])

        cuda_img = cuda_from_bgr(frame)
        if not hasattr(analyze_depth_pose_video, 'depth_overlay'):
            analyze_depth_pose_video.depth_overlay = jetson.utils.cudaAllocMapped(
                width=cuda_img.width,
                height=cuda_img.height,
                format=cuda_img.format
            )

        depthnet.Process(cuda_img)
        depth_field = depthnet.GetDepthField()
        if depth_field:
            depth_np = jetson.utils.cudaToNumpy(depth_field, width, height, 1).squeeze()
        else:
            depthnet.Visualize(analyze_depth_pose_video.depth_overlay)
            depth_np = jetson.utils.cudaToNumpy(analyze_depth_pose_video.depth_overlay, width, height, 1).squeeze()

        pose_detections = pose_model.Process(cuda_img)

        person_depth = None
        ball_depth = None
        person_bbox = None
        ball_bbox = None
        for det in detections:
            label = det.get("class_name", "").lower()
            bbox = det.get("bbox")
            if not bbox:
                continue
            depth_value = _estimate_depth_for_bbox(depth_np, bbox)
            if label == "person" and (person_depth is None or (depth_value is not None and depth_value < person_depth)):
                person_depth = depth_value
                person_bbox = bbox
            elif label in ("sports_ball", "frisbee", "ball") and (ball_depth is None or (depth_value is not None and depth_value < ball_depth)):
                ball_depth = depth_value
                ball_bbox = bbox

        if person_depth is not None:
            person_depth_series.append({"frame": frame_idx, "depth": person_depth})
        if ball_depth is not None:
            ball_depth_series.append({"frame": frame_idx, "depth": ball_depth})

        ball_center = None
        if ball_bbox:
            x1, y1, x2, y2 = ball_bbox
            ball_center = (int((x1 + x2) / 2), int((y1 + y2) / 2))

        contact_labels = _compute_contact_labels(ball_center, pose_detections, pose_model, contact_distance_px)
        if contact_labels:
            events.append({
                "frame": frame_idx,
                "ball_depth": ball_depth,
                "person_depth": person_depth,
                "contact_points": contact_labels
            })

        processed += 1
        frame_idx += 1

    cap.release()

    def _analyze_trend(series):
        if not series:
            return "unknown"
        values = [item["depth"] for item in series if item["depth"] is not None]
        if not values:
            return "unknown"
        if len(values) == 1:
            return "stable"
        if values[-1] < values[0] - 0.1:
            return "approaching"
        if values[-1] > values[0] + 0.1:
            return "moving_away"
        return "stable"

    return {
        "frames_analyzed": processed,
        "person_depth_trend": _analyze_trend(person_depth_series),
        "ball_depth_trend": _analyze_trend(ball_depth_series),
        "person_depth_series": person_depth_series,
        "ball_depth_series": ball_depth_series,
        "contact_events": events
    }
