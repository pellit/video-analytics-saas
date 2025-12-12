#!/usr/bin/env python3
"""
Benchmark ONNX Inference con modelos reales
Testea YOLOv8n y YOLO-NAS con ONNX Runtime
"""

import time
import numpy as np
import sys
import json
import os

ITERATIONS = 100
WARMUP = 10

results = {
    "language": "Python",
    "runtime": "onnxruntime",
    "iterations": ITERATIONS,
    "models": {}
}

try:
    import onnxruntime as ort
    import cv2
    
    print("="*70, file=sys.stderr)
    print("🔬 BENCHMARK ONNX INFERENCE - Python", file=sys.stderr)
    print("="*70, file=sys.stderr)
    print(f"ONNX Runtime: {ort.__version__}", file=sys.stderr)
    print(f"Providers: {ort.get_available_providers()}", file=sys.stderr)
    
    # Configurar sesión optimizada
    sess_options = ort.SessionOptions()
    sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    sess_options.intra_op_num_threads = 4
    sess_options.inter_op_num_threads = 1
    
    # Lista de modelos a testear
    models_to_test = [
        {
            "name": "YOLOv8n",
            "path": "/app/models/yolov8n.onnx",
            "input_type": "float32",
            "input_shape": (1, 3, 640, 640),
        },
        {
            "name": "YOLO-NAS-S", 
            "path": "/app/models/yolo_nas_s.onnx",
            "input_type": "uint8",
            "input_shape": (1, 3, 640, 640),
        },
        {
            "name": "YuNet-Face",
            "path": "/app/models/face_detection_yunet_2023mar.onnx",
            "input_type": "float32",
            "input_shape": (1, 3, 320, 320),
        }
    ]
    
    # Generar imagen de prueba
    test_frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    
    for model_info in models_to_test:
        model_name = model_info["name"]
        model_path = model_info["path"]
        
        if not os.path.exists(model_path):
            print(f"\n⚠️ {model_name}: No encontrado en {model_path}", file=sys.stderr)
            continue
            
        print(f"\n{'='*70}", file=sys.stderr)
        print(f"📦 {model_name}", file=sys.stderr)
        print(f"   Path: {model_path}", file=sys.stderr)
        print(f"   Size: {os.path.getsize(model_path)/1024/1024:.1f} MB", file=sys.stderr)
        
        try:
            # Cargar modelo
            start = time.time()
            session = ort.InferenceSession(
                model_path, 
                sess_options, 
                providers=["CPUExecutionProvider"]
            )
            load_time = time.time() - start
            
            input_info = session.get_inputs()[0]
            output_info = session.get_outputs()[0]
            print(f"   Input: {input_info.name} - {input_info.shape} - {input_info.type}", file=sys.stderr)
            print(f"   Output: {output_info.name} - {output_info.shape}", file=sys.stderr)
            print(f"   Load time: {load_time:.3f}s", file=sys.stderr)
            
            # Preparar input según el tipo del modelo
            input_shape = model_info["input_shape"]
            h, w = input_shape[2], input_shape[3]
            
            # Preprocesar frame
            resized = cv2.resize(test_frame, (w, h))
            
            if model_info["input_type"] == "float32":
                # CHW format, float32, normalized [0,1]
                input_data = resized.transpose(2, 0, 1).astype(np.float32) / 255.0
                input_data = input_data[np.newaxis, ...]
            else:
                # uint8 format para YOLO-NAS
                input_data = resized.transpose(2, 0, 1).astype(np.uint8)
                input_data = input_data[np.newaxis, ...]
            
            input_name = input_info.name
            
            # Warmup
            print(f"   ⏳ Warmup ({WARMUP} iters)...", file=sys.stderr)
            for _ in range(WARMUP):
                session.run(None, {input_name: input_data})
            
            # Benchmark inferencia pura
            print(f"   ⏱️ Benchmark inferencia ({ITERATIONS} iters)...", file=sys.stderr)
            inference_times = []
            for i in range(ITERATIONS):
                start = time.time()
                outputs = session.run(None, {input_name: input_data})
                inference_times.append((time.time() - start) * 1000)
            
            # Benchmark pipeline completo (preprocess + inference)
            print(f"   ⏱️ Benchmark pipeline completo ({ITERATIONS} iters)...", file=sys.stderr)
            pipeline_times = []
            for i in range(ITERATIONS):
                start = time.time()
                # Preprocesamiento
                resized = cv2.resize(test_frame, (w, h))
                if model_info["input_type"] == "float32":
                    tensor = resized.transpose(2, 0, 1).astype(np.float32) / 255.0
                    tensor = tensor[np.newaxis, ...]
                else:
                    tensor = resized.transpose(2, 0, 1).astype(np.uint8)
                    tensor = tensor[np.newaxis, ...]
                # Inferencia
                outputs = session.run(None, {input_name: tensor})
                pipeline_times.append((time.time() - start) * 1000)
            
            # Calcular estadísticas
            model_results = {
                "model_size_mb": os.path.getsize(model_path) / 1024 / 1024,
                "load_time_s": load_time,
                "input_shape": list(input_shape),
                "input_type": model_info["input_type"],
                "inference_ms": {
                    "mean": float(np.mean(inference_times)),
                    "std": float(np.std(inference_times)),
                    "min": float(np.min(inference_times)),
                    "max": float(np.max(inference_times)),
                    "p50": float(np.percentile(inference_times, 50)),
                    "p95": float(np.percentile(inference_times, 95)),
                    "p99": float(np.percentile(inference_times, 99)),
                },
                "inference_fps": 1000.0 / np.mean(inference_times),
                "pipeline_ms": {
                    "mean": float(np.mean(pipeline_times)),
                    "std": float(np.std(pipeline_times)),
                    "min": float(np.min(pipeline_times)),
                    "max": float(np.max(pipeline_times)),
                    "p50": float(np.percentile(pipeline_times, 50)),
                    "p95": float(np.percentile(pipeline_times, 95)),
                },
                "pipeline_fps": 1000.0 / np.mean(pipeline_times),
            }
            
            results["models"][model_name] = model_results
            
            print(f"   ✅ Inferencia: {model_results['inference_ms']['mean']:.2f}ms ({model_results['inference_fps']:.1f} FPS)", file=sys.stderr)
            print(f"   ✅ Pipeline:   {model_results['pipeline_ms']['mean']:.2f}ms ({model_results['pipeline_fps']:.1f} FPS)", file=sys.stderr)
            
        except Exception as e:
            print(f"   ❌ Error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            results["models"][model_name] = {"error": str(e)}
    
    print(f"\n{'='*70}", file=sys.stderr)
    print("✅ Benchmark completado!", file=sys.stderr)

except Exception as e:
    results["error"] = str(e)
    print(f"❌ Error global: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc(file=sys.stderr)

# Output JSON
print(json.dumps(results, indent=2))
