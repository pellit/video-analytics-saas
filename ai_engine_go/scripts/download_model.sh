#!/bin/bash
# Script to download and convert YOLOv8n to ONNX format

set -e

MODEL_DIR="./models"
mkdir -p "$MODEL_DIR"

echo "📦 Installing ultralytics..."
pip install ultralytics onnx onnxruntime -q

echo "🔄 Converting YOLOv8n to ONNX..."
python3 << 'EOF'
from ultralytics import YOLO

# Load YOLOv8n model
model = YOLO('yolov8n.pt')

# Export to ONNX
model.export(format='onnx', imgsz=640, opset=17, simplify=True)
print("✅ Model exported to yolov8n.onnx")
EOF

# Move to models directory
mv yolov8n.onnx "$MODEL_DIR/"

echo "✅ Model ready at $MODEL_DIR/yolov8n.onnx"
