import os
import sys
import time
import logging
import subprocess
import cv2
import numpy as np

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SmartLoader")

# ==============================================================================
# 🛠️ FIX DE RUTAS JETSON (Basado en tu Dockerfile)
# ==============================================================================
# Rutas donde el Dockerfile instaló la librería
JETSON_PATHS = [
    "/usr/local/lib/python3.11/site-packages",  # Ruta principal del 'make install'
    "/usr/local/lib/python3.11/dist-packages",  # Ruta del enlace simbólico
    "/usr/lib/python3.11/site-packages",
    "/jetson-inference/python/bindings"         # Ruta source por si acaso
]

logger.info(f"[SYS] Python Version: {sys.version}")
logger.info(f"[SYS] Current PYTHONPATH: {sys.path}")

jetson_found = False
for p in JETSON_PATHS:
    target = os.path.join(p, "jetson")
    if os.path.exists(target):
        logger.info(f"[SYS] ✅ Librería 'jetson' encontrada en: {target}")
        if p not in sys.path:
            sys.path.append(p)
            logger.info(f"[SYS] -> Agregado {p} al path")
        jetson_found = True
        
        # Verificación extra: ¿Tiene __init__.py?
        if not os.path.exists(os.path.join(target, "__init__.py")):
            logger.warning(f"[SYS] ⚠️ ALERTA: {target} no tiene __init__.py. Python podría ignorarlo.")
    else:
        logger.debug(f"[SYS] No está en: {p}")

if not jetson_found:
    logger.critical("[SYS] ❌ CRÍTICO: No se encontró la carpeta 'jetson' en ninguna ruta esperada.")

# ==============================================================================

class SmartModelLoader:
    def __init__(self, model_path_base, task='detect', target_imgsz=640):
        self.model = None
        self.net = None
        self.backend = None
        self.target_imgsz = int(target_imgsz)
        self.model_filename = "Ninguno"
        self.task = task
        
        # Definir archivos
        path_engine = f"{model_path_base}.engine"
        path_onnx = f"{model_path_base}.onnx"
        path_fixed = f"{model_path_base}_fixed.onnx"
        
        logger.info(f"[INIT] Loader para: {model_path_base}")

        # -----------------------------------------------------------
        # ESTRATEGIA 1: JETSON INFERENCE (ENGINE) - La Prioridad
        # -----------------------------------------------------------
        if os.path.exists(path_engine):
            try:
                # Importación diferida para no romper si falla
                import jetson.inference
                import jetson.utils
                
                logger.info(f"[TRY] Cargando ENGINE con jetson.inference: {path_engine}")
                self.net = jetson.inference.detectNet(
                    argv=[
                        f"--model={path_engine}", 
                        f"--labels={os.path.join(os.path.dirname(path_engine), 'classes.txt')}", 
                        "--input-blob=images", 
                        "--output-cvg=output_0", 
                        "--output-bbox=output_0"
                    ],
                    threshold=0.3
                )
                self.backend = 'jetson_inference'
                self.model_filename = os.path.basename(path_engine)
                logger.info("[EXITO] ENGINE cargado (GPU Nativa)")
                return
            except ImportError:
                logger.error("[FAIL] No se pudo importar 'jetson.inference'.")
            except Exception as e:
                logger.error(f"[FAIL] Error cargando engine: {e}")

        # -----------------------------------------------------------
        # ESTRATEGIA 2: ULTRALYTICS (FALLBACK)
        # -----------------------------------------------------------
        # Usamos Ultralytics para el ONNX si el engine falló
        target_onnx = path_fixed if os.path.exists(path_fixed) else path_onnx
        
        if os.path.exists(target_onnx):
            try:
                from ultralytics import YOLO
                logger.info(f"[TRY] Fallback Ultralytics ONNX: {target_onnx}")
                self.model = YOLO(target_onnx, task=task)
                self.backend = 'ultralytics_onnx'
                self.model_filename = os.path.basename(target_onnx)
                logger.info("[EXITO] Ultralytics ONNX cargado.")
                return
            except Exception as e:
                logger.error(f"[FAIL] Ultralytics falló: {e}")

        raise RuntimeError(f"FATAL: No se pudo cargar modelo {model_path_base}")

    def predict(self, frame, conf_thres=0.5):
        t_start = time.time()
        annotated_frame = frame
        
        if self.backend == 'jetson_inference':
            import jetson.utils
            # Conversión necesaria: OpenCV (BGR) -> Jetson (RGB CUDA)
            img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            cuda_img = jetson.utils.cudaFromNumpy(img_rgb)
            
            self.net.Detect(cuda_img, overlay='box,labels,conf')
            
            # Recuperar imagen: Jetson (RGB CUDA) -> OpenCV (BGR)
            annotated_frame = cv2.cvtColor(jetson.utils.cudaToNumpy(cuda_img), cv2.COLOR_RGB2BGR)

        elif 'ultralytics' in str(self.backend):
            results = self.model(frame, imgsz=self.target_imgsz, conf=conf_thres, verbose=False)
            annotated_frame = results[0].plot()

        t_end = time.time()
        fps = 1.0 / (t_end - t_start) if (t_end - t_start) > 0 else 0
        
        # Stats Overlay
        text = f"{self.backend} | {fps:.1f} FPS"
        cv2.rectangle(annotated_frame, (5, 5), (300, 40), (0,0,0), -1)
        cv2.putText(annotated_frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        return annotated_frame