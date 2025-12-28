import cv2
import time
import numpy as np
import os

# ==============================================================================
# CONFIGURACIÓN
# ==============================================================================
# Usamos el ONNX estándar que ya tienes. 
# OpenCV es capaz de redimensionar la entrada dinámicamente.
MODEL_PATH = "/app/ai_engine/models/yolov8n.onnx"

class BenchmarkRunner:
    def __init__(self):
        self.img_dummy = np.zeros((1080, 1920, 3), dtype=np.uint8)

    def run_test(self, test_name, input_size, enable_fp16):
        print(f"\n🔹 PROBANDO: {test_name}")
        print(f"   Config: Input={input_size} | Mode={'FP16 (Rápido)' if enable_fp16 else 'FP32 (Estándar)'}")
        
        if not os.path.exists(MODEL_PATH):
            print(f"❌ Error: No encuentro el modelo en {MODEL_PATH}")
            return 0

        try:
            # 1. Cargar Red
            net = cv2.dnn.readNet(MODEL_PATH)
            
            # 2. Configurar Backend (CUDA)
            net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
            
            # 3. Configurar Precisión (El secreto de la velocidad)
            if enable_fp16:
                net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA_FP16)
            else:
                net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
            
            # 4. Preprocesamiento (Blob)
            blob = cv2.dnn.blobFromImage(
                self.img_dummy, 
                1/255.0, 
                input_size, 
                swapRB=True, 
                crop=False
            )
            net.setInput(blob)
            
            # 5. Warmup (Calentamiento)
            print("   🔥 Calentando GPU...")
            for _ in range(5):
                net.forward()

            # 6. Benchmark Real
            iters = 50
            print(f"   🚀 Ejecutando {iters} inferencias...")
            
            t_start = time.time()
            for _ in range(iters):
                # Es vital volver a setear el input si cambiamos algo, 
                # aunque aquí es estático, simula el flujo real.
                net.setInput(blob) 
                output = net.forward()
            t_end = time.time()
            
            # Cálculos
            total_time = t_end - t_start
            avg_ms = (total_time / iters) * 1000
            fps = iters / total_time
            
            print(f"   🏁 RESULTADO: {avg_ms:.1f} ms | \033[92m{fps:.2f} FPS\033[0m")
            return fps

        except Exception as e:
            print(f"❌ Error durante el test: {e}")
            return 0

def main():
    print("=======================================================")
    print(" 🏎️  TEST DE VELOCIDAD: OPTIMIZACIÓN OPENCV CUDA FP16")
    print("=======================================================")
    
    runner = BenchmarkRunner()
    
    # 1. Escenario Base (Lo que tenías antes)
    fps_base = runner.run_test(
        test_name="BASE (Lo que tenías antes)", 
        input_size=(640, 640), 
        enable_fp16=False
    )
    
    # 2. Escenario Optimizado (Lo que tendrás ahora)
    fps_opt = runner.run_test(
        test_name="OPTIMIZADO (Tu nueva config)", 
        input_size=(416, 416), 
        enable_fp16=True
    )
    
    print("\n" + "="*50)
    print(" RESUMEN FINAL")
    print("="*50)
    print(f"🐢 Antes (640 FP32):  {fps_base:.2f} FPS")
    print(f"🐇 Ahora (416 FP16):  {fps_opt:.2f} FPS")
    
    if fps_base > 0:
        mejora = fps_opt / fps_base
        print(f"\n🚀 MEJORA DE VELOCIDAD: {mejora:.1f}x veces más rápido")
    
    if fps_opt > 12:
        print("\n✅ CONCLUSIÓN: El sistema es viable para tiempo real.")
    else:
        print("\n⚠️ CONCLUSIÓN: Aún falta velocidad (¿Seguro que es Maxwell/CUDA?)")

if __name__ == "__main__":
    main()