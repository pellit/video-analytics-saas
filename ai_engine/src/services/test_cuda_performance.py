import sys
import os

# --- FIX TEMPORAL PARA TESTING ---
# Añadimos la ruta actual al path para poder importar sin paquete si es necesario
# O mejor aún, añadimos la raíz /app
sys.path.append("/app")

# Truco: Si ejecutamos esto directo, forzamos que las importaciones funcionen
# Cambia la importación relativa en el script que llamamos (esto es un parche sucio pero efectivo para testing rápido)
try:
    from src.services.hit_detection_service_optimized import HitDetectionServiceOptimized
except ImportError:
    # Fallback por si la estructura de carpetas es distinta
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from hit_detection_service_optimized import HitDetectionServiceOptimized
# ---------------------------------


import cv2
import time
import numpy as np
import os
from hit_detection_service_optimized import HitDetectionServiceOptimized

def benchmark_model(name, wrapper, img):
    print(f"\n--- Benchmarking {name} ---")
    if wrapper.net is None:
        print(f"❌ Modelo {name} NO cargado.")
        return

    # Warmup (Calentamiento de GPU)
    print("🔥 Calentando GPU...")
    for _ in range(5):
        wrapper.detect(img)
    
    # Test Real
    start = time.time()
    iters = 50
    print(f"🚀 Ejecutando {iters} inferencias...")
    for _ in range(iters):
        wrapper.detect(img)
    end = time.time()
    
    avg_time = (end - start) / iters
    fps = 1.0 / avg_time
    print(f"✅ {name}: {avg_time*1000:.2f} ms por frame ({fps:.2f} FPS)")

def check_opencv_cuda():
    print("\n--- Verificación OpenCV CUDA ---")
    try:
        count = cv2.cuda.getCudaEnabledDeviceCount()
        print(f"Dispositivos CUDA detectados: {count}")
        if count > 0:
            cv2.cuda.printCudaDeviceInfo(0)
            return True
        else:
            print("⚠️ ADVERTENCIA: OpenCV no detecta CUDA. Todo correrá en CPU (Lento).")
            return False
    except AttributeError:
        print("⚠️ ERROR: Tu versión de OpenCV no tiene el módulo 'cv2.cuda'. Recompila con CUDA.")
        return False

def main():
    print("========================================")
    print(" TEST DE RENDIMIENTO - JETSON NANO")
    print("========================================")
    
    has_cuda = check_opencv_cuda()
    
    # Crear imagen dummy (640x640)
    img = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)
    
    print("\n--- Inicializando Servicio ---")
    # Instanciamos la clase (esto carga los modelos)
    try:
        service = HitDetectionServiceOptimized()
        print("✅ Servicio inicializado correctamente.")
    except Exception as e:
        print(f"❌ Error inicializando servicio: {e}")
        return

    # Verificar backends de los modelos cargados
    print("\n--- Verificando Backends de Modelos ---")
    models = {
        "YOLO Det": service.det,
        "YOLO Pose": service.pose,
        # "MiDaS": service.midas # MiDaS es raw dnn, más difícil de checkear backend directamente en wrapper
    }
    
    for name, wrapper in models.items():
        if wrapper.net:
            # Truco para ver el backend actual (si OpenCV lo permite)
            # En Python es difícil ver el backend activo sin correrlo, 
            # pero ya lo configuramos en el código con setPreferableTarget
            print(f"🔹 {name}: Cargado. Configurado para CUDA.")
            benchmark_model(name, wrapper, img)
        else:
            print(f"🔸 {name}: No se pudo cargar.")

    # Test de MiDaS si está disponible
    if service.midas:
        print(f"\n--- Benchmarking MiDaS (Profundidad) ---")
        blob = cv2.dnn.blobFromImage(img, 1/255.0, (256, 256), (123.675, 116.28, 103.53), True, False)
        service.midas.setInput(blob)
        
        # Warmup
        service.midas.forward()
        
        start = time.time()
        for _ in range(20): # MiDaS es pesado, menos iters
            service.midas.forward()
        end = time.time()
        avg = (end - start) / 20
        print(f"✅ MiDaS: {avg*1000:.2f} ms ({1.0/avg:.2f} FPS)")
    else:
        print("🔸 MiDaS no cargado.")

if __name__ == "__main__":
    main()