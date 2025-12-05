#!/usr/bin/env python3
"""
Benchmark script to compare detection models performance.
Tests ONNX, RT-DETR, and Ultralytics on the same frames.
"""

import os
import sys
import time
import cv2
import numpy as np
import subprocess
from datetime import datetime

sys.path.insert(0, '/app')

def download_youtube_video(url: str, duration_sec: int = 10):
    """Download video from YouTube to temp file."""
    print(f"\n📥 Descargando {duration_sec}s de video de YouTube...")
    temp_path = "/tmp/benchmark_video.mp4"
    
    try:
        cmd = [
            'yt-dlp', '-f', 'worst[ext=mp4]/worst',
            '--download-sections', f'*0:00-0:{duration_sec:02d}',
            '-o', temp_path, '--force-overwrites', '--no-playlist', url
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
            print(f"✅ Video descargado: {os.path.getsize(temp_path) / 1024:.1f} KB")
            return temp_path
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def extract_frames(video_path: str, max_frames: int = 300):
    """Extract frames from video file."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None
    
    frames = []
    while len(frames) < max_frames:
        ret, frame = cap.read()
        if not ret:
            break
        frame = cv2.resize(frame, (640, 480))
        frames.append(frame)
    
    cap.release()
    print(f"✅ Frames extraídos: {len(frames)}")
    return frames

def generate_synthetic_frames(n=300):
    """Generate synthetic frames for testing."""
    print("🎨 Generando frames sintéticos...")
    frames = []
    for i in range(n):
        frame = np.random.randint(50, 200, (480, 640, 3), dtype=np.uint8)
        for _ in range(np.random.randint(1, 5)):
            x, y = np.random.randint(50, 500), np.random.randint(50, 400)
            w, h = np.random.randint(30, 100), np.random.randint(30, 100)
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), -1)
        frames.append(frame)
    return frames

def benchmark_onnx(frames, warmup=5):
    print("\n" + "="*60)
    print("🔥 BENCHMARK: ONNX YOLO-NAS")
    print("="*60)
    
    try:
        from src.models.onnx_yolonas import ONNXYOLONASDetector
        model_path = "/app/models/yolo_nas_s.onnx"
        
        if not os.path.exists(model_path):
            print(f"❌ Modelo no encontrado")
            return None
        
        print(f"📦 Tamaño: {os.path.getsize(model_path)/1024/1024:.1f} MB")
        start = time.time()
        detector = ONNXYOLONASDetector(model_path)
        load_time = time.time() - start
        print(f"✅ Cargado en {load_time:.2f}s")
        
        # Warmup
        for i in range(warmup):
            detector.detect(frames[i], confidence_threshold=0.5)
        
        print(f"⏱️ Benchmark ({len(frames)} frames)...")
        times, total_det = [], 0
        for i, frame in enumerate(frames):
            start = time.time()
            detections, _ = detector.detect(frame, confidence_threshold=0.5)
            times.append(time.time() - start)
            total_det += len(detections)
            if (i+1) % 100 == 0:
                print(f"  {i+1}/{len(frames)} - FPS: {1.0/np.mean(times[-100:]):.1f}")
        
        return {'model': 'ONNX YOLO-NAS', 'load_time': load_time, 'times': times, 'total_detections': total_det}
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

def benchmark_rtdetr(frames, warmup=5):
    print("\n" + "="*60)
    print("🔥 BENCHMARK: RT-DETR")
    print("="*60)
    
    try:
        from src.models.rt_detr import RTDETRDetector
        
        start = time.time()
        detector = RTDETRDetector()
        load_time = time.time() - start
        print(f"✅ Cargado en {load_time:.2f}s")
        
        # Warmup
        for i in range(warmup):
            detector.detect(frames[i], confidence_threshold=0.5)
        
        print(f"⏱️ Benchmark ({len(frames)} frames)...")
        times, total_det = [], 0
        for i, frame in enumerate(frames):
            start = time.time()
            detections, _ = detector.detect(frame, confidence_threshold=0.5)
            times.append(time.time() - start)
            total_det += len(detections)
            if (i+1) % 100 == 0:
                print(f"  {i+1}/{len(frames)} - FPS: {1.0/np.mean(times[-100:]):.1f}")
        
        return {'model': 'RT-DETR', 'load_time': load_time, 'times': times, 'total_detections': total_det}
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

def benchmark_ultralytics(frames, warmup=5):
    print("\n" + "="*60)
    print("🔥 BENCHMARK: Ultralytics YOLOv8n")
    print("="*60)
    
    try:
        from ultralytics import YOLO
        model_path = "/app/yolov8n.pt"
        
        if not os.path.exists(model_path):
            print(f"❌ Modelo no encontrado: {model_path}")
            return None
        
        print(f"📦 Tamaño: {os.path.getsize(model_path)/1024/1024:.1f} MB")
        start = time.time()
        model = YOLO(model_path)
        load_time = time.time() - start
        print(f"✅ Cargado en {load_time:.2f}s")
        
        # Warmup
        for i in range(warmup):
            model(frames[i], verbose=False)
        
        print(f"⏱️ Benchmark ({len(frames)} frames)...")
        times, total_det = [], 0
        for i, frame in enumerate(frames):
            start = time.time()
            results = model(frame, verbose=False, conf=0.5)
            times.append(time.time() - start)
            total_det += len(results[0].boxes) if results and results[0].boxes is not None else 0
            if (i+1) % 100 == 0:
                print(f"  {i+1}/{len(frames)} - FPS: {1.0/np.mean(times[-100:]):.1f}")
        
        return {'model': 'Ultralytics YOLOv8n', 'load_time': load_time, 'times': times, 'total_detections': total_det}
    except ImportError:
        print("❌ Ultralytics no instalado")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def benchmark_mediapipe(frames, warmup=5):
    """MediaPipe Object Detection - optimizado para CPU"""
    print("\n" + "="*60)
    print("🔥 BENCHMARK: MediaPipe Object Detection")
    print("="*60)
    
    try:
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
        
        # Descargar modelo si no existe
        model_path = "/tmp/efficientdet_lite0.tflite"
        if not os.path.exists(model_path):
            print("📥 Descargando modelo EfficientDet-Lite0...")
            import urllib.request
            url = "https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/int8/1/efficientdet_lite0.tflite"
            urllib.request.urlretrieve(url, model_path)
        
        print(f"📦 Tamaño: {os.path.getsize(model_path)/1024/1024:.1f} MB")
        
        start = time.time()
        base_options = python.BaseOptions(model_asset_path=model_path)
        options = vision.ObjectDetectorOptions(
            base_options=base_options,
            score_threshold=0.5,
            max_results=20
        )
        detector = vision.ObjectDetector.create_from_options(options)
        load_time = time.time() - start
        print(f"✅ Cargado en {load_time:.2f}s")
        
        # Warmup
        for i in range(warmup):
            rgb = cv2.cvtColor(frames[i], cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            detector.detect(mp_image)
        
        print(f"⏱️ Benchmark ({len(frames)} frames)...")
        times, total_det = [], 0
        for i, frame in enumerate(frames):
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            
            start = time.time()
            result = detector.detect(mp_image)
            times.append(time.time() - start)
            total_det += len(result.detections)
            if (i+1) % 100 == 0:
                print(f"  {i+1}/{len(frames)} - FPS: {1.0/np.mean(times[-100:]):.1f}")
        
        detector.close()
        return {'model': 'MediaPipe EfficientDet', 'load_time': load_time, 'times': times, 'total_detections': total_det}
    except ImportError:
        print("❌ MediaPipe no instalado (pip install mediapipe)")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def benchmark_yolonas_native(frames, warmup=5):
    """YOLO-NAS nativo con super_gradients"""
    print("\n" + "="*60)
    print("🔥 BENCHMARK: YOLO-NAS Nativo (super_gradients)")
    print("="*60)
    
    try:
        from super_gradients.training import models
        import torch
        
        start = time.time()
        model = models.get("yolo_nas_s", pretrained_weights="coco")
        model.eval()
        # Forzar CPU
        model = model.to('cpu')
        load_time = time.time() - start
        print(f"✅ Cargado en {load_time:.2f}s")
        
        # Warmup
        for i in range(warmup):
            with torch.no_grad():
                model.predict(frames[i], conf=0.5)
        
        print(f"⏱️ Benchmark ({len(frames)} frames)...")
        times, total_det = [], 0
        for i, frame in enumerate(frames):
            start = time.time()
            with torch.no_grad():
                preds = model.predict(frame, conf=0.5)
            times.append(time.time() - start)
            # Contar detecciones
            if hasattr(preds, 'prediction'):
                total_det += len(preds.prediction.bboxes_xyxy)
            if (i+1) % 100 == 0:
                print(f"  {i+1}/{len(frames)} - FPS: {1.0/np.mean(times[-100:]):.1f}")
        
        return {'model': 'YOLO-NAS Native', 'load_time': load_time, 'times': times, 'total_detections': total_det}
    except ImportError:
        print("❌ super_gradients no instalado")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def benchmark_opencv_dnn_mobilenet(frames, warmup=5):
    """MobileNet-SSD con OpenCV DNN - muy rápido en CPU"""
    print("\n" + "="*60)
    print("🔥 BENCHMARK: OpenCV DNN MobileNet-SSD")
    print("="*60)
    
    try:
        # Descargar modelo si no existe
        model_path = "/tmp/mobilenet_ssd.caffemodel"
        config_path = "/tmp/mobilenet_ssd.prototxt"
        
        if not os.path.exists(model_path):
            print("📥 Descargando MobileNet-SSD...")
            import urllib.request
            # MobileNet-SSD v2
            urllib.request.urlretrieve(
                "https://raw.githubusercontent.com/chuanqi305/MobileNet-SSD/master/MobileNetSSD_deploy.caffemodel",
                model_path
            )
            urllib.request.urlretrieve(
                "https://raw.githubusercontent.com/chuanqi305/MobileNet-SSD/master/MobileNetSSD_deploy.prototxt",
                config_path
            )
        
        print(f"📦 Tamaño: {os.path.getsize(model_path)/1024/1024:.1f} MB")
        
        start = time.time()
        net = cv2.dnn.readNetFromCaffe(config_path, model_path)
        net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        load_time = time.time() - start
        print(f"✅ Cargado en {load_time:.2f}s")
        
        # Warmup
        for i in range(warmup):
            blob = cv2.dnn.blobFromImage(frames[i], 0.007843, (300, 300), 127.5)
            net.setInput(blob)
            net.forward()
        
        print(f"⏱️ Benchmark ({len(frames)} frames)...")
        times, total_det = [], 0
        for i, frame in enumerate(frames):
            blob = cv2.dnn.blobFromImage(frame, 0.007843, (300, 300), 127.5)
            net.setInput(blob)
            
            start = time.time()
            detections = net.forward()
            times.append(time.time() - start)
            
            # Contar detecciones con confianza > 0.5
            for j in range(detections.shape[2]):
                confidence = detections[0, 0, j, 2]
                if confidence > 0.5:
                    total_det += 1
            
            if (i+1) % 100 == 0:
                print(f"  {i+1}/{len(frames)} - FPS: {1.0/np.mean(times[-100:]):.1f}")
        
        return {'model': 'OpenCV MobileNet-SSD', 'load_time': load_time, 'times': times, 'total_detections': total_det}
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def benchmark_opencv_dnn_yolov4_tiny(frames, warmup=5):
    """YOLOv4-tiny con OpenCV DNN - buen balance velocidad/precisión"""
    print("\n" + "="*60)
    print("🔥 BENCHMARK: OpenCV DNN YOLOv4-tiny")
    print("="*60)
    
    try:
        # Descargar modelo si no existe
        weights_path = "/tmp/yolov4-tiny.weights"
        config_path = "/tmp/yolov4-tiny.cfg"
        
        if not os.path.exists(weights_path):
            print("📥 Descargando YOLOv4-tiny...")
            import urllib.request
            urllib.request.urlretrieve(
                "https://github.com/AlexeyAB/darknet/releases/download/darknet_yolo_v4_pre/yolov4-tiny.weights",
                weights_path
            )
            urllib.request.urlretrieve(
                "https://raw.githubusercontent.com/AlexeyAB/darknet/master/cfg/yolov4-tiny.cfg",
                config_path
            )
        
        print(f"📦 Tamaño: {os.path.getsize(weights_path)/1024/1024:.1f} MB")
        
        start = time.time()
        net = cv2.dnn.readNetFromDarknet(config_path, weights_path)
        net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        layer_names = net.getLayerNames()
        output_layers = [layer_names[i - 1] for i in net.getUnconnectedOutLayers()]
        load_time = time.time() - start
        print(f"✅ Cargado en {load_time:.2f}s")
        
        # Warmup
        for i in range(warmup):
            blob = cv2.dnn.blobFromImage(frames[i], 1/255.0, (416, 416), swapRB=True, crop=False)
            net.setInput(blob)
            net.forward(output_layers)
        
        print(f"⏱️ Benchmark ({len(frames)} frames)...")
        times, total_det = [], 0
        for i, frame in enumerate(frames):
            blob = cv2.dnn.blobFromImage(frame, 1/255.0, (416, 416), swapRB=True, crop=False)
            net.setInput(blob)
            
            start = time.time()
            outputs = net.forward(output_layers)
            times.append(time.time() - start)
            
            # Contar detecciones
            for out in outputs:
                for detection in out:
                    scores = detection[5:]
                    if np.max(scores) > 0.5:
                        total_det += 1
            
            if (i+1) % 100 == 0:
                print(f"  {i+1}/{len(frames)} - FPS: {1.0/np.mean(times[-100:]):.1f}")
        
        return {'model': 'OpenCV YOLOv4-tiny', 'load_time': load_time, 'times': times, 'total_detections': total_det}
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def benchmark_yolov8n_onnx(frames, warmup=5):
    """YOLOv8n exportado a ONNX - alternativa ligera"""
    print("\n" + "="*60)
    print("🔥 BENCHMARK: YOLOv8n ONNX")
    print("="*60)
    
    try:
        import onnxruntime as ort
        
        # Verificar si existe el modelo ONNX
        model_path = "/tmp/yolov8n.onnx"
        
        if not os.path.exists(model_path):
            print("📥 Exportando YOLOv8n a ONNX...")
            try:
                from ultralytics import YOLO
                model = YOLO("/app/yolov8n.pt")
                model.export(format="onnx", imgsz=640, simplify=True)
                import shutil
                shutil.move("/app/yolov8n.onnx", model_path)
            except:
                print("❌ No se pudo exportar YOLOv8n a ONNX")
                return None
        
        print(f"📦 Tamaño: {os.path.getsize(model_path)/1024/1024:.1f} MB")
        
        start = time.time()
        session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
        input_name = session.get_inputs()[0].name
        load_time = time.time() - start
        print(f"✅ Cargado en {load_time:.2f}s")
        
        def preprocess(frame):
            img = cv2.resize(frame, (640, 640))
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img = img.astype(np.float32) / 255.0
            img = np.transpose(img, (2, 0, 1))
            img = np.expand_dims(img, axis=0)
            return img
        
        # Warmup
        for i in range(warmup):
            img = preprocess(frames[i])
            session.run(None, {input_name: img})
        
        print(f"⏱️ Benchmark ({len(frames)} frames)...")
        times, total_det = [], 0
        for i, frame in enumerate(frames):
            img = preprocess(frame)
            
            start = time.time()
            outputs = session.run(None, {input_name: img})
            times.append(time.time() - start)
            
            # Contar detecciones (output shape: [1, 84, 8400] for YOLOv8)
            if len(outputs) > 0 and outputs[0] is not None:
                output = outputs[0]
                if len(output.shape) == 3:
                    # Transpose to [1, 8400, 84]
                    output = np.transpose(output, (0, 2, 1))
                    # Get confidence scores (max of class scores)
                    scores = np.max(output[0, :, 4:], axis=1)
                    total_det += np.sum(scores > 0.5)
            
            if (i+1) % 100 == 0:
                print(f"  {i+1}/{len(frames)} - FPS: {1.0/np.mean(times[-100:]):.1f}")
        
        return {'model': 'YOLOv8n ONNX', 'load_time': load_time, 'times': times, 'total_detections': total_det}
    except ImportError:
        print("❌ onnxruntime no instalado")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def benchmark_nanodet(frames, warmup=5):
    """NanoDet - modelo ultra-ligero para CPU"""
    print("\n" + "="*60)
    print("🔥 BENCHMARK: NanoDet-Plus ONNX")
    print("="*60)
    
    try:
        import onnxruntime as ort
        
        model_path = "/tmp/nanodet-plus-m_416.onnx"
        
        if not os.path.exists(model_path):
            print("📥 Descargando NanoDet-Plus...")
            import urllib.request
            # NanoDet-Plus-m 416
            url = "https://github.com/RangiLyu/nanodet/releases/download/v1.0.0-alpha-1/nanodet-plus-m_416.onnx"
            urllib.request.urlretrieve(url, model_path)
        
        print(f"📦 Tamaño: {os.path.getsize(model_path)/1024/1024:.1f} MB")
        
        start = time.time()
        session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
        input_name = session.get_inputs()[0].name
        input_shape = session.get_inputs()[0].shape
        load_time = time.time() - start
        print(f"✅ Cargado en {load_time:.2f}s")
        print(f"   Input shape: {input_shape}")
        
        def preprocess(frame, target_size=416):
            img = cv2.resize(frame, (target_size, target_size))
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img = img.astype(np.float32)
            # Normalize
            mean = np.array([103.53, 116.28, 123.675], dtype=np.float32)
            std = np.array([57.375, 57.12, 58.395], dtype=np.float32)
            img = (img - mean) / std
            img = np.transpose(img, (2, 0, 1))
            img = np.expand_dims(img, axis=0)
            return img
        
        # Warmup
        for i in range(warmup):
            img = preprocess(frames[i])
            session.run(None, {input_name: img})
        
        print(f"⏱️ Benchmark ({len(frames)} frames)...")
        times, total_det = [], 0
        for i, frame in enumerate(frames):
            img = preprocess(frame)
            
            start = time.time()
            outputs = session.run(None, {input_name: img})
            times.append(time.time() - start)
            
            # Estimación de detecciones
            if len(outputs) > 0:
                # NanoDet output varies, just count high confidence
                for out in outputs:
                    if out is not None and len(out.shape) >= 2:
                        total_det += np.sum(out > 0.5)
            
            if (i+1) % 100 == 0:
                print(f"  {i+1}/{len(frames)} - FPS: {1.0/np.mean(times[-100:]):.1f}")
        
        return {'model': 'NanoDet-Plus', 'load_time': load_time, 'times': times, 'total_detections': total_det}
    except ImportError:
        print("❌ onnxruntime no instalado")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

def print_results(results):
    print("\n" + "="*70)
    print("📊 RESULTADOS DEL BENCHMARK")
    print("="*70)
    
    valid_results = [r for r in results if r is not None]
    
    if not valid_results:
        print("❌ No hay resultados válidos")
        return
    
    # Header
    print(f"\n{'Modelo':<25} {'Load(s)':<10} {'FPS Avg':<10} {'FPS Min':<10} {'FPS Max':<10} {'ms/frame':<10} {'Detects':<10}")
    print("-" * 85)
    
    for r in valid_results:
        times = r['times']
        avg_fps = len(times) / sum(times)
        min_fps = 1.0 / max(times)
        max_fps = 1.0 / min(times)
        avg_ms = np.mean(times) * 1000
        
        print(f"{r['model']:<25} {r['load_time']:<10.2f} {avg_fps:<10.1f} {min_fps:<10.1f} {max_fps:<10.1f} {avg_ms:<10.1f} {r['total_detections']:<10}")
    
    # Winner
    best = max(valid_results, key=lambda x: len(x['times']) / sum(x['times']))
    print(f"\n🏆 GANADOR: {best['model']} con {len(best['times']) / sum(best['times']):.1f} FPS promedio")
    
    # Speed comparison
    if len(valid_results) > 1:
        print("\n📈 COMPARACIÓN DE VELOCIDAD:")
        best_fps = len(best['times']) / sum(best['times'])
        for r in valid_results:
            if r != best:
                other_fps = len(r['times']) / sum(r['times'])
                ratio = best_fps / other_fps
                print(f"   {best['model']} es {ratio:.2f}x más rápido que {r['model']}")

def main():
    print("="*70)
    print(f"🎬 BENCHMARK DE MODELOS DE DETECCIÓN")
    print(f"   {datetime.now()}")
    print("="*70)
    
    # Try YouTube video first
    youtube_url = "https://www.youtube.com/watch?v=MNn9qKG2UFI"
    video_path = download_youtube_video(youtube_url, 10)
    
    frames = None
    if video_path:
        frames = extract_frames(video_path, 300)
    
    if not frames:
        print("⚠️ No se pudo descargar video, usando frames sintéticos")
        frames = generate_synthetic_frames(300)
    
    print(f"\n📦 Frames: {len(frames)}, Size: {frames[0].shape}")
    
    results = []
    
    # Run benchmarks - ordenados de más ligero a más pesado
    print("\n" + "🚀"*30)
    print("   INICIANDO BENCHMARKS - Esto puede tomar varios minutos...")
    print("🚀"*30)
    
    # Modelos ligeros para CPU primero
    results.append(benchmark_opencv_dnn_mobilenet(frames))
    results.append(benchmark_opencv_dnn_yolov4_tiny(frames))
    results.append(benchmark_mediapipe(frames))
    results.append(benchmark_nanodet(frames))
    
    # ONNX models
    results.append(benchmark_onnx(frames))
    # results.append(benchmark_yolov8n_onnx(frames))  # Requiere ultralytics para exportar
    
    # Modelos más pesados - comentados por lentitud
    # results.append(benchmark_yolonas_native(frames))  # Requiere super_gradients
    # results.append(benchmark_rtdetr(frames))  # ~0.3 FPS, muy lento
    # results.append(benchmark_ultralytics(frames))  # No instalado
    
    # Print results
    print_results(results)
    
    print("\n✅ Benchmark completado!")
    
    # Cleanup
    if video_path and os.path.exists(video_path):
        os.remove(video_path)

if __name__ == "__main__":
    main()
