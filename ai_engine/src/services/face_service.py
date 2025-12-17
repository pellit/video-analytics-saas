import os
from typing import List, Dict, Any, Optional, Tuple
from uuid import uuid4

import cv2
import numpy as np
from fastapi import HTTPException

from .video_utils import bgr_to_cuda
from .video_io import read_frame_at

try:
    import jetson.inference
    import jetson.utils
    JETSON_INFERENCE_AVAILABLE = True
except ImportError:
    JETSON_INFERENCE_AVAILABLE = False


class _OnnxSFaceRecognizer:
    def __init__(self, model_path: str, template: np.ndarray):
        self.net = cv2.dnn.readNetFromONNX(model_path)
        self.template = template

    def extract(self, image: np.ndarray, bbox: List[int], landmarks: Optional[List[float]], target_size: Tuple[int, int]) -> List[float]:
        aligned = FaceEmbeddingService.align_face_crop(image, bbox, landmarks, target_size, template=self.template)
        blob = cv2.dnn.blobFromImage(
            aligned,
            scalefactor=1 / 255.0,
            size=target_size,
            mean=(0, 0, 0),
            swapRB=True,
            crop=False
        )
        self.net.setInput(blob)
        embedding = self.net.forward().flatten()
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        return embedding.astype(np.float32).tolist()


class FaceEmbeddingService:
    """Gestiona la detección/embedding/consistencia facial."""

    def __init__(
        self,
        face_detect_model_path: str,
        face_recognition_model_path: str,
        jetson_face_network: str,
        jetson_face_threshold: float,
        sface_input_size: Tuple[int, int],
        sface_template: np.ndarray,
    ):
        self.face_detect_model_path = face_detect_model_path
        self.face_recognition_model_path = face_recognition_model_path
        self.jetson_face_network = jetson_face_network
        self.jetson_face_threshold = jetson_face_threshold
        self.sface_input_size = sface_input_size
        self.sface_template = sface_template.astype(np.float32)

        self.face_detector = None
        self.face_detector_backend = None
        self.face_recognizer = None
        self.face_recognizer_backend = None

    # ------------------------------------------------------------------ #
    # Loaders
    # ------------------------------------------------------------------ #
    def _load_face_detector(self):
        if self.face_detector is not None:
            return self.face_detector, self.face_detector_backend

        if JETSON_INFERENCE_AVAILABLE:
            try:
                detector = jetson.inference.detectNet(self.jetson_face_network, threshold=self.jetson_face_threshold)
                self.face_detector = detector
                self.face_detector_backend = "jetson_detectnet"
                return detector, self.face_detector_backend
            except Exception:
                self.face_detector = None

        if hasattr(cv2, "FaceDetectorYN") and hasattr(cv2.FaceDetectorYN, "create"):
            model_path = self.face_detect_model_path
            if not os.path.exists(model_path):
                raise HTTPException(503, f"No se encontró el modelo de detección facial en {model_path}")
            try:
                self.face_detector = cv2.FaceDetectorYN.create(model_path, "", (320, 320))
                self.face_detector_backend = "yunet"
            except Exception as exc:
                raise HTTPException(503, f"cv2.FaceDetectorYN no pudo cargar '{model_path}': {exc}")
        else:
            cascade_path = getattr(cv2.data, "haarcascades", "") + "haarcascade_frontalface_default.xml"
            if not cascade_path or not os.path.exists(cascade_path):
                raise HTTPException(503, "OpenCV no tiene FaceDetectorYN y no se encontró haarcascade_frontalface_default.xml.")
            detector = cv2.CascadeClassifier(cascade_path)
            if detector.empty():
                raise HTTPException(503, "No se pudo inicializar el clasificador Haar para detección facial.")
            self.face_detector = detector
            self.face_detector_backend = "cascade"
        return self.face_detector, self.face_detector_backend

    def _load_face_recognizer(self):
        if self.face_recognizer is not None:
            return self.face_recognizer, self.face_recognizer_backend

        model_path = self.face_recognition_model_path
        if not os.path.exists(model_path):
            raise HTTPException(503, f"No se encontró el modelo de reconocimiento facial en {model_path}")

        if hasattr(cv2, "FaceRecognizerSF") and hasattr(cv2.FaceRecognizerSF, "create"):
            try:
                self.face_recognizer = cv2.FaceRecognizerSF.create(model_path, "")
                self.face_recognizer_backend = "opencv_sface"
                return self.face_recognizer, self.face_recognizer_backend
            except Exception:
                self.face_recognizer = None

        try:
            self.face_recognizer = _OnnxSFaceRecognizer(model_path, self.sface_template)
            self.face_recognizer_backend = "onnx_sface"
        except Exception as exc:
            raise HTTPException(503, f"No se pudo inicializar el modelo de reconocimiento facial: {exc}")
        return self.face_recognizer, self.face_recognizer_backend

    # ------------------------------------------------------------------ #
    # Detection / embedding
    # ------------------------------------------------------------------ #
    @staticmethod
    def align_face_crop(
        image: np.ndarray,
        bbox: List[int],
        landmarks: Optional[List[float]],
        target_size: Tuple[int, int],
        template: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        x1, y1, x2, y2 = bbox
        x1 = max(0, int(x1))
        y1 = max(0, int(y1))
        x2 = min(image.shape[1], int(x2))
        y2 = min(image.shape[0], int(y2))
        if x2 <= x1 or y2 <= y1:
            return cv2.resize(image, target_size)
        if landmarks and len(landmarks) >= 10:
            src = np.array(landmarks[:10], dtype=np.float32).reshape(5, 2)
            template = template if template is not None else np.array([
                [38.2946, 51.6963],
                [73.5318, 51.5014],
                [56.0252, 71.7366],
                [41.5493, 92.3655],
                [70.7299, 92.2041]
            ], dtype=np.float32)
            try:
                M, _ = cv2.estimateAffinePartial2D(src, template, method=cv2.LMEDS)
            except Exception:
                M = None
            if M is not None:
                return cv2.warpAffine(image, M, target_size)
        face = image[y1:y2, x1:x2]
        if face.size == 0:
            return cv2.resize(image, target_size)
        return cv2.resize(face, target_size)

    def detect_with_embeddings(self, image: np.ndarray, score_threshold: float = 0.6) -> List[Dict[str, Any]]:
        detector, backend = self._load_face_detector()
        recognizer, recognizer_backend = self._load_face_recognizer()
        h, w = image.shape[:2]
        detections: List[Dict[str, Any]] = []
        multiscale_factors = [1.0, 0.85, 0.7, 0.55]

        def _scale_image(src: np.ndarray, scale: float) -> np.ndarray:
            if scale == 1.0:
                return src
            new_w = max(1, int(src.shape[1] * scale))
            new_h = max(1, int(src.shape[0] * scale))
            return cv2.resize(src, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        if backend == "jetson_detectnet":
            for scale in multiscale_factors:
                scaled_img = _scale_image(image, scale)
                cuda_img = bgr_to_cuda(scaled_img)
                raw = detector.Detect(cuda_img, overlay="none")
                if raw:
                    inv_scale = 1.0 / scale
                    for det in raw:
                        if not np.isfinite(det.Left) or not np.isfinite(det.Top) or not np.isfinite(det.Right) or not np.isfinite(det.Bottom):
                            continue
                        x1 = max(0, int(det.Left * inv_scale))
                        y1 = max(0, int(det.Top * inv_scale))
                        x2 = min(w, int(det.Right * inv_scale))
                        y2 = min(h, int(det.Bottom * inv_scale))
                        detections.append({
                            "bbox": [x1, y1, x2, y2],
                            "score": float(det.Confidence),
                            "landmarks": None,
                            "raw": None
                        })
                    if detections:
                        break
        elif backend == "yunet":
            for scale in multiscale_factors:
                scaled_img = _scale_image(image, scale)
                scaled_h, scaled_w = scaled_img.shape[:2]
                detector.setInputSize((scaled_w, scaled_h))
                _, raw = detector.detect(scaled_img)
                if raw is None or len(raw) == 0:
                    continue
                inv_scale = 1.0 / scale
                for face in raw:
                    x, y, box_w, box_h = face[:4]
                    if not np.isfinite(x) or not np.isfinite(y) or not np.isfinite(box_w) or not np.isfinite(box_h):
                        continue
                    x1 = max(0, int(x * inv_scale))
                    y1 = max(0, int(y * inv_scale))
                    x2 = min(w, int((x + box_w) * inv_scale))
                    y2 = min(h, int((y + box_h) * inv_scale))
                    landmarks = None
                    raw_face = None
                    if len(face) >= 14 and np.all(np.isfinite(face[4:14])):
                        lm = (face[4:14] * inv_scale).tolist()
                        landmarks = lm
                        raw_face = face.copy().astype(np.float32)
                        raw_face[0] = x1
                        raw_face[1] = y1
                        raw_face[2] = max(0, x2 - x1)
                        raw_face[3] = max(0, y2 - y1)
                        raw_face[4:14] = face[4:14] * inv_scale
                    detections.append({
                        "bbox": [x1, y1, x2, y2],
                        "score": float(face[4]) if len(face) > 4 else 0.0,
                        "landmarks": landmarks,
                        "raw": raw_face
                    })
                if detections:
                    break
        else:
            gray_original = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            for scale in multiscale_factors:
                scaled_gray = _scale_image(gray_original, scale)
                raw = detector.detectMultiScale(
                    scaled_gray,
                    scaleFactor=1.1,
                    minNeighbors=5,
                    minSize=(48, 48)
                )
                if len(raw) == 0:
                    continue
                inv_scale = 1.0 / scale
                for (x, y, box_w, box_h) in raw:
                    x1 = max(0, int(x * inv_scale))
                    y1 = max(0, int(y * inv_scale))
                    x2 = min(w, int((x + box_w) * inv_scale))
                    y2 = min(h, int((y + box_h) * inv_scale))
                    detections.append({
                        "bbox": [x1, y1, x2, y2],
                        "score": 1.0,
                        "landmarks": None,
                        "raw": None
                    })
                if detections:
                    break

        results = []
        for det in detections:
            if det["score"] < score_threshold:
                continue

            bbox = det["bbox"]
            landmarks = det.get("landmarks")
            embedding: Optional[List[float]] = None

            if recognizer_backend == "opencv_sface" and det["raw"] is not None:
                try:
                    embedding = recognizer.feature(image, det["raw"]).flatten().tolist()
                except Exception:
                    embedding = None
            else:
                try:
                    embedding = recognizer.extract(image, bbox, landmarks, self.sface_input_size)
                except Exception:
                    embedding = None

            if not embedding:
                continue

            bbox_int = [
                int(max(0, min(w, bbox[0]))),
                int(max(0, min(h, bbox[1]))),
                int(max(0, min(w, bbox[2]))),
                int(max(0, min(h, bbox[3]))),
            ]
            results.append({
                "face_id": str(uuid4()),
                "bbox": bbox_int,
                "score": det["score"],
                "embedding": embedding
            })
        return results

    def get_primary_face_embedding(self, image: np.ndarray, min_score: float = 0.6) -> Optional[Dict[str, Any]]:
        faces = self.detect_with_embeddings(image, min_score)
        if not faces:
            return None
        return max(faces, key=lambda f: f["score"])

    def compare_embeddings(self, embedding_a: List[float], embedding_b: List[float]) -> float:
        recognizer, backend = self._load_face_recognizer()
        vec_a = np.array(embedding_a, dtype=np.float32).reshape(1, -1)
        vec_b = np.array(embedding_b, dtype=np.float32).reshape(1, -1)
        if backend == "opencv_sface":
            return float(recognizer.match(vec_a, vec_b, cv2.FaceRecognizerSF_FR_COSINE))
        similarity = float(np.dot(vec_a.flatten(), vec_b.flatten()))
        return similarity

    def evaluate_face_consistency(
        self,
        video_path: str,
        frame_count: int,
        score_threshold: float,
        match_threshold: float
    ) -> Dict[str, Any]:
        if frame_count <= 0:
            return {
                "threshold": match_threshold,
                "samples": [],
                "pairwise": [],
                "consistent": False,
                "note": "El video no contiene frames válidos"
            }

        targets = [
            ("start", 0),
            ("middle", max(frame_count // 2, 0)),
            ("end", max(frame_count - 1, 0)),
        ]

        samples = []
        embeddings: Dict[str, List[float]] = {}

        for label, idx in targets:
            frame = read_frame_at(video_path, idx)
            sample = {
                "position": label,
                "frame": int(idx),
                "success": False
            }
            if frame is None:
                sample["error"] = "frame_unavailable"
            else:
                face = self.get_primary_face_embedding(frame, score_threshold)
                if face:
                    sample["success"] = True
                    sample["score"] = float(face["score"])
                    sample["face_id"] = face["face_id"]
                    embeddings[label] = face["embedding"]
                else:
                    sample["error"] = "face_not_detected"
            samples.append(sample)

        pairwise = []
        positions_to_compare = [("start", "middle"), ("middle", "end"), ("start", "end")]
        for ref, other in positions_to_compare:
            if ref in embeddings and other in embeddings:
                similarity = self.compare_embeddings(embeddings[ref], embeddings[other])
                pairwise.append({
                    "pair": f"{ref}-{other}",
                    "similarity": similarity,
                    "match": similarity >= match_threshold
                })

        consistent = bool(pairwise) and all(item["match"] for item in pairwise)
        return {
            "threshold": match_threshold,
            "samples": samples,
            "pairwise": pairwise,
            "consistent": consistent,
            "successful_samples": sum(1 for sample in samples if sample["success"])
        }
