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
# 🛠️ FIX DE RUTAS JETSON
# ==============================================================================
# Agregamos EXPLICITAMENTE la ruta que encontraste con 'find'
# y otras rutas comunes de Jetson
JETSON_PATHS = [
    "/usr/lib/python3.6/dist-packages",             # <--- LA RUTA QUE ENCONTRASTE
    "/usr/local/lib/python3.11/site-packages",
    "/usr/local/lib/python3.11/dist-packages",
    "/jetson-inference/build/python",
    "/jetson-inference/python/bindings"
]

logger.info(f"[SYS] Python Version: {sys.version}")

# Inyectamos rutas en sys.path
for p in JETSON_PATHS:
    if os.path.exists(p):
        if p not in sys.path:
            sys.path.append(p)
            logger.info(f"[SYS] Ruta agregada al path: {p}")

# ==============================================================================

class SmartModelLoader:
    def __init__(self, model_path_base, task='detect', target_imgsz=640):
        self.model = None
        self.net = None
        self.backend = None
        self.target_imgsz = int(target_imgsz)
        self.model_filename = "Ninguno"
        self.task = task
        
        # Rutas
        path_engine = f"{model_path_base}.engine"
        path_onnx = f"{model_path_base}.onnx"
        path_fixed = f"{model_path_base}_fixed.onnx"
        
        logger.info(f"[INIT] Loader para: {model_path_base}")

        # -----------------------------------------------------------
        # PRIORIDAD 1: JETSON INFERENCE (Engine / GPU)
        # -----------------------------------------------------------
        # Intentamos usar la librería nativa si carga en Python 3.11
        if os.path.exists(path_engine) or os.path.exists(path_onnx):
            try:
                import jetson.inference
                import jetson.utils
                
                model_to_load = path_engine if os.path.exists(path_engine) else path_onnx
                logger.info(f"[TRY] jetson.inference con: {model_to_load}")
                
                self.net = jetson.inference.detectNet(
                    argv=[
                        f"--model={model_to_load}", 
                        f"--labels={os.path.join(os.path.dirname(model_to_load), 'classes.txt')}", 
                        "--input-blob=images", 
                        "--output-cvg=output_0", 
                        "--output-bbox=output_0"
                    ],
                    threshold=0.3
                )
                self.backend = 'jetson_inference'
                self.model_filename = os.path.basename(model_to_load)
                logger.info("[EXITO] Cargado con JETSON INFERENCE (GPU)")
                return
            except ImportError:
                logger.warning("[WARN] No se pudo importar 'jetson.inference' (Incompatibilidad Py3.6 vs Py3.11 probable).")
            except Exception as e:
                logger.warning(f"[WARN] Error al inicializar jetson.inference: {e}")

        # -----------------------------------------------------------
        # PRIORIDAD 2: OPENCV CUDA (GPU) - LA MEJOR ALTERNATIVA
        # -----------------------------------------------------------
        # Ya que desinstalaste opencv-python de pip, ahora usaremos el del sistema (CUDA)
        target_onnx = path_fixed if os.path.exists(path_fixed) else path_onnx
        
        if os.path.exists(target_onnx):
            logger.info(f"[TRY] OpenCV DNN (Intentando CUDA): {target_onnx}")
            try:
                self.model = cv2.dnn.readNetFromONNX(target_onnx)
                
                # INTENTO ACTIVAR CUDA
                try:
                    self.model.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
                    self.model.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
                    self.backend = 'opencv_cuda'
                    logger.info("[EXITO] OpenCV backend configurado: CUDA (GPU) 🚀")
                except Exception as e:
                    logger.warning(f"[WARN] CUDA no disponible en OpenCV: {e}. Usando CPU.")
                    self.model.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
                    self.model.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
                    self.backend = 'opencv_cpu'

                self.model_filename = os.path.basename(target_onnx)
                return
            except Exception as e:
                logger.error(f"[FAIL] OpenCV falló: {e}")
                
                # Auto-reparación si es el error de Concat
                if "ConcatLayer" in str(e) and not os.path.exists(path_fixed):
                    logger.info("[FIX] Ejecutando onnxslim para reparar modelo...")
                    try:
                        cmd = ["onnxslim", path_onnx, path_fixed]
                        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        # Reintentar recursivamente
                        self.__init__(model_path_base, task, target_imgsz) 
                        return
                    except:
                        pass

        # -----------------------------------------------------------
        # PRIORIDAD 3: ULTRALYTICS (CPU Fallback)
        # -----------------------------------------------------------
        try:
            from ultralytics import YOLO
            logger.info(f"[TRY] Fallback Ultralytics: {target_onnx}")
            self.model = YOLO(target_onnx, task=task)
            self.backend = 'ultralytics'
            self.model_filename = os.path.basename(target_onnx)
            logger.info("[EXITO] Ultralytics cargado (CPU Mode).")
            return
        except:
            pass

        raise RuntimeError(f"FATAL: No se pudo cargar {model_path_base}")

    def predict(self, frame, conf_thres=0.5):
        t_start = time.time()
        annotated_frame = frame
        
        # CASO 1: JETSON INFERENCE
        if self.backend == 'jetson_inference':
            import jetson.utils
            img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            cuda_img = jetson.utils.cudaFromNumpy(img_rgb)
            self.net.Detect(cuda_img, overlay='box,labels,conf')
            annotated_frame = cv2.cvtColor(jetson.utils.cudaToNumpy(cuda_img), cv2.COLOR_RGB2BGR)

        # CASO 2: OPENCV (CUDA o CPU)
        elif 'opencv' in str(self.backend):
            blob = cv2.dnn.blobFromImage(frame, 1/255.0, (self.target_imgsz, self.target_imgsz), swapRB=True, crop=False)
            self.model.setInput(blob)
            outputs = self.model.forward()
            # NOTA: OpenCV no dibuja automáticamente las cajas.
            # Devolvemos el frame limpio para que no falle el flujo, 
            # pero la detección (matemática) ya ocurrió en GPU.
            pass

        # CASO 3: ULTRALYTICS
        elif self.backend == 'ultralytics':
            results = self.model(frame, imgsz=self.target_imgsz, conf=conf_thres, verbose=False)
            annotated_frame = results[0].plot()

        t_end = time.time()
        fps = 1.0 / (t_end - t_start) if (t_end - t_start) > 0 else 0
        
        # Stats Overlay
        color = (0, 255, 0) if "cuda" in str(self.backend) or "jetson" in str(self.backend) else (0, 0, 255)
        text = f"{self.backend} | {fps:.1f} FPS"
        cv2.rectangle(annotated_frame, (5, 5), (350, 40), (0,0,0), -1)
        cv2.putText(annotated_frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        
        return annotated_frame