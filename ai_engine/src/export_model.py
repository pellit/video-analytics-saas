#!/usr/bin/env python3
"""
YOLO-NAS to ONNX Model Exporter

Este script descarga YOLO-NAS pre-entrenado y lo exporta a formato ONNX
para máxima velocidad en CPU.

Uso:
    python export_model.py [modelo] [tamaño]
    
Ejemplos:
    python export_model.py yolo_nas_s 640    # Small model, 640x640 (default)
    python export_model.py yolo_nas_m 640    # Medium model
    python export_model.py yolo_nas_l 640    # Large model (más preciso pero lento)
    python export_model.py yolo_nas_s 320    # Small con 320x320 (más rápido)
"""

import os
import sys
import json
import time
from pathlib import Path

# Output directory
MODELS_DIR = Path(__file__).parent.parent / "models"
MODELS_DIR.mkdir(exist_ok=True)

# Status file for tracking export progress
STATUS_FILE = MODELS_DIR / "export_status.json"


def update_status(status: str, progress: int = 0, error: str = None, model_info: dict = None):
    """Update export status file for frontend polling."""
    data = {
        "status": status,
        "progress": progress,
        "timestamp": time.time(),
        "error": error,
        "model_info": model_info
    }
    with open(STATUS_FILE, "w") as f:
        json.dump(data, f)


def get_available_models():
    """List available YOLO-NAS models."""
    return {
        "yolo_nas_s": {
            "name": "YOLO-NAS Small",
            "description": "Fastest, good for CPU. ~12M params",
            "recommended_for": "Real-time CPU inference"
        },
        "yolo_nas_m": {
            "name": "YOLO-NAS Medium",
            "description": "Balanced speed/accuracy. ~32M params",
            "recommended_for": "GPU or powerful CPU"
        },
        "yolo_nas_l": {
            "name": "YOLO-NAS Large",
            "description": "Most accurate but slowest. ~44M params",
            "recommended_for": "GPU with accuracy priority"
        }
    }


def check_onnx_model(model_name: str = "yolo_nas_s") -> dict:
    """Check if ONNX model exists and get info."""
    onnx_path = MODELS_DIR / f"{model_name}.onnx"
    
    if onnx_path.exists():
        stat = onnx_path.stat()
        return {
            "exists": True,
            "path": str(onnx_path),
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "created_at": stat.st_ctime,
            "modified_at": stat.st_mtime
        }
    return {"exists": False, "path": str(onnx_path)}


def export_yolo_nas(model_type: str = "yolo_nas_s", input_size: int = 640) -> dict:
    """
    Export YOLO-NAS model to ONNX format.
    
    Args:
        model_type: One of 'yolo_nas_s', 'yolo_nas_m', 'yolo_nas_l'
        input_size: Input image size (320 for speed, 640 for accuracy)
    
    Returns:
        dict with export result
    """
    try:
        update_status("starting", 5)
        
        # Validate model type
        if model_type not in ["yolo_nas_s", "yolo_nas_m", "yolo_nas_l"]:
            raise ValueError(f"Invalid model type: {model_type}. Use yolo_nas_s, yolo_nas_m, or yolo_nas_l")
        
        update_status("importing", 10)
        print("📦 Importing super_gradients...")
        
        try:
            from super_gradients.training import models
            from super_gradients.common.object_names import Models
        except ImportError as e:
            update_status("error", 0, error=f"super_gradients not installed: {e}")
            return {
                "success": False,
                "error": "super_gradients package not installed. Run: pip install super-gradients"
            }
        
        # Map model type to super_gradients Models enum
        model_map = {
            "yolo_nas_s": Models.YOLO_NAS_S,
            "yolo_nas_m": Models.YOLO_NAS_M,
            "yolo_nas_l": Models.YOLO_NAS_L
        }
        
        update_status("downloading", 20)
        print(f"⬇️ Downloading {model_type} pre-trained weights...")
        
        # Load model with COCO weights
        model = models.get(model_map[model_type], pretrained_weights="coco")
        
        update_status("preparing", 50)
        print(f"🔧 Preparing model for export (input size: {input_size}x{input_size})...")
        
        # Output path
        output_path = str(MODELS_DIR / f"{model_type}.onnx")
        
        update_status("exporting", 70)
        print(f"🚀 Exporting to ONNX: {output_path}")
        
        # Export to ONNX
        # preprocessing=True: Includes normalization in the model
        # postprocessing=True: Includes NMS in the model (very important!)
        model.export(
            output_path,
            preprocessing=True,
            postprocessing=True,
            input_image_shape=[input_size, input_size]
        )
        
        update_status("verifying", 90)
        print("✅ Verifying exported model...")
        
        # Verify the export
        model_info = check_onnx_model(model_type)
        
        if not model_info["exists"]:
            raise Exception("Export completed but file not found!")
        
        # Quick validation with onnxruntime
        try:
            import onnxruntime as ort
            session = ort.InferenceSession(output_path, providers=['CPUExecutionProvider'])
            input_name = session.get_inputs()[0].name
            input_shape = session.get_inputs()[0].shape
            output_names = [o.name for o in session.get_outputs()]
            
            model_info["input_name"] = input_name
            model_info["input_shape"] = input_shape
            model_info["output_names"] = output_names
            model_info["validated"] = True
            
            print(f"✅ ONNX model validated successfully!")
            print(f"   Input: {input_name} {input_shape}")
            print(f"   Outputs: {output_names}")
        except Exception as e:
            model_info["validated"] = False
            model_info["validation_error"] = str(e)
            print(f"⚠️ Could not validate with onnxruntime: {e}")
        
        update_status("completed", 100, model_info=model_info)
        print(f"🎉 Export completed! Model saved to: {output_path}")
        
        return {
            "success": True,
            "model_type": model_type,
            "input_size": input_size,
            "output_path": output_path,
            "model_info": model_info
        }
        
    except Exception as e:
        error_msg = str(e)
        update_status("error", 0, error=error_msg)
        print(f"❌ Export failed: {error_msg}")
        return {
            "success": False,
            "error": error_msg
        }


def get_export_status() -> dict:
    """Get current export status from file."""
    if STATUS_FILE.exists():
        try:
            with open(STATUS_FILE) as f:
                return json.load(f)
        except:
            pass
    return {"status": "idle", "progress": 0}


def list_models() -> dict:
    """List all available and installed models."""
    available = get_available_models()
    installed = {}
    
    for model_name in available.keys():
        info = check_onnx_model(model_name)
        if info["exists"]:
            installed[model_name] = info
    
    return {
        "available": available,
        "installed": installed
    }


# CLI interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Export YOLO-NAS to ONNX")
    parser.add_argument("command", nargs="?", default="export",
                       choices=["export", "status", "list", "check"],
                       help="Command to run")
    parser.add_argument("--model", "-m", default="yolo_nas_s",
                       choices=["yolo_nas_s", "yolo_nas_m", "yolo_nas_l"],
                       help="Model type to export")
    parser.add_argument("--size", "-s", type=int, default=640,
                       choices=[320, 416, 512, 640],
                       help="Input image size")
    
    args = parser.parse_args()
    
    if args.command == "export":
        result = export_yolo_nas(args.model, args.size)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["success"] else 1)
        
    elif args.command == "status":
        status = get_export_status()
        print(json.dumps(status, indent=2))
        
    elif args.command == "list":
        models = list_models()
        print(json.dumps(models, indent=2))
        
    elif args.command == "check":
        info = check_onnx_model(args.model)
        print(json.dumps(info, indent=2))
        sys.exit(0 if info.get("exists") else 1)
