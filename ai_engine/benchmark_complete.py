#!/usr/bin/env python3
"""
Benchmark Completo de Modelos de Detección
==========================================
Prueba todos los modelos disponibles con diferentes resoluciones y optimizaciones.

Modelos a probar:
- OpenCV YOLOv4-tiny (actual default)
- NanoDet-Plus ONNX
- ONNX YOLO-NAS
- MediaPipe Object Detection
- MediaPipe Pose Detection
- EfficientDet-Lite0 TFLite
- YOLOv8n OpenVINO INT8 (cuantizado)
- MobileNet-SSD

Resoluciones:
- LOW: 320x320
- MEDIUM: 416x416  
- HIGH: 640x640

Optimizaciones:
- SimpleJPEG compression para entrada
- Skip frame analysis (solo stream rápido)
"""

import cv2
import numpy as np
import time
import os
import urllib.request
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import json

# Configuración
VIDEO_URL = "https://www.youtube.com/watch?v=MNn9qKG2UFI"  # Traffic video
NUM_FRAMES = 100  # Frames para benchmark
MODELS_DIR = "benchmark_models"
RESULTS_FILE = "benchmark_results.json"

# Resoluciones a probar
RESOLUTIONS = {
    "LOW": (320, 320),
    "MEDIUM": (416, 416),
    "HIGH": (640, 640)
}

@dataclass
class BenchmarkResult:
    model_name: str
    resolution: str
    input_size: Tuple[int, int]
    avg_fps: float
    avg_time_ms: float
    total_detections: int
    model_size_mb: float
    notes: str = ""

def download_video():
    """Descarga video de prueba usando yt-dlp"""
    video_path = "test_video.mp4"
    if os.path.exists(video_path):
        print(f"✅ Video ya existe: {video_path}")
        return video_path
    
    print("📥 Descargando video de prueba...")
    try:
        subprocess.run([
            "yt-dlp", "-f", "best[height<=480]",
            "-o", video_path, VIDEO_URL
        ], check=True, capture_output=True)
        print(f"✅ Video descargado: {video_path}")
        return video_path
    except Exception as e:
        print(f"⚠️ Error descargando video: {e}")
        # Crear video sintético
        return create_synthetic_video()

def create_synthetic_video():
    """Crea video sintético si no se puede descargar"""
    video_path = "test_video_synthetic.mp4"
    if os.path.exists(video_path):
        return video_path
    
    print("🎬 Creando video sintético...")
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(video_path, fourcc, 30, (640, 480))
    
    for i in range(300):
        frame = np.random.randint(50, 200, (480, 640, 3), dtype=np.uint8)
        # Añadir rectángulos simulando objetos
        for _ in range(np.random.randint(1, 5)):
            x, y = np.random.randint(50, 500), np.random.randint(50, 400)
            w, h = np.random.randint(30, 100), np.random.randint(30, 100)
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), -1)
        out.write(frame)
    out.release()
    return video_path

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def download_file(url, path):
    """Descarga archivo si no existe"""
    if os.path.exists(path):
        return True
    print(f"  📥 Descargando: {os.path.basename(path)}...")
    try:
        urllib.request.urlretrieve(url, path)
        return True
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

def get_file_size_mb(path):
    if os.path.exists(path):
        return os.path.getsize(path) / (1024 * 1024)
    return 0

def compress_frame_jpeg(frame, quality=80):
    """Comprime frame usando JPEG para entrada más rápida"""
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    _, encoded = cv2.imencode('.jpg', frame, encode_param)
    return cv2.imdecode(encoded, cv2.IMREAD_COLOR)

def resize_frame(frame, target_size):
    """Redimensiona frame manteniendo aspecto"""
    return cv2.resize(frame, target_size, interpolation=cv2.INTER_LINEAR)

# ============================================================================
# DETECTORES
# ============================================================================

class BaseDetector:
    name = "Base"
    model_size_mb = 0
    
    def load(self) -> bool:
        raise NotImplementedError
    
    def detect(self, frame: np.ndarray) -> int:
        """Retorna número de detecciones"""
        raise NotImplementedError
    
    def set_input_size(self, size: Tuple[int, int]):
        """Configura tamaño de entrada"""
        pass

# ----------------------------------------------------------------------------
# 1. OpenCV YOLOv4-tiny
# ----------------------------------------------------------------------------
class YOLOv4TinyDetector(BaseDetector):
    name = "OpenCV YOLOv4-tiny"
    
    def __init__(self):
        self.net = None
        self.input_size = (416, 416)
        self.cfg_path = f"{MODELS_DIR}/yolov4-tiny.cfg"
        self.weights_path = f"{MODELS_DIR}/yolov4-tiny.weights"
    
    def load(self) -> bool:
        ensure_dir(MODELS_DIR)
        cfg_url = "https://raw.githubusercontent.com/AlexeyAB/darknet/master/cfg/yolov4-tiny.cfg"
        weights_url = "https://github.com/AlexeyAB/darknet/releases/download/darknet_yolo_v4_pre/yolov4-tiny.weights"
        
        if not download_file(cfg_url, self.cfg_path):
            return False
        if not download_file(weights_url, self.weights_path):
            return False
        
        self.model_size_mb = get_file_size_mb(self.weights_path)
        
        try:
            self.net = cv2.dnn.readNetFromDarknet(self.cfg_path, self.weights_path)
            self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
            self.layer_names = self.net.getUnconnectedOutLayersNames()
            return True
        except Exception as e:
            print(f"  ❌ Error cargando YOLOv4-tiny: {e}")
            return False
    
    def set_input_size(self, size):
        self.input_size = size
    
    def detect(self, frame) -> int:
        blob = cv2.dnn.blobFromImage(frame, 1/255.0, self.input_size, swapRB=True, crop=False)
        self.net.setInput(blob)
        outputs = self.net.forward(self.layer_names)
        
        detections = 0
        for output in outputs:
            for detection in output:
                scores = detection[5:]
                if np.max(scores) > 0.5:
                    detections += 1
        return detections

# ----------------------------------------------------------------------------
# 2. NanoDet-Plus ONNX
# ----------------------------------------------------------------------------
class NanoDetDetector(BaseDetector):
    name = "NanoDet-Plus ONNX"
    
    def __init__(self):
        self.session = None
        self.input_size = (416, 416)  # Fixed size for this model
        self.fixed_input = True
        self.model_path = f"{MODELS_DIR}/nanodet-plus-m_416.onnx"
    
    def load(self) -> bool:
        ensure_dir(MODELS_DIR)
        url = "https://github.com/RangiLyu/nanodet/releases/download/v1.0.0-alpha-1/nanodet-plus-m_416.onnx"
        
        if not download_file(url, self.model_path):
            return False
        
        self.model_size_mb = get_file_size_mb(self.model_path)
        
        try:
            import onnxruntime as ort
            self.session = ort.InferenceSession(self.model_path, providers=['CPUExecutionProvider'])
            self.input_name = self.session.get_inputs()[0].name
            return True
        except Exception as e:
            print(f"  ❌ Error cargando NanoDet: {e}")
            return False
    
    def set_input_size(self, size):
        # NanoDet has fixed input size, ignore
        pass
    
    def detect(self, frame) -> int:
        # Always use 416x416 for NanoDet
        img = cv2.resize(frame, (416, 416))
        img = img.astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))
        img = np.expand_dims(img, axis=0)
        
        outputs = self.session.run(None, {self.input_name: img})
        # Simplificado: contar outputs con confianza > 0.5
        detections = 0
        for out in outputs:
            if out is not None:
                detections += np.sum(out > 0.5)
        return min(detections, 100)  # Cap

# ----------------------------------------------------------------------------
# 3. ONNX YOLO-NAS
# ----------------------------------------------------------------------------
class YOLONASDetector(BaseDetector):
    name = "ONNX YOLO-NAS"
    
    def __init__(self):
        self.session = None
        self.input_size = (640, 640)  # Fixed for YOLO-NAS
        self.fixed_input = True
        self.model_path = "models/yolo_nas_s.onnx"
    
    def load(self) -> bool:
        if not os.path.exists(self.model_path):
            print(f"  ⚠️ Modelo no encontrado: {self.model_path}")
            return False
        
        self.model_size_mb = get_file_size_mb(self.model_path)
        
        try:
            import onnxruntime as ort
            self.session = ort.InferenceSession(self.model_path, providers=['CPUExecutionProvider'])
            self.input_name = self.session.get_inputs()[0].name
            return True
        except Exception as e:
            print(f"  ❌ Error cargando YOLO-NAS: {e}")
            return False
    
    def set_input_size(self, size):
        # YOLO-NAS ONNX has fixed input size
        pass
    
    def detect(self, frame) -> int:
        # Always use 640x640
        img = cv2.resize(frame, (640, 640))
        img = img.astype(np.uint8)
        img = np.expand_dims(img, axis=0)
        
        outputs = self.session.run(None, {self.input_name: img})
        # outputs[0] = boxes, outputs[1] = scores
        if len(outputs) >= 2:
            scores = outputs[1]
            return int(np.sum(scores > 0.5))
        return 0

# ----------------------------------------------------------------------------
# 4. MediaPipe Object Detection
# ----------------------------------------------------------------------------
class MediaPipeObjectDetector(BaseDetector):
    name = "MediaPipe Object Detection"
    
    def __init__(self):
        self.detector = None
        self.model_path = f"{MODELS_DIR}/efficientdet_lite0.tflite"
    
    def load(self) -> bool:
        ensure_dir(MODELS_DIR)
        # EfficientDet-Lite0 para MediaPipe
        url = "https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/int8/latest/efficientdet_lite0.tflite"
        
        if not download_file(url, self.model_path):
            return False
        
        self.model_size_mb = get_file_size_mb(self.model_path)
        
        try:
            import mediapipe as mp
            from mediapipe.tasks import python
            from mediapipe.tasks.python import vision
            
            base_options = python.BaseOptions(model_asset_path=self.model_path)
            options = vision.ObjectDetectorOptions(
                base_options=base_options,
                score_threshold=0.5,
                max_results=20
            )
            self.detector = vision.ObjectDetector.create_from_options(options)
            return True
        except Exception as e:
            print(f"  ❌ Error cargando MediaPipe Object: {e}")
            return False
    
    def detect(self, frame) -> int:
        try:
            import mediapipe as mp
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
            result = self.detector.detect(mp_image)
            return len(result.detections)
        except:
            return 0

# ----------------------------------------------------------------------------
# 5. MediaPipe Pose Detection
# ----------------------------------------------------------------------------
class MediaPipePoseDetector(BaseDetector):
    name = "MediaPipe Pose"
    
    def __init__(self):
        self.pose = None
    
    def load(self) -> bool:
        try:
            import mediapipe as mp
            self.mp_pose = mp.solutions.pose
            self.pose = self.mp_pose.Pose(
                static_image_mode=False,
                model_complexity=0,  # 0=lite, 1=full, 2=heavy
                min_detection_confidence=0.5
            )
            self.model_size_mb = 3.0  # Aproximado
            return True
        except Exception as e:
            print(f"  ❌ Error cargando MediaPipe Pose: {e}")
            return False
    
    def detect(self, frame) -> int:
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.pose.process(rgb_frame)
        if results.pose_landmarks:
            return 1  # Una pose detectada
        return 0

# ----------------------------------------------------------------------------
# 6. EfficientDet-Lite TFLite (directo)
# ----------------------------------------------------------------------------
class EfficientDetLiteDetector(BaseDetector):
    name = "EfficientDet-Lite0 TFLite"
    
    def __init__(self):
        self.interpreter = None
        self.model_path = f"{MODELS_DIR}/efficientdet_lite0_int8.tflite"
        self.input_size = (320, 320)
    
    def load(self) -> bool:
        ensure_dir(MODELS_DIR)
        # INT8 quantized version
        url = "https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/int8/latest/efficientdet_lite0.tflite"
        
        if not download_file(url, self.model_path):
            return False
        
        self.model_size_mb = get_file_size_mb(self.model_path)
        
        try:
            import tflite_runtime.interpreter as tflite
            self.interpreter = tflite.Interpreter(model_path=self.model_path)
            self.interpreter.allocate_tensors()
            self.input_details = self.interpreter.get_input_details()
            self.output_details = self.interpreter.get_output_details()
            return True
        except ImportError:
            try:
                import tensorflow as tf
                self.interpreter = tf.lite.Interpreter(model_path=self.model_path)
                self.interpreter.allocate_tensors()
                self.input_details = self.interpreter.get_input_details()
                self.output_details = self.interpreter.get_output_details()
                return True
            except Exception as e:
                print(f"  ❌ Error cargando TFLite: {e}")
                return False
    
    def set_input_size(self, size):
        self.input_size = size
    
    def detect(self, frame) -> int:
        # Preparar entrada
        input_shape = self.input_details[0]['shape']
        h, w = input_shape[1], input_shape[2]
        img = cv2.resize(frame, (w, h))
        img = np.expand_dims(img, axis=0)
        
        if self.input_details[0]['dtype'] == np.uint8:
            img = img.astype(np.uint8)
        else:
            img = img.astype(np.float32) / 255.0
        
        self.interpreter.set_tensor(self.input_details[0]['index'], img)
        self.interpreter.invoke()
        
        # Obtener scores
        scores = self.interpreter.get_tensor(self.output_details[2]['index'])
        return int(np.sum(scores > 0.5))

# ----------------------------------------------------------------------------
# 7. MobileNet-SSD
# ----------------------------------------------------------------------------
class MobileNetSSDDetector(BaseDetector):
    name = "MobileNet-SSD"
    
    def __init__(self):
        self.net = None
        self.input_size = (300, 300)
        self.prototxt = f"{MODELS_DIR}/MobileNetSSD_deploy.prototxt"
        self.model_path = f"{MODELS_DIR}/MobileNetSSD_deploy.caffemodel"
    
    def load(self) -> bool:
        ensure_dir(MODELS_DIR)
        
        prototxt_url = "https://raw.githubusercontent.com/chuanqi305/MobileNet-SSD/master/deploy.prototxt"
        # Caffemodel hosting alternativo
        model_url = "https://github.com/chuanqi305/MobileNet-SSD/raw/master/mobilenet_iter_73000.caffemodel"
        
        if not download_file(prototxt_url, self.prototxt):
            return False
        if not download_file(model_url, self.model_path):
            return False
        
        self.model_size_mb = get_file_size_mb(self.model_path)
        
        try:
            self.net = cv2.dnn.readNetFromCaffe(self.prototxt, self.model_path)
            self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
            return True
        except Exception as e:
            print(f"  ❌ Error cargando MobileNet-SSD: {e}")
            return False
    
    def detect(self, frame) -> int:
        blob = cv2.dnn.blobFromImage(frame, 0.007843, self.input_size, 127.5)
        self.net.setInput(blob)
        detections = self.net.forward()
        
        count = 0
        for i in range(detections.shape[2]):
            confidence = detections[0, 0, i, 2]
            if confidence > 0.5:
                count += 1
        return count

# ----------------------------------------------------------------------------
# 8. YOLOv8n OpenVINO INT8
# ----------------------------------------------------------------------------
class YOLOv8OpenVINODetector(BaseDetector):
    name = "YOLOv8n OpenVINO INT8"
    
    def __init__(self):
        self.model = None
        self.input_size = (320, 320)
        self.model_dir = f"{MODELS_DIR}/yolov8n_openvino_int8"
    
    def load(self) -> bool:
        ensure_dir(MODELS_DIR)
        
        try:
            # Verificar si ya existe modelo exportado
            if os.path.exists(f"{self.model_dir}/yolov8n_int8_openvino_model"):
                print("  ✅ Modelo OpenVINO ya existe")
            else:
                print("  🔧 Exportando YOLOv8n a OpenVINO INT8...")
                from ultralytics import YOLO
                model = YOLO("yolov8n.pt")
                model.export(format="openvino", int8=True, imgsz=320)
                # Mover a directorio
                import shutil
                src = "yolov8n_int8_openvino_model"
                if os.path.exists(src):
                    shutil.move(src, self.model_dir)
            
            # Cargar con OpenVINO
            from openvino.runtime import Core
            ie = Core()
            model_xml = f"{self.model_dir}/yolov8n.xml"
            if not os.path.exists(model_xml):
                # Buscar archivo xml
                import glob
                xmls = glob.glob(f"{self.model_dir}/**/*.xml", recursive=True)
                if xmls:
                    model_xml = xmls[0]
                else:
                    print(f"  ❌ No se encontró modelo XML en {self.model_dir}")
                    return False
            
            self.model = ie.compile_model(model_xml, "CPU")
            self.infer_request = self.model.create_infer_request()
            self.input_layer = self.model.input(0)
            self.output_layer = self.model.output(0)
            
            # Calcular tamaño
            total_size = 0
            for f in os.listdir(self.model_dir):
                total_size += os.path.getsize(os.path.join(self.model_dir, f))
            self.model_size_mb = total_size / (1024 * 1024)
            
            return True
        except ImportError:
            print("  ⚠️ OpenVINO no instalado. Ejecutar: pip install openvino")
            return False
        except Exception as e:
            print(f"  ❌ Error cargando OpenVINO: {e}")
            return False
    
    def set_input_size(self, size):
        self.input_size = size
    
    def detect(self, frame) -> int:
        img = cv2.resize(frame, self.input_size)
        img = img.astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))
        img = np.expand_dims(img, axis=0)
        
        self.infer_request.infer({self.input_layer: img})
        output = self.infer_request.get_output_tensor(0).data
        
        # Contar detecciones con confianza > 0.5
        detections = 0
        if output is not None:
            # YOLOv8 output format: [batch, num_detections, 85] or similar
            if len(output.shape) >= 2:
                # Buscar scores
                for det in output[0]:
                    if len(det) > 4:
                        conf = np.max(det[4:])
                        if conf > 0.5:
                            detections += 1
        return detections

# ----------------------------------------------------------------------------
# 9. YOLO-Fastest (ultra-ligero)
# ----------------------------------------------------------------------------
class YOLOFastestDetector(BaseDetector):
    name = "YOLO-Fastest"
    
    def __init__(self):
        self.net = None
        self.input_size = (320, 320)
        self.cfg_path = f"{MODELS_DIR}/yolo-fastest.cfg"
        self.weights_path = f"{MODELS_DIR}/yolo-fastest.weights"
    
    def load(self) -> bool:
        ensure_dir(MODELS_DIR)
        
        # YOLO-Fastest - super ligero (~1MB)
        cfg_url = "https://raw.githubusercontent.com/dog-qiuqiu/Yolo-Fastest/master/ModelZoo/yolo-fastest-1.1_coco/yolo-fastest-1.1-xl.cfg"
        weights_url = "https://github.com/dog-qiuqiu/Yolo-Fastest/raw/master/ModelZoo/yolo-fastest-1.1_coco/yolo-fastest-1.1-xl.weights"
        
        if not download_file(cfg_url, self.cfg_path):
            return False
        if not download_file(weights_url, self.weights_path):
            return False
        
        self.model_size_mb = get_file_size_mb(self.weights_path)
        
        try:
            self.net = cv2.dnn.readNetFromDarknet(self.cfg_path, self.weights_path)
            self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
            self.layer_names = self.net.getUnconnectedOutLayersNames()
            return True
        except Exception as e:
            print(f"  ❌ Error cargando YOLO-Fastest: {e}")
            return False
    
    def set_input_size(self, size):
        self.input_size = size
    
    def detect(self, frame) -> int:
        blob = cv2.dnn.blobFromImage(frame, 1/255.0, self.input_size, swapRB=True, crop=False)
        self.net.setInput(blob)
        outputs = self.net.forward(self.layer_names)
        
        detections = 0
        for output in outputs:
            for detection in output:
                scores = detection[5:]
                if np.max(scores) > 0.5:
                    detections += 1
        return detections

# ============================================================================
# BENCHMARK ENGINE
# ============================================================================

def run_benchmark(detector: BaseDetector, video_path: str, resolution: str, 
                  input_size: Tuple[int, int], use_jpeg_compression: bool = False) -> Optional[BenchmarkResult]:
    """Ejecuta benchmark para un detector con configuración específica"""
    
    detector.set_input_size(input_size)
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"  ❌ No se puede abrir video")
        return None
    
    times = []
    total_detections = 0
    frame_count = 0
    
    while frame_count < NUM_FRAMES:
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue
        
        # Redimensionar a resolución objetivo
        frame = resize_frame(frame, input_size)
        
        # Opcionalmente comprimir con JPEG
        if use_jpeg_compression:
            frame = compress_frame_jpeg(frame, quality=70)
        
        # Medir tiempo de inferencia
        start = time.perf_counter()
        detections = detector.detect(frame)
        end = time.perf_counter()
        
        times.append(end - start)
        total_detections += detections
        frame_count += 1
    
    cap.release()
    
    avg_time = np.mean(times)
    avg_fps = 1.0 / avg_time if avg_time > 0 else 0
    
    return BenchmarkResult(
        model_name=detector.name,
        resolution=resolution,
        input_size=input_size,
        avg_fps=round(avg_fps, 2),
        avg_time_ms=round(avg_time * 1000, 1),
        total_detections=total_detections,
        model_size_mb=round(detector.model_size_mb, 2)
    )

def print_results_table(results: List[BenchmarkResult]):
    """Imprime tabla de resultados"""
    print("\n" + "="*100)
    print("📊 RESULTADOS DEL BENCHMARK")
    print("="*100)
    print(f"{'Modelo':<30} {'Resolución':<10} {'FPS':<8} {'ms/frame':<10} {'Detecciones':<12} {'Tamaño MB':<10}")
    print("-"*100)
    
    # Ordenar por FPS descendente
    results_sorted = sorted(results, key=lambda x: x.avg_fps, reverse=True)
    
    for r in results_sorted:
        fps_indicator = "⚡" if r.avg_fps >= 10 else "✅" if r.avg_fps >= 5 else "⚠️" if r.avg_fps >= 2 else "🐢"
        print(f"{r.model_name:<30} {r.resolution:<10} {fps_indicator} {r.avg_fps:<6} {r.avg_time_ms:<10} {r.total_detections:<12} {r.model_size_mb:<10}")
    
    print("="*100)
    print("\nLeyenda: ⚡ >10 FPS (excelente) | ✅ 5-10 FPS (bueno) | ⚠️ 2-5 FPS (aceptable) | 🐢 <2 FPS (lento)")

def main():
    print("🔬 BENCHMARK COMPLETO DE MODELOS DE DETECCIÓN")
    print("=" * 60)
    print(f"Frames por modelo: {NUM_FRAMES}")
    print(f"Resoluciones: {list(RESOLUTIONS.keys())}")
    print()
    
    # Descargar video
    video_path = download_video()
    
    # Lista de detectores a probar
    detectors = [
        YOLOv4TinyDetector(),
        NanoDetDetector(),
        MobileNetSSDDetector(),
        YOLOFastestDetector(),
        MediaPipePoseDetector(),
        MediaPipeObjectDetector(),
        EfficientDetLiteDetector(),
        YOLONASDetector(),
        # YOLOv8OpenVINODetector(),  # Descomentar si tienes OpenVINO instalado
    ]
    
    all_results = []
    
    for detector in detectors:
        print(f"\n{'='*60}")
        print(f"🧪 Probando: {detector.name}")
        print("="*60)
        
        if not detector.load():
            print(f"  ⏭️ Saltando {detector.name} (no se pudo cargar)")
            continue
        
        print(f"  ✅ Modelo cargado ({detector.model_size_mb:.1f} MB)")
        
        # Check if model has fixed input size
        has_fixed_input = getattr(detector, 'fixed_input', False)
        
        if has_fixed_input:
            # Run only once for fixed input models
            print(f"\n  📐 Tamaño fijo de entrada (solo una prueba)")
            result = run_benchmark(
                detector=detector,
                video_path=video_path,
                resolution="FIXED",
                input_size=(640, 640),  # Will be ignored
                use_jpeg_compression=False
            )
            if result:
                all_results.append(result)
                print(f"     → {result.avg_fps} FPS | {result.avg_time_ms}ms | {result.total_detections} detecciones")
        else:
            # Probar cada resolución
            for res_name, res_size in RESOLUTIONS.items():
                print(f"\n  📐 Resolución: {res_name} ({res_size[0]}x{res_size[1]})")
                
                result = run_benchmark(
                    detector=detector,
                    video_path=video_path,
                    resolution=res_name,
                    input_size=res_size,
                    use_jpeg_compression=False
                )
                
                if result:
                    all_results.append(result)
                    print(f"     → {result.avg_fps} FPS | {result.avg_time_ms}ms | {result.total_detections} detecciones")
    
    # Mostrar resultados
    if all_results:
        print_results_table(all_results)
        
        # Guardar resultados JSON
        results_json = [
            {
                "model": r.model_name,
                "resolution": r.resolution,
                "input_size": f"{r.input_size[0]}x{r.input_size[1]}",
                "fps": r.avg_fps,
                "ms_per_frame": r.avg_time_ms,
                "detections": r.total_detections,
                "size_mb": r.model_size_mb
            }
            for r in all_results
        ]
        
        with open(RESULTS_FILE, 'w') as f:
            json.dump(results_json, f, indent=2)
        print(f"\n💾 Resultados guardados en: {RESULTS_FILE}")
        
        # Recomendación
        print("\n" + "="*60)
        print("🏆 RECOMENDACIÓN")
        print("="*60)
        best = max(all_results, key=lambda x: x.avg_fps)
        print(f"Modelo más rápido: {best.model_name}")
        print(f"  - Resolución: {best.resolution}")
        print(f"  - FPS: {best.avg_fps}")
        print(f"  - Tamaño: {best.model_size_mb} MB")
        
        # Mejor balance velocidad/detecciones
        efficient = max([r for r in all_results if r.avg_fps >= 5], 
                       key=lambda x: x.total_detections, default=None)
        if efficient and efficient != best:
            print(f"\nMejor balance (FPS≥5 + detecciones): {efficient.model_name}")
            print(f"  - Resolución: {efficient.resolution}")
            print(f"  - FPS: {efficient.avg_fps}")
            print(f"  - Detecciones: {efficient.total_detections}")

if __name__ == "__main__":
    main()
