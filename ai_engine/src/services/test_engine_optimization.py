import cv2
import time
import numpy as np
import os
import sys
import shutil

# Intentar importar librerías de NVIDIA (Standard en Jetson)
try:
    import tensorrt as trt
    import pycuda.driver as cuda
    import pycuda.autoinit
    TRT_AVAILABLE = True
except ImportError:
    print("⚠️ Librerías tensorrt/pycuda no encontradas. Se usará solo Ultralytics para exportar.")
    TRT_AVAILABLE = False

from ultralytics import YOLO

# ==============================================================================
# CONFIGURACIÓN
# ==============================================================================
MODELS_DIR = "/app/ai_engine/models"
ONNX_PATH = os.path.join(MODELS_DIR, "yolov8n.onnx")
ENGINE_PATH_416 = os.path.join(MODELS_DIR, "yolov8n_416.engine")

# ==============================================================================
# 1. CLASE WRAPPER TENSORRT (Infernecia Pura y Rápida)
# ==============================================================================
class TensorRTWrapper:
    def __init__(self, engine_path):
        self.engine_path = engine_path
        self.logger = trt.Logger(trt.Logger.WARNING)
        self.runtime = trt.Runtime(self.logger)
        self.engine = self.load_engine()
        self.context = self.engine.create_execution_context()
        self.inputs, self.outputs, self.bindings, self.stream = self.allocate_buffers()

    def load_engine(self):
        with open(self.engine_path, "rb") as f:
            return self.runtime.deserialize_cuda_engine(f.read())

    def allocate_buffers(self):
        inputs, outputs, bindings = [], [], []
        stream = cuda.Stream()
        for binding in self.engine:
            size = trt.volume(self.engine.get_binding_shape(binding))
            dtype = trt.nptype(self.engine.get_binding_dtype(binding))
            # Allocate host and device buffers
            host_mem = cuda.pagelocked_empty(size, dtype)
            device_mem = cuda.mem_alloc(host_mem.nbytes)
            bindings.append(int(device_mem))
            if self.engine.binding_is_input(binding):
                inputs.append({'host': host_mem, 'device': device_mem})
            else:
                outputs.append({'host': host_mem, 'device': device_mem})
        return inputs, outputs, bindings, stream

    def detect(self, img):
        # Preprocesamiento Básico (Resize + Normalize) para 416x416
        # Asume img es BGR
        resized = cv2.resize(img, (416, 416))
        input_data = resized.transpose((2, 0, 1)).ravel() / 255.0
        
        # Copiar a memoria paginada
        np.copyto(self.inputs[0]['host'], input_data)

        # Transferencia Host -> Device
        cuda.memcpy_htod_async(self.inputs[0]['device'], self.inputs[0]['host'], self.stream)
        
        # Ejecutar Inferencia
        self.context.execute_async_v2(bindings=self.bindings, stream_handle=self.stream.handle)
        
        # Transferencia Device -> Host
        cuda.memcpy_dtoh_async(self.outputs[0]['host'], self.outputs[0]['device'], self.stream)
        self.stream.synchronize()
        
        # Retornar output crudo (aquí harías el post-proceso de cajas)
        return self.outputs[0]['host']

# ==============================================================================
# 2. CLASE WRAPPER ONNX (La versión actual lenta)
# ==============================================================================
class YoloOnnxWrapper:
    def __init__(self, model_path, size):
        self.net = cv2.dnn.readNet(model_path)
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
        self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
        self.size = size

    def detect(self, img):
        blob = cv2.dnn.blobFromImage(img, 1/255.0, self.size, swapRB=True, crop=False)
        self.net.setInput(blob)
        self.net.forward()

# ==============================================================================
# 3. GENERADOR DE ENGINE
# ==============================================================================
def ensure_engine_exists():
    if os.path.exists(ENGINE_PATH_416):
        print(f"✅ Engine encontrado: {ENGINE_PATH_416}")
        return True
    
    print(f"⚠️ Engine no encontrado. Generando {ENGINE_PATH_416}...")
    print("⏳ Esto tomará unos 5-10 minutos en la Jetson Nano. ¡Paciencia!")
    
    try:
        # Usamos Ultralytics para exportar. Es más seguro que trtexec manual.
        # Bajamos el modelo .pt original (pequeño)
        model = YOLO("yolov8n.pt") 
        
        # Exportamos a TensorRT (format='engine') con imgsz=416 y half=True (FP16 es vital para Nano)
        print("🚀 Iniciando exportación (FP16, 416x416)...")
        path = model.export(format="engine", imgsz=416, half=True, device=0)
        
        # Mover al directorio correcto
        shutil.move(path, ENGINE_PATH_416)
        print("✅ Exportación completada exitosamente.")
        return True
    except Exception as e:
        print(f"❌ Falló la exportación: {e}")
        return False

# ==============================================================================
# MAIN TEST
# ==============================================================================
def main():
    print("\n=======================================================")
    print(" 🚀 TEST DE ACELERACIÓN: ONNX vs TENSORRT (.engine)")
    print("=======================================================")

    # 1. Preparar el modelo Engine
    if not ensure_engine_exists():
        return

    img = np.zeros((1080, 1920, 3), dtype=np.uint8)

    # 2. Benchmark ONNX Original (640x640)
    print("\n1️⃣  TEST ONNX (Actual - 640x640)")
    try:
        onnx_model = YoloOnnxWrapper(ONNX_PATH, (640, 640))
        # Warmup
        onnx_model.detect(img)
        
        start = time.time()
        for _ in range(30): onnx_model.detect(img)
        end = time.time()
        
        fps_onnx = 30 / (end - start)
        ms_onnx = ((end - start) / 30) * 1000
        print(f"   🐢 ONNX 640: {ms_onnx:.1f} ms | {fps_onnx:.1f} FPS")
    except Exception as e:
        print(f"   ❌ Error en ONNX: {e}")
        fps_onnx = 0.1

    # 3. Benchmark TensorRT Engine (416x416)
    if TRT_AVAILABLE:
        print("\n2️⃣  TEST TENSORRT ENGINE (Nuevo - 416x416 FP16)")
        try:
            trt_model = TensorRTWrapper(ENGINE_PATH_416)
            # Warmup
            trt_model.detect(img)
            
            start = time.time()
            for _ in range(50): trt_model.detect(img) # Más iters porque es rápido
            end = time.time()
            
            fps_trt = 50 / (end - start)
            ms_trt = ((end - start) / 50) * 1000
            print(f"   🐇 ENGINE 416: {ms_trt:.1f} ms | {fps_trt:.1f} FPS")
            
            speedup = fps_trt / fps_onnx
            print(f"\n🚀 MEJORA DE VELOCIDAD: {speedup:.1f}x veces más rápido")
            
        except Exception as e:
            print(f"   ❌ Error en TensorRT: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("\n⚠️ No se pudo correr el test de TensorRT (faltan librerías python).")
        print("   Pero si la exportación funcionó, puedes usar 'yolo predict model=yolov8n_416.engine' para probar.")

if __name__ == "__main__":
    main()