import cv2
import time
import numpy as np
import os

# ==============================================================================
# CONFIGURACIÓN
# ==============================================================================
MODELS_DIR = "/app/ai_engine/models"
DET_MODEL_PATH = os.path.join(MODELS_DIR, "yolov8n.onnx")
POSE_MODEL_PATH = os.path.join(MODELS_DIR, "yolov8n-pose.onnx")
MIDAS_MODEL_PATH = os.path.join(MODELS_DIR, "midas_v21_small.onnx")

# ==============================================================================
# CLASES PARA EL TEST (Simulando la versión vieja y la nueva)
# ==============================================================================

class YoloWrapperTest:
    def __init__(self, model_path, input_size):
        self.model_path = model_path
        self.input_size = input_size
        self.net = None
        
    def load(self):
        if not os.path.exists(self.model_path):
            print(f"❌ Modelo no encontrado: {self.model_path}")
            return False
        try:
            self.net = cv2.dnn.readNet(self.model_path)
            self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
            self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
            return True
        except Exception as e:
            print(f"❌ Error cargando {self.model_path}: {e}")
            return False

    def detect(self, img):
        if not self.net: return
        blob = cv2.dnn.blobFromImage(img, 1/255.0, self.input_size, swapRB=True, crop=False)
        self.net.setInput(blob)
        self.net.forward() # Solo medimos inferencia, no post-proceso

def benchmark(name, wrapper, img, iters=50):
    if not wrapper.net: return 0
    
    # Warmup
    wrapper.detect(img)
    
    start = time.time()
    for _ in range(iters):
        wrapper.detect(img)
    total_time = time.time() - start
    
    avg_ms = (total_time / iters) * 1000
    fps = 1.0 / (total_time / iters)
    print(f"   👉 {name:<20} | {avg_ms:.1f} ms | {fps:.1f} FPS")
    return avg_ms

# ==============================================================================
# MAIN
# ==============================================================================
def main():
    print("\n=======================================================")
    print(" 🧪 TEST DE OPTIMIZACIÓN PREVIO A CAMBIOS")
    print("=======================================================")
    
    # Imagen dummy 1080p
    img = np.zeros((1080, 1920, 3), dtype=np.uint8)

    # 1. COMPARATIVA YOLO (Detección)
    print("\n1️⃣  COMPARATIVA YOLO DETECCION (yolov8n)")
    print("-" * 50)
    
    yolo_old = YoloWrapperTest(DET_MODEL_PATH, (640, 640))
    yolo_new = YoloWrapperTest(DET_MODEL_PATH, (416, 416)) # <--- OPTIMIZACIÓN
    
    if yolo_old.load() and yolo_new.load():
        t_old = benchmark("Actual (640x640)", yolo_old, img)
        t_new = benchmark("Propuesto (416x416)", yolo_new, img)
        
        speedup = t_old / t_new if t_new > 0 else 0
        print(f"\n   🚀 MEJORA ESTIMADA: {speedup:.1f}x más rápido")
    
    # 2. COMPARATIVA POSE
    print("\n2️⃣  COMPARATIVA YOLO POSE (yolov8n-pose)")
    print("-" * 50)
    
    pose_old = YoloWrapperTest(POSE_MODEL_PATH, (640, 640))
    pose_new = YoloWrapperTest(POSE_MODEL_PATH, (416, 416)) # <--- OPTIMIZACIÓN
    
    if pose_old.load() and pose_new.load():
        benchmark("Actual (640x640)", pose_old, img)
        benchmark("Propuesto (416x416)", pose_new, img)

    # 3. SIMULACIÓN ESTRATEGIA DE PROFUNDIDAD (MiDaS)
    print("\n3️⃣  ESTRATEGIA DE PROFUNDIDAD (MiDaS)")
    print("-" * 50)
    
    # Cargar MiDaS
    midas = cv2.dnn.readNet(MIDAS_MODEL_PATH)
    midas.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
    midas.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
    
    blob = cv2.dnn.blobFromImage(img, 1/255.0, (256, 256), (123.675, 116.28, 103.53), True, False)
    midas.setInput(blob)
    midas.forward() # Warmup
    
    # Medir tiempo de 1 inferencia MiDaS
    start = time.time()
    for _ in range(10): midas.forward()
    midas_time_ms = ((time.time() - start) / 10) * 1000
    
    print(f"   ⏱️  Costo de 1 MiDaS: {midas_time_ms:.1f} ms")
    
    # Calcular impacto en un ciclo de 5 frames
    # Escenario A: Correr MiDaS en CADA frame (5 veces)
    total_A = midas_time_ms * 5
    # Escenario B: Correr MiDaS 1 vez y reutilizar 4 veces (Costo casi 0 para reutilizar)
    total_B = midas_time_ms * 1 
    
    print(f"   🔴 Estrategia Actual (5 frames):  {total_A:.1f} ms gastados en profundidad")
    print(f"   🟢 Estrategia Nueva (5 frames):   {total_B:.1f} ms gastados en profundidad")
    print(f"   🛡️  Ahorro por ciclo: {total_A - total_B:.1f} ms liberados para YOLO")

if __name__ == "__main__":
    main()