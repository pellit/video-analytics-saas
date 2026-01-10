import os
import sys
import time
import logging
import numpy as np
import cv2

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SmartLoader")

# --- FIX PARA JETSON INFERENCE ---
# Forzamos la ruta donde el Dockerfile compiló la librería
sys.path.append("/usr/local/lib/python3.11/site-packages")

class SmartModelLoader:
    def __init__(self, model_path_base, task='detect', target_imgsz=640):
        self.model = None
        self.backend = None
        self.target_imgsz = int(target_imgsz)
        self.model_filename = "Ninguno"
        self.task = task
        
        # Rutas posibles
        path_engine = f"{model_path_base}.engine"
        path_pt = f"{model_path_base}.pt"     # Recomendado si falla el engine
        path_onnx = f"{model_path_base}.onnx"
        
        logger.info(f"[INIT] Loader Ultralytics activado para: {model_path_base}")

        # Intentar importar librerías clave
        self.has_ultralytics = False
        try:
            from ultralytics import YOLO
            self.has_ultralytics = True
        except ImportError:
            logger.warning("[WARN] 'ultralytics' no instalado. Ejecuta: pip install ultralytics")

        # ==============================================================================
        # ESTRATEGIA 1: ULTRALYTICS (Engine > PT > ONNX)
        # ==============================================================================
        if self.has_ultralytics:
            from ultralytics import YOLO

            # 1.1 Intentar ENGINE (Lo más rápido)
            if os.path.exists(path_engine):
                try:
                    logger.info(f"[TRY] Cargando Engine con Ultralytics: {path_engine}")
                    # Ultralytics intentará usar el backend TensorRT
                    self.model = YOLO(path_engine, task=task)
                    self.backend = 'ultralytics'
                    self.model_filename = os.path.basename(path_engine)
                    
                    # Warmup
                    self.model(np.zeros((640,640,3), dtype='uint8'), verbose=False)
                    logger.info("[EXITO] ENGINE cargado correctamente.")
                    return
                except Exception as e:
                    logger.error(f"[FAIL] Engine falló (Posiblemente falte tensorrt en Py3.11): {e}")

            # 1.2 Intentar PT (Original de PyTorch - Muy robusto)
            # Si tienes el .pt, súbelo a la carpeta. Es a prueba de balas.
            if os.path.exists(path_pt):
                try:
                    logger.info(f"[TRY] Cargando PyTorch Model: {path_pt}")
                    self.model = YOLO(path_pt, task=task)
                    self.backend = 'ultralytics'
                    self.model_filename = os.path.basename(path_pt)
                    logger.info("[EXITO] PT cargado correctamente.")
                    return
                except Exception as e:
                    logger.error(f"[FAIL] PT falló: {e}")

            # 1.3 Intentar ONNX con Ultralytics (Mejor parser que OpenCV)
            if os.path.exists(path_onnx):
                try:
                    logger.info(f"[TRY] Cargando ONNX con Ultralytics: {path_onnx}")
                    self.model = YOLO(path_onnx, task=task)
                    self.backend = 'ultralytics'
                    self.model_filename = os.path.basename(path_onnx)
                    logger.info("[EXITO] ONNX (Ultralytics) cargado.")
                    return
                except Exception as e:
                    logger.error(f"[FAIL] ONNX Ultralytics falló: {e}")

        # ==============================================================================
        # ESTRATEGIA 2: JETSON INFERENCE (Nativo NVIDIA)
        # ==============================================================================
        # Intentamos forzar la carga si Ultralytics falló o no está
        if os.path.exists(path_onnx):
            try:
                import jetson.inference
                import jetson.utils
                logger.info(f"[TRY] Intentando jetson.inference (Plan B): {path_onnx}")
                
                self.net = jetson.inference.detectNet(
                    argv=[
                        f"--model={path_onnx}", 
                        f"--labels={os.path.join(os.path.dirname(path_onnx), 'classes.txt')}", 
                        "--input-blob=images", 
                        "--output-cvg=output_0", 
                        "--output-bbox=output_0"
                    ],
                    threshold=0.3
                )
                self.backend = 'jetson_inference'
                self.model_filename = os.path.basename(path_onnx)
                logger.info("[EXITO] Cargado con jetson.inference")
                return
            except ImportError:
                logger.error("[FAIL] jetson.inference no se pudo importar (revisar PYTHONPATH)")
            except Exception as e:
                logger.error(f"[FAIL] jetson.inference error: {e}")

        # ==============================================================================
        # ESTRATEGIA 3: OPENCV (Último recurso - ya sabemos que falla con este modelo)
        # ==============================================================================
        # (Omitido intencionalmente porque ya comprobamos que tu modelo rompe OpenCV 4.10)
        
        raise RuntimeError(f"FATAL: No se pudo cargar el modelo {model_path_base} con ningún backend (Ultralytics/Jetson/OpenCV).")

    def predict(self, frame, conf_thres=0.5):
        t_start = time.time()
        annotated_frame = frame
        
        # --- ULTRALYTICS BACKEND ---
        if self.backend == 'ultralytics':
            # Inferencia (Engine, PT u ONNX)
            results = self.model(frame, imgsz=self.target_imgsz, conf=conf_thres, verbose=False)
            annotated_frame = results[0].plot()

        # --- JETSON INFERENCE BACKEND ---
        elif self.backend == 'jetson_inference':
            import jetson.utils
            img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            cuda_img = jetson.utils.cudaFromNumpy(img_rgb)
            self.net.Detect(cuda_img, overlay='box,labels,conf')
            annotated_frame = cv2.cvtColor(jetson.utils.cudaToNumpy(cuda_img), cv2.COLOR_RGB2BGR)

        t_end = time.time()
        inference_time = (t_end - t_start) * 1000
        fps = 1.0 / (t_end - t_start) if (t_end - t_start) > 0 else 0
        
        self._draw_stats(annotated_frame, fps, inference_time)
        return annotated_frame

    def _draw_stats(self, img, fps, ms):
        cv2.rectangle(img, (5, 5), (350, 85), (0, 0, 0), -1)
        lines = [
            f"Model: {self.model_filename}",
            f"Backend: {str(self.backend).upper()}",
            f"Time: {ms:.1f}ms | FPS: {fps:.1f}"
        ]
        y = 30
        for line in lines:
            cv2.putText(img, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            y += 25