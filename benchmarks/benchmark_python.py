#!/usr/bin/env python3
"""
Benchmark de Python para procesamiento de video/imágenes
Mide: decodificación, resize, conversión de color, inferencia simulada
"""
import time
import numpy as np
import cv2
import json
import sys
from statistics import mean, stdev

# Configuración
ITERATIONS = 100
WARMUP = 10
IMAGE_SIZE = (1920, 1080)  # Full HD
TARGET_SIZE = (640, 640)   # YOLO input size

def generate_test_image():
    """Genera una imagen de prueba"""
    return np.random.randint(0, 255, (*IMAGE_SIZE, 3), dtype=np.uint8)

def benchmark_decode_encode():
    """Benchmark: encode/decode JPEG"""
    img = generate_test_image()
    
    # Warmup
    for _ in range(WARMUP):
        _, encoded = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    
    # Benchmark encode
    times_encode = []
    for _ in range(ITERATIONS):
        start = time.perf_counter()
        _, encoded = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        times_encode.append((time.perf_counter() - start) * 1000)
    
    # Benchmark decode
    times_decode = []
    for _ in range(ITERATIONS):
        start = time.perf_counter()
        cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        times_decode.append((time.perf_counter() - start) * 1000)
    
    return {
        "encode_ms": {"mean": mean(times_encode), "std": stdev(times_encode), "min": min(times_encode), "max": max(times_encode)},
        "decode_ms": {"mean": mean(times_decode), "std": stdev(times_decode), "min": min(times_decode), "max": max(times_decode)}
    }

def benchmark_resize():
    """Benchmark: resize de imagen"""
    img = generate_test_image()
    
    # Warmup
    for _ in range(WARMUP):
        cv2.resize(img, TARGET_SIZE, interpolation=cv2.INTER_LINEAR)
    
    times = []
    for _ in range(ITERATIONS):
        start = time.perf_counter()
        cv2.resize(img, TARGET_SIZE, interpolation=cv2.INTER_LINEAR)
        times.append((time.perf_counter() - start) * 1000)
    
    return {"mean": mean(times), "std": stdev(times), "min": min(times), "max": max(times)}

def benchmark_color_conversion():
    """Benchmark: conversión BGR -> RGB"""
    img = generate_test_image()
    
    # Warmup
    for _ in range(WARMUP):
        cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    
    times = []
    for _ in range(ITERATIONS):
        start = time.perf_counter()
        cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        times.append((time.perf_counter() - start) * 1000)
    
    return {"mean": mean(times), "std": stdev(times), "min": min(times), "max": max(times)}

def benchmark_preprocessing():
    """Benchmark: pipeline completo de preprocessing para YOLO"""
    img = generate_test_image()
    
    # Warmup
    for _ in range(WARMUP):
        resized = cv2.resize(img, TARGET_SIZE, interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        normalized = rgb.astype(np.float32) / 255.0
        batched = np.expand_dims(normalized.transpose(2, 0, 1), 0)
    
    times = []
    for _ in range(ITERATIONS):
        start = time.perf_counter()
        resized = cv2.resize(img, TARGET_SIZE, interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        normalized = rgb.astype(np.float32) / 255.0
        batched = np.expand_dims(normalized.transpose(2, 0, 1), 0)
        times.append((time.perf_counter() - start) * 1000)
    
    return {"mean": mean(times), "std": stdev(times), "min": min(times), "max": max(times)}

def benchmark_nms_simulation():
    """Benchmark: simulación de NMS (Non-Maximum Suppression)"""
    # Simular 1000 detecciones
    num_boxes = 1000
    boxes = np.random.rand(num_boxes, 4).astype(np.float32) * 640
    scores = np.random.rand(num_boxes).astype(np.float32)
    
    # Warmup
    for _ in range(WARMUP):
        indices = cv2.dnn.NMSBoxes(boxes.tolist(), scores.tolist(), 0.25, 0.45)
    
    times = []
    for _ in range(ITERATIONS):
        start = time.perf_counter()
        indices = cv2.dnn.NMSBoxes(boxes.tolist(), scores.tolist(), 0.25, 0.45)
        times.append((time.perf_counter() - start) * 1000)
    
    return {"mean": mean(times), "std": stdev(times), "min": min(times), "max": max(times)}

def benchmark_matrix_ops():
    """Benchmark: operaciones matriciales típicas de ML"""
    # Simular operación de feature map
    feature_map = np.random.rand(1, 256, 80, 80).astype(np.float32)
    weights = np.random.rand(256, 256).astype(np.float32)
    
    # Warmup
    for _ in range(WARMUP):
        reshaped = feature_map.reshape(256, -1)
        result = np.matmul(weights, reshaped)
    
    times = []
    for _ in range(ITERATIONS):
        start = time.perf_counter()
        reshaped = feature_map.reshape(256, -1)
        result = np.matmul(weights, reshaped)
        times.append((time.perf_counter() - start) * 1000)
    
    return {"mean": mean(times), "std": stdev(times), "min": min(times), "max": max(times)}

def benchmark_json_serialization():
    """Benchmark: serialización JSON de detecciones"""
    detections = [
        {"class": "person", "confidence": 0.95, "bbox": [100, 200, 300, 400], "track_id": i}
        for i in range(50)
    ]
    
    # Warmup
    for _ in range(WARMUP):
        json.dumps(detections)
    
    times = []
    for _ in range(ITERATIONS):
        start = time.perf_counter()
        json.dumps(detections)
        times.append((time.perf_counter() - start) * 1000)
    
    return {"mean": mean(times), "std": stdev(times), "min": min(times), "max": max(times)}

def main():
    print("=" * 60, file=sys.stderr)
    print("BENCHMARK PYTHON - Video Analytics", file=sys.stderr)
    print(f"Iterations: {ITERATIONS}, Warmup: {WARMUP}", file=sys.stderr)
    print(f"Image size: {IMAGE_SIZE} -> {TARGET_SIZE}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    
    results = {
        "language": "Python",
        "iterations": ITERATIONS,
        "image_size": IMAGE_SIZE,
        "target_size": TARGET_SIZE,
        "benchmarks": {}
    }
    
    print("\n[1/7] JPEG Encode/Decode...", file=sys.stderr)
    results["benchmarks"]["jpeg_codec"] = benchmark_decode_encode()
    
    print("[2/7] Resize...", file=sys.stderr)
    results["benchmarks"]["resize"] = benchmark_resize()
    
    print("[3/7] Color Conversion...", file=sys.stderr)
    results["benchmarks"]["color_conversion"] = benchmark_color_conversion()
    
    print("[4/7] Full Preprocessing Pipeline...", file=sys.stderr)
    results["benchmarks"]["preprocessing"] = benchmark_preprocessing()
    
    print("[5/7] NMS Simulation...", file=sys.stderr)
    results["benchmarks"]["nms"] = benchmark_nms_simulation()
    
    print("[6/7] Matrix Operations...", file=sys.stderr)
    results["benchmarks"]["matrix_ops"] = benchmark_matrix_ops()
    
    print("[7/7] JSON Serialization...", file=sys.stderr)
    results["benchmarks"]["json_serialization"] = benchmark_json_serialization()
    
    print("\n✅ Benchmark completado!", file=sys.stderr)
    
    # Output JSON to stdout
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()
