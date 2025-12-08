#!/usr/bin/env python3
"""
Benchmark comparativo: Python vs Rust AI Worker
Compara tiempos de inferencia, throughput y uso de memoria
"""

import asyncio
import json
import os
import sys
import time
import subprocess
import psutil
from pathlib import Path
from typing import Optional

try:
    import redis.asyncio as redis
except ImportError:
    import redis

# Colores para terminal
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_header(text: str):
    """Imprime un header decorativo"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{text:^60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.END}\n")


def print_result(label: str, value: str, unit: str = ""):
    """Imprime un resultado formateado"""
    print(f"  {Colors.BLUE}{label:25}{Colors.END}: {Colors.GREEN}{value}{Colors.END} {unit}")


async def get_redis_client() -> Optional[redis.Redis]:
    """Obtiene cliente Redis"""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    try:
        client = redis.from_url(redis_url, decode_responses=True)
        await client.ping()
        return client
    except Exception as e:
        print(f"{Colors.YELLOW}⚠️  Redis no disponible: {e}{Colors.END}")
        return None


async def benchmark_python_worker(iterations: int = 100) -> dict:
    """
    Benchmark del worker Python
    Ejecuta inferencias y mide tiempos
    """
    print_header("Benchmark: Python Worker")
    
    results = {
        "worker_type": "python",
        "iterations": iterations,
        "avg_inference_ms": 0,
        "min_inference_ms": 0,
        "max_inference_ms": 0,
        "fps": 0,
        "memory_mb": 0,
        "error": None
    }
    
    try:
        # Importar dependencias de Python worker
        import numpy as np
        
        # Verificar si existe modelo ONNX
        model_path = os.getenv("MODEL_PATH", "/app/models/yolov8n.onnx")
        alt_paths = [
            "./ai_engine_go/models/yolov8n.onnx",
            "./ai_engine/yolov8n.pt",
            "../ai_engine_go/models/yolov8n.onnx"
        ]
        
        onnx_available = False
        for path in [model_path] + alt_paths:
            if os.path.exists(path):
                model_path = path
                onnx_available = True
                break
        
        if not onnx_available:
            print(f"{Colors.YELLOW}⚠️  Modelo ONNX no encontrado, usando benchmark sintético{Colors.END}")
            
            # Benchmark sintético (simula trabajo de inferencia)
            times = []
            start_total = time.time()
            
            for i in range(iterations):
                start = time.time()
                
                # Simular preprocesamiento
                frame = np.random.rand(1, 3, 640, 640).astype(np.float32)
                
                # Simular inferencia (operaciones matriciales intensivas)
                # Esto NO es una inferencia real, solo mide overhead de NumPy
                _ = np.matmul(frame.reshape(3, -1), frame.reshape(-1, 3))
                _ = np.sum(frame)
                _ = np.argmax(frame, axis=2)
                
                # Simular NMS
                boxes = np.random.rand(100, 4).astype(np.float32)
                scores = np.random.rand(100).astype(np.float32)
                _ = np.argsort(scores)[::-1][:10]
                
                elapsed_ms = (time.time() - start) * 1000
                times.append(elapsed_ms)
                
                if (i + 1) % 20 == 0:
                    print(f"  Progress: {i+1}/{iterations}")
            
            total_time = time.time() - start_total
            
            results["avg_inference_ms"] = sum(times) / len(times)
            results["min_inference_ms"] = min(times)
            results["max_inference_ms"] = max(times)
            results["fps"] = iterations / total_time
            results["note"] = "synthetic_benchmark"
            
        else:
            # Benchmark con ONNX Runtime real
            import onnxruntime as ort
            
            print(f"  Modelo: {model_path}")
            
            # Crear sesión ONNX
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 4
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            session = ort.InferenceSession(model_path, opts, providers=['CPUExecutionProvider'])
            
            input_name = session.get_inputs()[0].name
            
            # Warmup
            print("  Warmup...")
            dummy = np.random.rand(1, 3, 640, 640).astype(np.float32)
            for _ in range(10):
                _ = session.run(None, {input_name: dummy})
            
            # Benchmark
            print(f"  Running {iterations} iterations...")
            times = []
            start_total = time.time()
            
            for i in range(iterations):
                frame = np.random.rand(1, 3, 640, 640).astype(np.float32)
                
                start = time.time()
                _ = session.run(None, {input_name: frame})
                elapsed_ms = (time.time() - start) * 1000
                times.append(elapsed_ms)
                
                if (i + 1) % 20 == 0:
                    print(f"  Progress: {i+1}/{iterations}")
            
            total_time = time.time() - start_total
            
            results["avg_inference_ms"] = sum(times) / len(times)
            results["min_inference_ms"] = min(times)
            results["max_inference_ms"] = max(times)
            results["fps"] = iterations / total_time
        
        # Obtener uso de memoria
        process = psutil.Process()
        results["memory_mb"] = process.memory_info().rss / (1024 * 1024)
        
    except ImportError as e:
        results["error"] = f"Missing dependency: {e}"
        print(f"{Colors.RED}❌ Error: {e}{Colors.END}")
    except Exception as e:
        results["error"] = str(e)
        print(f"{Colors.RED}❌ Error: {e}{Colors.END}")
    
    return results


async def benchmark_rust_worker(iterations: int = 100) -> dict:
    """
    Benchmark del worker Rust
    Ejecuta el binario con BENCHMARK_MODE
    """
    print_header("Benchmark: Rust Worker")
    
    results = {
        "worker_type": "rust",
        "iterations": iterations,
        "avg_inference_ms": 0,
        "min_inference_ms": 0,
        "max_inference_ms": 0,
        "fps": 0,
        "memory_mb": 0,
        "error": None
    }
    
    # Buscar binario Rust
    rust_binary = None
    possible_paths = [
        "./rust_ai_worker/target/release/rust_ai_worker",
        "./target/release/rust_ai_worker",
        "/app/rust_ai_worker"
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            rust_binary = path
            break
    
    if not rust_binary:
        # Intentar compilar
        print(f"{Colors.YELLOW}⚠️  Binario no encontrado, intentando compilar...{Colors.END}")
        try:
            cwd = "./rust_ai_worker" if os.path.exists("./rust_ai_worker/Cargo.toml") else "."
            subprocess.run(
                ["cargo", "build", "--release"],
                cwd=cwd,
                check=True,
                capture_output=True
            )
            rust_binary = f"{cwd}/target/release/rust_ai_worker"
        except subprocess.CalledProcessError as e:
            results["error"] = f"Compilation failed: {e}"
            print(f"{Colors.RED}❌ Compilación falló{Colors.END}")
            return results
        except FileNotFoundError:
            results["error"] = "Cargo not found"
            print(f"{Colors.RED}❌ Cargo no encontrado{Colors.END}")
            return results
    
    print(f"  Binario: {rust_binary}")
    
    # Buscar modelo
    model_path = os.getenv("MODEL_PATH", "")
    for path in ["./ai_engine_go/models/yolov8n.onnx", "/app/models/yolov8n.onnx"]:
        if os.path.exists(path):
            model_path = path
            break
    
    if not model_path:
        results["error"] = "Model not found"
        print(f"{Colors.RED}❌ Modelo no encontrado{Colors.END}")
        return results
    
    # Ejecutar benchmark
    env = os.environ.copy()
    env["BENCHMARK_MODE"] = "1"
    env["BENCHMARK_ITERATIONS"] = str(iterations)
    env["MODEL_PATH"] = model_path
    env["RUST_LOG"] = "info"
    
    print(f"  Running {iterations} iterations...")
    
    try:
        process = subprocess.Popen(
            [rust_binary],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        output_lines = []
        for line in iter(process.stdout.readline, ''):
            line = line.strip()
            output_lines.append(line)
            if "Benchmark Results" in line:
                # Empezar a capturar resultados
                pass
            elif "Avg inference:" in line:
                try:
                    val = float(line.split(":")[1].replace("ms", "").strip())
                    results["avg_inference_ms"] = val
                except:
                    pass
            elif "Min inference:" in line:
                try:
                    val = float(line.split(":")[1].replace("ms", "").strip())
                    results["min_inference_ms"] = val
                except:
                    pass
            elif "Max inference:" in line:
                try:
                    val = float(line.split(":")[1].replace("ms", "").strip())
                    results["max_inference_ms"] = val
                except:
                    pass
            elif "Throughput:" in line:
                try:
                    val = float(line.split(":")[1].replace("FPS", "").strip())
                    results["fps"] = val
                except:
                    pass
            elif "Memory:" in line:
                try:
                    val = float(line.split(":")[1].replace("MB", "").strip())
                    results["memory_mb"] = val
                except:
                    pass
            
            if process.poll() is not None:
                break
        
        process.wait(timeout=300)
        
    except subprocess.TimeoutExpired:
        process.kill()
        results["error"] = "Timeout"
    except Exception as e:
        results["error"] = str(e)
        print(f"{Colors.RED}❌ Error: {e}{Colors.END}")
    
    return results


def print_comparison(python_results: dict, rust_results: dict):
    """Imprime comparación de resultados"""
    print_header("Comparación de Resultados")
    
    def safe_div(a, b):
        if b == 0:
            return 0
        return a / b
    
    # Tabla de resultados
    print(f"  {'Métrica':<25} {'Python':>15} {'Rust':>15} {'Speedup':>12}")
    print(f"  {'-'*67}")
    
    # Avg inference time
    py_avg = python_results.get("avg_inference_ms", 0)
    rs_avg = rust_results.get("avg_inference_ms", 0)
    speedup = safe_div(py_avg, rs_avg) if rs_avg > 0 else 0
    color = Colors.GREEN if speedup > 1 else Colors.RED
    print(f"  {'Avg Inference Time':<25} {py_avg:>12.2f}ms {rs_avg:>12.2f}ms {color}{speedup:>10.2f}x{Colors.END}")
    
    # Min inference
    py_min = python_results.get("min_inference_ms", 0)
    rs_min = rust_results.get("min_inference_ms", 0)
    speedup = safe_div(py_min, rs_min) if rs_min > 0 else 0
    color = Colors.GREEN if speedup > 1 else Colors.RED
    print(f"  {'Min Inference Time':<25} {py_min:>12.2f}ms {rs_min:>12.2f}ms {color}{speedup:>10.2f}x{Colors.END}")
    
    # Max inference
    py_max = python_results.get("max_inference_ms", 0)
    rs_max = rust_results.get("max_inference_ms", 0)
    speedup = safe_div(py_max, rs_max) if rs_max > 0 else 0
    color = Colors.GREEN if speedup > 1 else Colors.RED
    print(f"  {'Max Inference Time':<25} {py_max:>12.2f}ms {rs_max:>12.2f}ms {color}{speedup:>10.2f}x{Colors.END}")
    
    # FPS
    py_fps = python_results.get("fps", 0)
    rs_fps = rust_results.get("fps", 0)
    speedup = safe_div(rs_fps, py_fps) if py_fps > 0 else 0
    color = Colors.GREEN if speedup > 1 else Colors.RED
    print(f"  {'Throughput':<25} {py_fps:>12.2f} FPS {rs_fps:>12.2f} FPS {color}{speedup:>10.2f}x{Colors.END}")
    
    # Memory
    py_mem = python_results.get("memory_mb", 0)
    rs_mem = rust_results.get("memory_mb", 0)
    ratio = safe_div(py_mem, rs_mem) if rs_mem > 0 else 0
    color = Colors.GREEN if ratio > 1 else Colors.RED
    print(f"  {'Memory Usage':<25} {py_mem:>12.1f} MB {rs_mem:>12.1f} MB {color}{ratio:>10.2f}x{Colors.END}")
    
    print()
    
    # Resumen
    if rs_avg > 0 and py_avg > 0:
        overall_speedup = py_avg / rs_avg
        if overall_speedup > 1:
            print(f"  {Colors.GREEN}✅ Rust es {overall_speedup:.2f}x más rápido que Python{Colors.END}")
        else:
            print(f"  {Colors.YELLOW}⚠️  Python es {1/overall_speedup:.2f}x más rápido que Rust{Colors.END}")
    
    if rs_mem > 0 and py_mem > 0:
        mem_ratio = py_mem / rs_mem
        if mem_ratio > 1:
            print(f"  {Colors.GREEN}✅ Rust usa {mem_ratio:.2f}x menos memoria{Colors.END}")
        else:
            print(f"  {Colors.YELLOW}⚠️  Python usa {1/mem_ratio:.2f}x menos memoria{Colors.END}")


async def main():
    """Función principal"""
    print_header("Benchmark: Python vs Rust AI Worker")
    
    # Configuración
    iterations = int(os.getenv("BENCHMARK_ITERATIONS", "100"))
    run_python = os.getenv("SKIP_PYTHON", "").lower() != "true"
    run_rust = os.getenv("SKIP_RUST", "").lower() != "true"
    
    print(f"  Iteraciones: {iterations}")
    print(f"  Benchmark Python: {'✓' if run_python else '✗'}")
    print(f"  Benchmark Rust: {'✓' if run_rust else '✗'}")
    
    # Resultados
    python_results = {}
    rust_results = {}
    
    # Ejecutar benchmarks
    if run_python:
        python_results = await benchmark_python_worker(iterations)
        if not python_results.get("error"):
            print_result("Avg Inference", f"{python_results['avg_inference_ms']:.2f}", "ms")
            print_result("Min Inference", f"{python_results['min_inference_ms']:.2f}", "ms")
            print_result("Max Inference", f"{python_results['max_inference_ms']:.2f}", "ms")
            print_result("Throughput", f"{python_results['fps']:.2f}", "FPS")
            print_result("Memory", f"{python_results['memory_mb']:.1f}", "MB")
    
    if run_rust:
        rust_results = await benchmark_rust_worker(iterations)
        if not rust_results.get("error"):
            print_result("Avg Inference", f"{rust_results['avg_inference_ms']:.2f}", "ms")
            print_result("Min Inference", f"{rust_results['min_inference_ms']:.2f}", "ms")
            print_result("Max Inference", f"{rust_results['max_inference_ms']:.2f}", "ms")
            print_result("Throughput", f"{rust_results['fps']:.2f}", "FPS")
            print_result("Memory", f"{rust_results['memory_mb']:.1f}", "MB")
    
    # Comparación
    if python_results and rust_results:
        print_comparison(python_results, rust_results)
    
    # Guardar resultados
    output_file = os.getenv("BENCHMARK_OUTPUT", "benchmark_results.json")
    results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "iterations": iterations,
        "python": python_results,
        "rust": rust_results
    }
    
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n  {Colors.BLUE}Resultados guardados en: {output_file}{Colors.END}")
    
    # Publicar a Redis si está disponible
    redis_client = await get_redis_client()
    if redis_client:
        try:
            await redis_client.set("benchmark:comparison", json.dumps(results))
            await redis_client.close()
            print(f"  {Colors.BLUE}Resultados publicados en Redis{Colors.END}")
        except Exception as e:
            print(f"  {Colors.YELLOW}⚠️  No se pudo publicar a Redis: {e}{Colors.END}")


if __name__ == "__main__":
    asyncio.run(main())
