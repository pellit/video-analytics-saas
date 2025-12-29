import os
import subprocess
import sys

# Rutas
PT_PATH = "/app/ai_engine/models/yolov8n.pt"
ONNX_416_PATH = "/app/ai_engine/models/yolov8n_416.onnx"

def install_and_export():
    print("🔧 [1/3] Verificando librería Ultralytics...")
    try:
        import ultralytics
        print("   ✅ Ultralytics ya está instalada.")
    except ImportError:
        print("   ⚠️ No encontrada. Instalando...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "ultralytics"])
        import ultralytics
    
    from ultralytics import YOLO

    print(f"\n📂 [2/3] Cargando modelo base: {PT_PATH}")
    if not os.path.exists(PT_PATH):
        print("   ❌ ERROR: No encuentro el archivo .pt. Asegúrate de haber hecho 'docker cp yolov8n.pt ...'")
        return

    model = YOLO(PT_PATH)

    print("\n🚀 [3/3] Exportando a ONNX (416x416)...")
    # opset=12 es el más compatible con OpenCV DNN
    path = model.export(format="onnx", imgsz=416, opset=12, device=0)

    # Asegurar nombre correcto
    if path != ONNX_416_PATH:
        if os.path.exists(ONNX_416_PATH):
            os.remove(ONNX_416_PATH)
        os.rename(path, ONNX_416_PATH)

    print(f"\n✅ ¡ÉXITO! Modelo generado en: {ONNX_416_PATH}")

if __name__ == "__main__":
    install_and_export()