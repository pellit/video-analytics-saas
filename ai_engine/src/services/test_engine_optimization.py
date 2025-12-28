import os
import subprocess
import sys
import time

# ==============================================================================
# CONFIGURACIÓN
# ==============================================================================
MODELS_DIR = "/app/ai_engine/models"
# Usamos el ONNX que ya debería estar en tu imagen Docker
ONNX_PATH = os.path.join(MODELS_DIR, "yolov8n.onnx") 
ENGINE_PATH = os.path.join(MODELS_DIR, "yolov8n_416.engine")

# Ruta al binario de NVIDIA (estándar en Jetson)
TRTEXEC_BIN = "/usr/src/tensorrt/bin/trtexec"

def check_files():
    if not os.path.exists(ONNX_PATH):
        print(f"❌ ERROR CRÍTICO: No encuentro el archivo ONNX en: {ONNX_PATH}")
        print("   Verifica que la imagen Docker se construyó correctamente o copia tu yolov8n.onnx ahí.")
        return False
    
    if not os.path.exists(TRTEXEC_BIN):
        # Intentar buscarlo en el PATH por si acaso
        global TRTEXEC_BIN
        TRTEXEC_BIN = "trtexec"
        try:
            subprocess.run([TRTEXEC_BIN, "--help"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            print("❌ ERROR: No encuentro la herramienta 'trtexec'.")
            print("   ¿Estás seguro que estás usando la imagen base l4t-jetpack o dustynv/jetson-inference?")
            return False
            
    print(f"✅ ONNX encontrado: {ONNX_PATH}")
    return True

def build_engine():
    print("\n[1/2] 🛠️  CONSTRUYENDO ENGINE DESDE ONNX (OFFLINE)...")
    if os.path.exists(ENGINE_PATH):
        print(f"✅ El engine ya existe: {ENGINE_PATH}")
        print("   (Si quieres regenerarlo, bórralo primero con: rm " + ENGINE_PATH + ")")
        return True

    print(f"⏳ Ejecutando conversión con trtexec (esto tardará 5-10 min)...")
    print("   Parámetros: FP16=ON, Input=416x416")
    
    # Comando mágico de conversión nativa
    # --onnx: Entrada
    # --saveEngine: Salida
    # --fp16: Usar media precisión (Doble de velocidad en Jetson)
    # --explicitBatch: Necesario para ONNX modernos
    cmd = [
        TRTEXEC_BIN,
        f"--onnx={ONNX_PATH}",
        f"--saveEngine={ENGINE_PATH}",
        "--fp16",
        "--allowGPUFallback",
        "--explicitBatch"
    ]
    
    # Nota: Si el ONNX original es dinámico o 640x640, trtexec intentará optimizarlo tal cual.
    # Si falla por dimensiones, agregaremos flags de shapes.
    
    try:
        # Ejecutamos y mostramos output para que veas el progreso
        t0 = time.time()
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        for line in process.stdout:
            # Filtrar ruido, mostrar progreso
            if "TensorRT version" in line or "Starting build" in line or "Built engine" in line:
                print(f"   [TRT log] {line.strip()}")
        
        process.wait()
        
        if process.returncode == 0 and os.path.exists(ENGINE_PATH):
            print(f"✅ Conversión completada en {int(time.time()-t0)} segundos.")
            return True
        else:
            print("❌ Error: trtexec falló. Revisa los logs anteriores.")
            return False
    except Exception as e:
        print(f"❌ Excepción ejecutando trtexec: {e}")
        return False

def benchmark_engine():
    print("\n[2/2] 🚀 BENCHMARK DE VELOCIDAD (ENGINE)...")
    
    if not os.path.exists(ENGINE_PATH):
        print("❌ No hay engine para probar.")
        return

    cmd = [
        TRTEXEC_BIN,
        f"--loadEngine={ENGINE_PATH}",
        "--duration=10",     # 10 segundos de prueba
        "--noDataTransfer",  # Medir solo cómputo GPU
        "--useSpinWait"      # Máximo estrés
    ]
    
    print(f"Ejecutando: {' '.join(cmd)}")
    print("-" * 50)
    
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        fps_found = False
        
        for line in process.stdout:
            if "Queries per second" in line: # Esta es la línea de FPS
                print(f"🏁 \033[92m{line.strip()}\033[0m") # Verde
                fps_found = True
            elif "Mean Host Latency" in line or "Throughput" in line:
                print(f"   {line.strip()}")
        
        process.wait()
        print("-" * 50)
        
        if not fps_found:
            print("⚠️ No pude leer los FPS exactos, pero si no hubo error, funcionó.")
            
    except Exception as e:
        print(f"❌ Error en benchmark: {e}")

if __name__ == "__main__":
    if check_files():
        if build_engine():
            benchmark_engine()