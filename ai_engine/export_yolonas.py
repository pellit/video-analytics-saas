#!/usr/bin/env python3
"""
Script para exportar YOLO-NAS a formato ONNX optimizado.
Ejecutar localmente para generar el archivo .onnx

Uso:
    python export_yolonas.py [--size small|medium|large] [--input-size 640]

El archivo generado debe copiarse al servidor de producción.
"""

import argparse
import sys

def main():
    parser = argparse.ArgumentParser(description='Exportar YOLO-NAS a ONNX')
    parser.add_argument('--size', choices=['small', 'medium', 'large'], default='small',
                        help='Tamaño del modelo (small=rápido, large=preciso)')
    parser.add_argument('--input-size', type=int, default=640,
                        help='Tamaño de entrada (640 estándar, 320 para máxima velocidad)')
    parser.add_argument('--output', type=str, default=None,
                        help='Ruta de salida del archivo ONNX')
    args = parser.parse_args()

    try:
        from super_gradients.training import models
        from super_gradients.common.object_names import Models
    except ImportError:
        print("❌ Error: Necesitas instalar super-gradients")
        print("   pip install super-gradients onnx")
        sys.exit(1)

    # Mapeo de tamaños
    model_map = {
        'small': Models.YOLO_NAS_S,
        'medium': Models.YOLO_NAS_M,
        'large': Models.YOLO_NAS_L
    }

    model_name = model_map[args.size]
    input_size = args.input_size
    output_path = args.output or f"yolo_nas_{args.size[0]}.onnx"

    print(f"⏳ Descargando y cargando YOLO-NAS {args.size.capitalize()}...")
    model = models.get(model_name, pretrained_weights="coco")

    print(f"🔧 Configuración:")
    print(f"   - Modelo: YOLO-NAS {args.size.capitalize()}")
    print(f"   - Input: {input_size}x{input_size}")
    print(f"   - Output: {output_path}")

    print(f"\n🚀 Exportando a ONNX...")
    
    model.export(
        output_path,
        preprocessing=True,   # Incluye normalización
        postprocessing=True,  # Incluye NMS (Non-Max Suppression)
        input_image_shape=[input_size, input_size]
    )

    print(f"\n✅ ¡Listo! Archivo '{output_path}' creado.")
    print(f"\n📋 Próximos pasos:")
    print(f"   1. Copia '{output_path}' a ai_engine/models/")
    print(f"   2. El worker lo detectará automáticamente")


if __name__ == "__main__":
    main()
