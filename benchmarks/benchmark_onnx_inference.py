#!/usr/bin/env python3
"""
Benchmark ONNX Inference: Python vs Go vs Rust
Compara el rendimiento real de inferencia de modelos YOLO con ONNX Runtime

Este script se ejecuta en el host y coordina benchmarks en los contenedores Docker.
"""

import subprocess
import json
import time
import sys
import os

def run_python_benchmark():
    """Ejecuta benchmark de inferencia ONNX en Python (dentro del contenedor ai_worker)"""
    print("\n" + "="*70)
    print("🐍 BENCHMARK: Python + ONNX Runtime + YOLOv8/YOLO-NAS")
    print("="*70)
    
    benchmark_script = '''
import time
import numpy as np
import sys
import json
import os

# Configuración
ITERATIONS = 100
WARMUP = 10
IMAGE_SIZE = (640, 640)

results = {
    "language": "Python",
    "runtime": "onnxruntime",
    "iterations": ITERATIONS,
    "benchmarks": {}
}

# Test con onnxruntime directamente
try:
    import onnxruntime as ort
    
    # Buscar modelo ONNX
    model_paths = [
        "/app/models/yolov8n.onnx",
        "/app/yolov8n.onnx", 
        "/app/models/yolo_nas_s.onnx"
    ]
    
    model_path = None
    for p in model_paths:
        if os.path.exists(p):
            model_path = p
            break
    
    if model_path is None:
        # Exportar yolov8n a ONNX si tenemos ultralytics
        try:
            from ultralytics import YOLO
            model = YOLO("/app/yolov8n.pt")
            model.export(format="onnx", opset=12, simplify=True)
            model_path = "/app/yolov8n.onnx"
        except Exception as e:
            print(f"No se pudo exportar modelo: {e}", file=sys.stderr)
    
    if model_path and os.path.exists(model_path):
        print(f"✅ Modelo: {model_path} ({os.path.getsize(model_path)/1024/1024:.1f} MB)", file=sys.stderr)
        
        # Crear sesión ONNX
        start = time.time()
        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess_options.intra_op_num_threads = 4
        session = ort.InferenceSession(model_path, sess_options, providers=["CPUExecutionProvider"])
        load_time = time.time() - start
        print(f"✅ Modelo cargado en {load_time:.3f}s", file=sys.stderr)
        
        input_name = session.get_inputs()[0].name
        input_shape = session.get_inputs()[0].shape
        print(f"✅ Input: {input_name} - Shape: {input_shape}", file=sys.stderr)
        
        # Generar imagen de prueba (simula frame de video)
        input_data = np.random.rand(1, 3, 640, 640).astype(np.float32)
        
        # Warmup
        print(f"⏳ Warmup ({WARMUP} iteraciones)...", file=sys.stderr)
        for _ in range(WARMUP):
            session.run(None, {input_name: input_data})
        
        # Benchmark inferencia pura
        print(f"⏱️ Benchmark ({ITERATIONS} iteraciones)...", file=sys.stderr)
        inference_times = []
        for i in range(ITERATIONS):
            start = time.time()
            outputs = session.run(None, {input_name: input_data})
            inference_times.append((time.time() - start) * 1000)  # ms
        
        results["benchmarks"]["inference_ms"] = {
            "mean": float(np.mean(inference_times)),
            "std": float(np.std(inference_times)),
            "min": float(np.min(inference_times)),
            "max": float(np.max(inference_times)),
            "p50": float(np.percentile(inference_times, 50)),
            "p95": float(np.percentile(inference_times, 95)),
            "p99": float(np.percentile(inference_times, 99)),
        }
        results["benchmarks"]["fps"] = 1000.0 / np.mean(inference_times)
        results["model"] = os.path.basename(model_path)
        results["load_time_s"] = load_time
        
        # Benchmark con preprocesamiento (imagen BGR -> tensor normalizado)
        preprocess_times = []
        raw_image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)  # Simula frame BGR
        
        def preprocess(img):
            # Resize a 640x640
            import cv2
            resized = cv2.resize(img, (640, 640))
            # BGR -> RGB -> CHW -> float32 normalizado
            rgb = resized[:, :, ::-1]
            chw = rgb.transpose(2, 0, 1)
            normalized = chw.astype(np.float32) / 255.0
            return normalized[np.newaxis, ...]
        
        for _ in range(WARMUP):
            tensor = preprocess(raw_image)
            session.run(None, {input_name: tensor})
        
        full_times = []
        for i in range(ITERATIONS):
            start = time.time()
            tensor = preprocess(raw_image)
            outputs = session.run(None, {input_name: tensor})
            full_times.append((time.time() - start) * 1000)
        
        results["benchmarks"]["full_pipeline_ms"] = {
            "mean": float(np.mean(full_times)),
            "std": float(np.std(full_times)),
            "min": float(np.min(full_times)),
            "max": float(np.max(full_times)),
            "p50": float(np.percentile(full_times, 50)),
            "p95": float(np.percentile(full_times, 95)),
        }
        results["benchmarks"]["full_pipeline_fps"] = 1000.0 / np.mean(full_times)
        
        print("✅ Benchmark completado!", file=sys.stderr)
    else:
        results["error"] = "No ONNX model found"
        print("❌ No se encontró modelo ONNX", file=sys.stderr)

except ImportError as e:
    results["error"] = f"Missing dependency: {e}"
    print(f"❌ Dependencia faltante: {e}", file=sys.stderr)
except Exception as e:
    results["error"] = str(e)
    print(f"❌ Error: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc()

print(json.dumps(results, indent=2))
'''
    
    try:
        result = subprocess.run(
            ["docker", "exec", "video-analytics-saas-ai_worker-1", "python3", "-c", benchmark_script],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        print(result.stderr)  # Logs
        
        # Parsear JSON del stdout
        try:
            data = json.loads(result.stdout)
            return data
        except json.JSONDecodeError:
            print(f"Error parsing JSON: {result.stdout}")
            return {"error": "JSON parse error", "output": result.stdout}
            
    except subprocess.TimeoutExpired:
        return {"error": "Timeout"}
    except Exception as e:
        return {"error": str(e)}


def run_go_benchmark():
    """Ejecuta benchmark de inferencia ONNX en Go"""
    print("\n" + "="*70)
    print("🐹 BENCHMARK: Go + ONNX Runtime + YOLOv8")
    print("="*70)
    
    # Verificar si el contenedor Go está corriendo
    result = subprocess.run(
        ["docker", "ps", "--filter", "name=ai_worker_go", "--format", "{{.Names}}"],
        capture_output=True,
        text=True
    )
    
    if "ai_worker_go" not in result.stdout:
        print("⚠️ Contenedor ai_worker_go no está corriendo")
        print("💡 Para ejecutar el benchmark de Go, iniciar con:")
        print("   docker compose -f docker-compose.yml -f docker-compose.mediamtx.yml up -d ai_worker_go")
        return {"error": "Container not running", "language": "Go"}
    
    try:
        result = subprocess.run(
            ["docker", "exec", "video-analytics-saas-ai_worker_go-1", "/app/ai_worker_go", "--benchmark"],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        print(result.stderr)
        
        try:
            data = json.loads(result.stdout)
            data["language"] = "Go"
            return data
        except json.JSONDecodeError:
            return {"error": "JSON parse error", "output": result.stdout, "language": "Go"}
            
    except Exception as e:
        return {"error": str(e), "language": "Go"}


def run_rust_benchmark():
    """Ejecuta benchmark de inferencia ONNX en Rust"""
    print("\n" + "="*70)
    print("🦀 BENCHMARK: Rust + ONNX Runtime + YOLOv8")
    print("="*70)
    
    # Verificar si el contenedor Rust está corriendo
    result = subprocess.run(
        ["docker", "ps", "--filter", "name=rust_ai_worker", "--format", "{{.Names}}"],
        capture_output=True,
        text=True
    )
    
    if "rust_ai_worker" not in result.stdout:
        print("⚠️ Contenedor rust_ai_worker no está corriendo")
        print("💡 Para ejecutar el benchmark de Rust, iniciar con:")
        print("   docker compose -f docker-compose.yml -f docker-compose.mediamtx.yml up -d rust_ai_worker")
        return {"error": "Container not running", "language": "Rust"}
    
    try:
        result = subprocess.run(
            ["docker", "exec", "video-analytics-saas-rust_ai_worker-1", "/app/rust_ai_worker", "--benchmark"],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        print(result.stderr)
        
        try:
            data = json.loads(result.stdout)
            data["language"] = "Rust"
            return data
        except json.JSONDecodeError:
            return {"error": "JSON parse error", "output": result.stdout, "language": "Rust"}
            
    except Exception as e:
        return {"error": str(e), "language": "Rust"}


def print_comparison(results):
    """Imprime tabla comparativa de resultados"""
    print("\n" + "="*80)
    print("📊 COMPARACIÓN DE INFERENCIA ONNX: Python vs Go vs Rust")
    print("="*80)
    
    # Solo incluir resultados exitosos
    valid_results = {k: v for k, v in results.items() if "error" not in v and "benchmarks" in v}
    
    if not valid_results:
        print("❌ No hay resultados válidos para comparar")
        for lang, data in results.items():
            if "error" in data:
                print(f"   {lang}: {data['error']}")
        return
    
    print(f"\n{'Métrica':<30} ", end="")
    for lang in valid_results:
        print(f"{lang:>15}", end="")
    print()
    print("-" * (30 + 15 * len(valid_results)))
    
    # Inferencia pura
    if all("inference_ms" in r["benchmarks"] for r in valid_results.values()):
        print(f"{'Inferencia (ms) - mean':<30} ", end="")
        for lang, data in valid_results.items():
            val = data["benchmarks"]["inference_ms"]["mean"]
            print(f"{val:>15.2f}", end="")
        print()
        
        print(f"{'Inferencia (ms) - p95':<30} ", end="")
        for lang, data in valid_results.items():
            val = data["benchmarks"]["inference_ms"]["p95"]
            print(f"{val:>15.2f}", end="")
        print()
        
        print(f"{'FPS (inferencia)':<30} ", end="")
        for lang, data in valid_results.items():
            val = data["benchmarks"]["fps"]
            print(f"{val:>15.1f}", end="")
        print()
    
    # Pipeline completo
    if all("full_pipeline_ms" in r.get("benchmarks", {}) for r in valid_results.values()):
        print(f"\n{'Pipeline completo (ms) - mean':<30} ", end="")
        for lang, data in valid_results.items():
            val = data["benchmarks"]["full_pipeline_ms"]["mean"]
            print(f"{val:>15.2f}", end="")
        print()
        
        print(f"{'FPS (pipeline completo)':<30} ", end="")
        for lang, data in valid_results.items():
            val = data["benchmarks"]["full_pipeline_fps"]
            print(f"{val:>15.1f}", end="")
        print()
    
    # Encontrar el más rápido
    if valid_results:
        print("\n" + "-" * 80)
        fastest = min(valid_results.items(), 
                     key=lambda x: x[1]["benchmarks"].get("inference_ms", {}).get("mean", float("inf")))
        print(f"\n🏆 Más rápido en inferencia: {fastest[0]}")
        
        # Calcular speedups
        if len(valid_results) > 1:
            base_time = fastest[1]["benchmarks"]["inference_ms"]["mean"]
            print("\n📈 Speedup relativo:")
            for lang, data in sorted(valid_results.items(), 
                                    key=lambda x: x[1]["benchmarks"]["inference_ms"]["mean"]):
                time_ms = data["benchmarks"]["inference_ms"]["mean"]
                ratio = time_ms / base_time
                bar = "█" * int(20 / ratio)
                print(f"   {lang:<10}: {time_ms:>8.2f}ms ({ratio:.2f}x) {bar}")


def main():
    print("="*80)
    print("🔬 BENCHMARK DE INFERENCIA ONNX - Video Analytics")
    print("="*80)
    print("\nEste benchmark compara el rendimiento REAL de inferencia")
    print("de modelos YOLO usando ONNX Runtime en Python, Go y Rust.\n")
    
    results = {}
    
    # Python (siempre disponible)
    results["Python"] = run_python_benchmark()
    
    # Go (opcional)
    results["Go"] = run_go_benchmark()
    
    # Rust (opcional)
    results["Rust"] = run_rust_benchmark()
    
    # Mostrar comparación
    print_comparison(results)
    
    # Guardar resultados JSON
    output_file = "/home/pta/video-analytics-saas/video-analytics-saas/benchmarks/onnx_inference_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n💾 Resultados guardados en: {output_file}")
    
    # Insights
    print("\n" + "="*80)
    print("💡 INSIGHTS")
    print("="*80)
    print("""
La inferencia ONNX es el cuello de botella real en video analytics.
El rendimiento depende principalmente de:

1. 🔧 ONNX Runtime version y optimizaciones (CPU/GPU/TensorRT)
2. 🧮 Número de threads configurados
3. 📦 Tamaño del modelo (yolov8n=6MB, yolov8s=22MB, yolov8m=50MB)
4. 🖼️ Tamaño de entrada (640x640 vs 1280x1280)

El lenguaje (Python/Go/Rust) tiene impacto MÍNIMO porque:
- ONNX Runtime es la misma librería C++ en todos los casos
- El binding solo hace marshaling de datos hacia/desde ONNX Runtime
- El 95%+ del tiempo se pasa dentro de ONNX Runtime

Para mejorar rendimiento real:
1. Usar GPU con CUDA/TensorRT provider
2. Usar modelos más pequeños (yolov8n vs yolov8x)
3. Procesar en batch si es posible
4. Reducir resolución de entrada si es aceptable
""")


if __name__ == "__main__":
    main()
