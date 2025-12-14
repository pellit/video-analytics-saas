import math
from collections import defaultdict, Counter
from typing import Dict, Any, List, Optional, Iterable, Set

import cv2
import numpy as np
from fastapi import HTTPException

from .object_analysis import (
    run_detectnet_inference,
    classify_frame_with_imagenet,
    annotate_depth_for_detections,
    infer_player_orientation,
    infer_contact_side,
    describe_depth_relation,
    extract_pose_for_bbox,
    compute_pose_ball_contacts,
)
from .video_utils import bgr_to_cuda


SOCCER_BALL_LABELS = {"sports_ball", "ball", "frisbee"}
GYM_EQUIPMENT_LABELS = {
    "barbell", "dumbbell", "bench", "kettlebell", "backpack", "suitcase",
    "handbag", "bottle", "chair", "cup"
}


class ActivityAnalyzer:
    """
    Agrupa la lógica de análisis de videos (fútbol/gym) y el fallback YOLO.
    """

    def __init__(
        self,
        yolo_fallback,
        enable_ball_fallback: bool,
        fallback_confidence: float,
        fallback_nms: float,
        soccer_labels: Optional[Iterable[str]] = None,
        gym_labels: Optional[Iterable[str]] = None,
    ):
        self.yolo_fallback = yolo_fallback
        self.enable_ball_fallback = enable_ball_fallback
        self.fallback_confidence = fallback_confidence
        self.fallback_nms = fallback_nms
        self.soccer_labels = set(soccer_labels or SOCCER_BALL_LABELS)
        self.gym_labels = set(gym_labels or GYM_EQUIPMENT_LABELS)

    # ------------------------------------------------------------------ #
    # Inference helpers
    # ------------------------------------------------------------------ #
    def run_inference(self, img: np.ndarray, confidence: float, nms_threshold: float) -> Dict[str, Any]:
        result = run_detectnet_inference(img, confidence, nms_threshold)
        detections = list(result.get("detections", []))
        has_ball = any(det.get("class_name", "").lower() in self.soccer_labels for det in detections)
        fallback_info = {
            "used": False,
            "reason": None,
            "new_detections": 0
        }

        if self.enable_ball_fallback and not has_ball:
            fallback_conf = max(confidence, self.fallback_confidence)
            fallback_nms = self.fallback_nms if self.fallback_nms > 0 else nms_threshold
            fallback_dets = self.yolo_fallback.detect(
                img,
                fallback_conf,
                fallback_nms,
                labels_filter=self.soccer_labels
            )
            if fallback_dets:
                fallback_info.update({
                    "used": True,
                    "reason": "ball_missing",
                    "new_detections": len(fallback_dets),
                    "confidence": fallback_conf
                })
                detections.extend(fallback_dets)
        result["detections"] = detections
        if fallback_info["used"]:
            result["ball_fallback"] = fallback_info
        return result

    # ------------------------------------------------------------------ #
    # Video analysis
    # ------------------------------------------------------------------ #
    def analyze_soccer_detections(
        self,
        video_path: str,
        frame_stride: int,
        max_frames: int,
        confidence: float,
        possession_distance_px: int,
        contact_threshold_px: Optional[int] = None,
        nms_threshold: float = 0.4
    ) -> Dict[str, Any]:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise HTTPException(400, "Unable to open uploaded video")

        frame_idx = 0
        processed = 0
        timeline = []
        class_names_detected: Set[str] = set()
        player_frames = 0
        ball_frames = 0
        possession_frames = 0
        juggling_hits = 0
        juggling_events: List[Dict[str, Any]] = []
        last_foot_contact_frame = None
        hand_contact_frames: List[int] = []
        hand_contact_events: List[Dict[str, Any]] = []
        juggling_gap = max(5, frame_stride * 2)
        ball_source_counts = defaultdict(int)

        while processed < max_frames:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % frame_stride != 0:
                frame_idx += 1
                continue

            inference = self.run_inference(frame, confidence, nms_threshold)
            detections = inference.get("detections", [])
            for det in detections:
                class_name = det.get("class_name")
                if class_name:
                    class_names_detected.add(class_name)
            depth_context = annotate_depth_for_detections(frame, detections)
            player_det = self._select_best_detection(detections, {"person"})
            ball_det = self._select_best_detection(detections, self.soccer_labels)

            entry: Dict[str, Any] = {"frame": frame_idx}
            classification = classify_frame_with_imagenet(frame)
            if classification:
                entry["scene_classification"] = classification
            if player_det:
                entry["player"] = player_det
                if depth_context:
                    entry["player_depth"] = player_det.get("depth_mean")
                    entry["player_orientation"] = infer_player_orientation(depth_context, player_det["bbox"])
                player_frames += 1
            if ball_det:
                entry["ball"] = ball_det
                if depth_context:
                    entry["ball_depth"] = ball_det.get("depth_mean")
                ball_frames += 1
                source = (ball_det.get("source") or "unknown").lower()
                ball_source_counts[source] += 1

            pose_data = None
            if player_det:
                pose_data = extract_pose_for_bbox(frame, player_det.get("bbox"))
                if pose_data:
                    entry["pose_keypoints"] = pose_data["keypoints"]

            if player_det and ball_det:
                distance = self._center_distance(player_det["bbox"], ball_det["bbox"])
                entry["player_ball_distance"] = round(distance, 2)
                entry["contact_side"] = infer_contact_side(player_det["bbox"], ball_det["bbox"])
                entry["depth_relation"] = describe_depth_relation(
                    player_det.get("depth_mean"),
                    ball_det.get("depth_mean")
                )
                if distance <= possession_distance_px:
                    possession_frames += 1

                contacts = compute_pose_ball_contacts(
                    pose_data,
                    ball_det["bbox"],
                    threshold_px=contact_threshold_px
                )
                if contacts:
                    limb_contacts = []
                    orientation = entry.get("player_orientation", "unknown")
                    for contact in contacts:
                        viewer_side = self._map_viewer_side(contact.get("side"), orientation)
                        contact_entry = {
                            **contact,
                            "viewer_side": viewer_side
                        }
                        limb_contacts.append(contact_entry)
                        if contact["limb_type"] in ("foot", "knee"):
                            if last_foot_contact_frame is None or frame_idx - last_foot_contact_frame <= juggling_gap:
                                juggling_hits += 1
                                juggling_events.append({
                                    "frame": frame_idx,
                                    "limb": contact["limb_name"],
                                    "viewer_side": viewer_side,
                                    "distance_px": contact["distance_px"]
                                })
                            last_foot_contact_frame = frame_idx
                        if contact["limb_type"] == "hand":
                            hand_contact_frames.append(frame_idx)
                            hand_contact_events.append({
                                "frame": frame_idx,
                                "limb": contact["limb_name"],
                                "viewer_side": viewer_side,
                                "distance_px": contact["distance_px"]
                            })
                    entry["limb_contacts"] = limb_contacts

            timeline.append(entry)
            processed += 1
            frame_idx += 1

        cap.release()
        total = len(timeline)

        def _ratio(count: int) -> float:
            return round((count / total) if total else 0.0, 4)

        ball_source_summary = [
            {"source": source, "frames": count, "ratio": _ratio(count)}
            for source, count in sorted(ball_source_counts.items(), key=lambda x: x[1], reverse=True)
        ]
        class_dictionary = {
            "detected_classes": sorted(class_names_detected),
            "ball_labels": sorted(self.soccer_labels),
            "primary_engine": "detectnet",
            "fallback_engine": self.yolo_fallback.model_name,
        }

        return {
            "frames_analyzed": processed,
            "timeline": timeline,
            "player_presence_ratio": _ratio(player_frames),
            "ball_presence_ratio": _ratio(ball_frames),
            "possession_ratio": _ratio(possession_frames),
            "juggling_hits": juggling_hits,
            "hand_contact_frames": hand_contact_frames,
            "juggling_events": juggling_events,
            "hand_contact_events": hand_contact_events,
            "ball_detection_sources": ball_source_summary,
            "ball_detection_counts": dict(ball_source_counts),
            "class_dictionary": class_dictionary
        }

    def analyze_gym_detections(
        self,
        video_path: str,
        frame_stride: int,
        max_frames: int,
        confidence: float,
        interaction_distance_px: int,
        nms_threshold: float = 0.4
    ) -> Dict[str, Any]:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise HTTPException(400, "Unable to open uploaded video")

        frame_idx = 0
        processed = 0
        timeline = []
        player_frames = 0
        equipment_frames = 0
        interaction_frames = 0
        prev_player_bbox = None
        vertical_variation_acc = 0.0
        vertical_variation_count = 0
        equipment_counts = defaultdict(int)

        while processed < max_frames:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % frame_stride != 0:
                frame_idx += 1
                continue

            inference = self.run_inference(frame, confidence, nms_threshold)
            detections = inference.get("detections", [])
            player_det = self._select_best_detection(detections, {"person"})
            equipment_det = self._select_best_detection(detections, self.gym_labels)

            entry: Dict[str, Any] = {"frame": frame_idx}
            if player_det:
                entry["athlete"] = player_det
                player_frames += 1
                if prev_player_bbox:
                    prev_height = prev_player_bbox[3] - prev_player_bbox[1]
                    curr_height = player_det["bbox"][3] - player_det["bbox"][1]
                    delta = abs(curr_height - prev_height)
                    vertical_variation_acc += delta
                    vertical_variation_count += 1
                prev_player_bbox = player_det["bbox"]
            else:
                prev_player_bbox = None

            if equipment_det:
                entry["equipment"] = equipment_det
                equipment_frames += 1
                label = equipment_det.get("class_name")
                if label:
                    equipment_counts[label] += 1

            if player_det and equipment_det:
                distance = self._center_distance(player_det["bbox"], equipment_det["bbox"])
                entry["athlete_equipment_distance"] = round(distance, 2)
                entry["interaction"] = distance <= interaction_distance_px
                if entry["interaction"]:
                    interaction_frames += 1

            timeline.append(entry)
            processed += 1
            frame_idx += 1

        cap.release()
        total = len(timeline)

        def _ratio(count: int) -> float:
            return round((count / total) if total else 0.0, 4)

        avg_variation = (
            round(vertical_variation_acc / vertical_variation_count, 2)
            if vertical_variation_count > 0 else 0.0
        )

        equipment_summary = [
            {"label": label, "ratio": _ratio(count)}
            for label, count in sorted(equipment_counts.items(), key=lambda x: x[1], reverse=True)
        ]

        return {
            "frames_analyzed": processed,
            "timeline": timeline,
            "player_presence_ratio": _ratio(player_frames),
            "equipment_presence_ratio": _ratio(equipment_frames),
            "interaction_ratio": _ratio(interaction_frames),
            "avg_vertical_variation": avg_variation,
            "equipment_summary": equipment_summary
        }

    # ------------------------------------------------------------------ #
    # Stats helpers
    # ------------------------------------------------------------------ #
    def compute_player_motion_metrics(self, timeline: List[Dict[str, Any]], fps: float) -> Dict[str, Any]:
        if not timeline or fps <= 0:
            return {
                "avg_speed_px_s": 0.0,
                "max_speed_px_s": 0.0,
                "total_distance_px": 0.0,
                "samples": 0,
                "movement_rating": "desconocido"
            }

        prev_center = None
        prev_frame = None
        total_distance = 0.0
        speeds = []

        for entry in timeline:
            player = entry.get("player")
            if not player or not player.get("bbox"):
                prev_center = None
                prev_frame = None
                continue
            center = self._bbox_center(player["bbox"])
            frame_number = int(entry.get("frame", 0))
            if prev_center is not None and prev_frame is not None:
                frame_delta = max(1, frame_number - prev_frame)
                delta_seconds = frame_delta / fps
                if delta_seconds > 0:
                    dist = math.hypot(center[0] - prev_center[0], center[1] - prev_center[1])
                    total_distance += dist
                    speeds.append(dist / delta_seconds)
            prev_center = center
            prev_frame = frame_number

        avg_speed = sum(speeds) / len(speeds) if speeds else 0.0
        max_speed = max(speeds) if speeds else 0.0
        if avg_speed < 40:
            movement_rating = "baja"
        elif avg_speed < 120:
            movement_rating = "media"
        else:
            movement_rating = "alta"

        return {
            "avg_speed_px_s": round(avg_speed, 2),
            "max_speed_px_s": round(max_speed, 2),
            "total_distance_px": round(total_distance, 2),
            "samples": len(speeds),
            "movement_rating": movement_rating
        }

    @staticmethod
    def summarize_orientation(timeline: List[Dict[str, Any]]) -> Dict[str, Any]:
        counts = Counter()
        for entry in timeline:
            orientation = entry.get("player_orientation")
            if orientation:
                counts[orientation] += 1
        total = sum(counts.values())
        if not total:
            return {
                "dominant_orientation": "unknown",
                "dominant_ratio": 0.0,
                "counts": []
            }
        dominant, dom_count = counts.most_common(1)[0]
        return {
            "dominant_orientation": dominant,
            "dominant_ratio": round(dom_count / total, 4),
            "counts": [
                {"orientation": key, "frames": value, "ratio": round(value / total, 4)}
                for key, value in counts.items()
            ]
        }

    def build_activity_report(
        self,
        metadata: Dict[str, Any],
        detection_summary: Dict[str, Any],
        action_analysis: Dict[str, Any],
        action_sequences: Dict[str, Any],
        motion_metrics: Dict[str, Any],
        orientation_summary: Dict[str, Any],
        face_checks: Dict[str, Any]
    ) -> Dict[str, Any]:
        fps = float(metadata.get("fps") or 0.0)
        frame_count = int(metadata.get("frame_count") or 0)
        duration = frame_count / fps if fps > 0 else 0.0

        player_pct = round(detection_summary.get("player_presence_ratio", 0.0) * 100, 1)
        ball_pct = round(detection_summary.get("ball_presence_ratio", 0.0) * 100, 1)
        possession_pct = round(detection_summary.get("possession_ratio", 0.0) * 100, 1)
        juggling_hits = int(detection_summary.get("juggling_hits", 0))
        hand_contacts = len(detection_summary.get("hand_contact_frames", []))
        ball_sources = detection_summary.get("ball_detection_sources", []) or []
        fallback_frames = sum(int(source.get("frames", 0)) for source in ball_sources if source.get("source") == "yolo")

        if ball_pct >= 25 and fallback_frames == 0:
            ball_tracking_quality = "sólida"
        elif ball_pct >= 8:
            ball_tracking_quality = "mixta"
        else:
            ball_tracking_quality = "débil"

        def _depth_stats(values: List[float]) -> Optional[Dict[str, float]]:
            if not values:
                return None
            return {
                "min": round(min(values), 3),
                "max": round(max(values), 3),
                "spread": round(max(values) - min(values), 3),
                "mean": round(sum(values) / len(values), 3)
            }

        def _depth_stats(values: List[float]) -> Optional[Dict[str, float]]:
            if not values:
                return None
            return {
                "min": round(min(values), 3),
                "max": round(max(values), 3),
                "spread": round(max(values) - min(values), 3),
                "mean": round(sum(values) / len(values), 3)
            }

        player_depth_values = [
            entry.get("player_depth")
            for entry in detection_summary.get("timeline", [])
            if entry.get("player_depth") is not None
        ]
        ball_depth_values = [
            entry.get("ball_depth")
            for entry in detection_summary.get("timeline", [])
            if entry.get("ball_depth") is not None
        ]

        motion_rating = motion_metrics.get("movement_rating", "desconocido")
        orientation_labels = {
            "facing_camera": "de frente a la cámara",
            "facing_away": "de espaldas a la cámara",
            "sideways": "de perfil",
            "unknown": "orientación desconocida",
            None: "orientación desconocida"
        }
        orientation_label = orientation_labels.get(
            orientation_summary.get("dominant_orientation"),
            orientation_labels["unknown"]
        )

        top_actions = (action_analysis or {}).get("top_labels", [])[:3]
        primary_action = top_actions[0] if top_actions else None

        action_segment = None
        if action_sequences and action_sequences.get("segments"):
            action_segment = action_sequences["segments"][0]

        ball_control_rating = "muy baja"
        if juggling_hits >= 6 or possession_pct >= 35:
            ball_control_rating = "alta"
        elif juggling_hits >= 3 or possession_pct >= 18:
            ball_control_rating = "media"
        elif ball_pct > 5:
            ball_control_rating = "baja"

        report_parts = [
            f"Analizamos {frame_count} frames (~{duration:.1f}s).",
            f"El jugador estuvo visible el {player_pct:.1f}% del tiempo."
        ]
        if ball_pct > 0:
            report_parts.append(
                f"El balón apareció el {ball_pct:.1f}% del tiempo y la posesión estimada fue del {possession_pct:.1f}%."
            )
        else:
            report_parts.append("El balón casi no fue detectado en el video.")

        report_parts.append(f"La movilidad general fue {motion_rating} y predominó una orientación {orientation_label}.")

        if primary_action:
            report_parts.append(
                f"ActionNet identificó '{primary_action['label']}' como acción dominante (confianza máx. {primary_action['max_confidence']:.2f})."
            )
        if juggling_hits > 0:
            report_parts.append(f"Se registraron {juggling_hits} toques/controles con miembros inferiores.")
        else:
            report_parts.append("No se observaron toques claros de control con los pies.")
        if hand_contacts > 0:
            report_parts.append(f"Se detectaron {hand_contacts} contactos con las manos.")
        if face_checks.get("consistent"):
            report_parts.append("Los chequeos faciales apuntan a que la misma persona aparece durante todo el clip.")
        else:
            report_parts.append("No pudimos confirmar que la misma persona aparezca en todo el video.")

        report_text = " ".join(report_parts)

        insights = [
            f"Movimiento {motion_rating} con velocidad promedio {motion_metrics.get('avg_speed_px_s', 0.0):.1f}px/s.",
            f"Control del balón catalogado como {ball_control_rating}.",
            f"Orientación predominante: {orientation_label}."
        ]
        if primary_action:
            insights.append(f"Acción dominante: {primary_action['label']} ({primary_action['count']} muestras).")
        if fallback_frames > 0:
            insights.append(f"Se usó fallback YOLO en {fallback_frames} frames para captar la pelota.")
        if hand_contacts > 0:
            insights.append(f"Advertencia: {hand_contacts} frames con posibles contactos de mano.")
        if face_checks.get("consistent"):
            insights.append("Chequeo facial consistente.")
        else:
            insights.append("El reconocimiento facial necesita mejor iluminación o primeros planos.")

        tips = []
        if ball_pct < 10:
            tips.append("Incrementa el contraste del balón o acércalo a cámara para mejorar la detección.")
        if motion_rating == "baja":
            tips.append("Agrega desplazamientos en diferentes direcciones para enriquecer el entrenamiento.")
        if hand_contacts > 0:
            tips.append("Evita el uso de las manos si buscas métricas estrictas de fútbol freestyle.")
        if not face_checks.get("consistent"):
            tips.append("Asegura buena iluminación frontal para que el sistema valide la identidad.")
        if not tips:
            tips.append("Mantén esta configuración: los sensores respondieron de forma estable.")

        metrics = {
            "player_presence_pct": player_pct,
            "ball_presence_pct": ball_pct,
            "possession_pct": possession_pct,
            "juggling_hits": juggling_hits,
            "hand_contacts": hand_contacts,
            "ball_detection_sources": ball_sources,
            "ball_tracking_quality": ball_tracking_quality,
            "ball_control_rating": ball_control_rating,
            "motion": motion_metrics,
            "orientation": orientation_summary,
            "dominant_actions": top_actions,
            "action_primary_segment": action_segment,
            "player_depth_stats": _depth_stats(player_depth_values),
            "ball_depth_stats": _depth_stats(ball_depth_values),
            "face_consistent": face_checks.get("consistent"),
            "face_successful_samples": face_checks.get("successful_samples", 0)
        }

        return {
            "report_text": report_text,
            "metrics": metrics,
            "insights": insights,
            "tips": tips
        }

    @staticmethod
    def derive_action_sequences(
        predictions: List[Dict[str, Any]],
        frame_stride: int,
        fps: float
    ) -> Dict[str, Any]:
        if not predictions or fps <= 0:
            return {
                "segments": [],
                "label_totals": []
            }

        time_per_sample = frame_stride / fps
        segments = []
        label_totals = defaultdict(int)
        current_label = None
        current_start = None
        current_count = 0

        for pred in predictions:
            label = pred.get("label")
            frame = pred.get("frame", 0)
            if label is None:
                continue
            label_totals[label] += 1
            if label != current_label:
                if current_label is not None:
                    segments.append({
                        "label": current_label,
                        "start_frame": current_start,
                        "end_frame": frame,
                        "estimated_seconds": round(current_count * time_per_sample, 2)
                    })
                current_label = label
                current_start = frame
                current_count = 0
            current_count += 1

        if current_label is not None:
            end_frame = predictions[-1].get("frame", current_start)
            segments.append({
                "label": current_label,
                "start_frame": current_start,
                "end_frame": end_frame,
                "estimated_seconds": round(current_count * time_per_sample, 2)
            })

        totals_payload = [
            {
                "label": label,
                "samples": count,
                "estimated_seconds": round(count * time_per_sample, 2)
            }
            for label, count in sorted(label_totals.items(), key=lambda x: x[1], reverse=True)
        ]

        return {
            "segments": segments,
            "label_totals": totals_payload
        }

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _select_best_detection(detections: List[Dict[str, Any]], label_set: Set[str]) -> Optional[Dict[str, Any]]:
        best = None
        for det in detections:
            if det.get("class_name", "").lower() in label_set:
                if best is None or det.get("confidence", 0) > best.get("confidence", 0):
                    best = det
        return best

    @staticmethod
    def _bbox_center(bbox: List[int]) -> tuple:
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    def _center_distance(self, bbox_a: List[int], bbox_b: List[int]) -> float:
        ax, ay = self._bbox_center(bbox_a)
        bx, by = self._bbox_center(bbox_b)
        return math.hypot(ax - bx, ay - by)

    @staticmethod
    def _map_viewer_side(player_side: Optional[str], orientation: Optional[str]) -> str:
        side = (player_side or "center").lower()
        orientation = (orientation or "unknown").lower()
        if side == "center":
            return "center"
        if orientation == "facing_away":
            return "right" if side == "left" else "left"
        if orientation == "sideways":
            return side
        if orientation == "facing_camera":
            return side
        return side
