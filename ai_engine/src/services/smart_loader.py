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

# Fix para encontrar jetson.inference compilado
sys.path.append("/usr/local/lib/python3.11/site-packages")

class SmartModelLoader:
    def __init__(self, model_path_base, task='detect', target_imgsz=640):
        self.model = None
        self.net = None # Para jetson.inference
        self.backend = None
        self.target_imgsz = int(target_imgsz)
        self.model_filename = "Ninguno"
        self.task = task
        
        # Rutas
        path_engine = f"{model_path_base}.engine"
        path_onnx = f"{model_path_base}.onnx"
        path_fixed = f"{model_path_base}_fixed.onnx"
        
        logger.info(f"[INIT] Loader Inteligente: {model_path_base}")

        # ==============================================================================
        # ESTRATEGIA 1: JETSON INFERENCE con ENGINE (Velocidad Nativa)
        # ==============================================================================
        # Esta es la forma correcta en Jetson Nano con Python 3.11
        if os.path.exists(path_engine):
            try:
                import jetson.inference
                import jetson.utils
                logger.info(f"[TRY] Cargando ENGINE con jetson.inference: {path_engine}")
                
                self.net = jetson.inference.detectNet(
                    argv=[
                        f"--model={path_engine}",  # Cargamos directo el engine
                        f"--labels={os.path.join(os.path.dirname(path_engine), 'classes.txt')}", 
                        "--input-blob=images", 
                        "--output-cvg=output_0", 
                        "--output-bbox=output_0"
                    ],
                    threshold=0.3
                )
                self.backend = 'jetson_inference'
                self.model_filename = os.path.basename(path_engine)
                logger.info("[EXITO] ENGINE cargado con jetson.inference (GPU)")
                return
            except Exception as e:
                logger.error(f"[FAIL] jetson.inference falló con engine: {e}")

        # ==============================================================================
        # ESTRATEGIA 2: JETSON INFERENCE con ONNX (Compilación Automática)
        # ==============================================================================
        # Si no hay engine o falló, le damos el ONNX. 
        # jetson.inference lo compilará a engine él mismo (tarda 1 min la primera vez).
        if os.path.exists(path_onnx):
            try:
                import jetson.inference
                import jetson.utils
                logger.info(f"[TRY] Cargando ONNX con jetson.inference: {path_onnx}")
                
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
                logger.info("[EXITO] ONNX cargado con jetson.inference (Se auto-compilará)")
                return
            except Exception as e:
                logger.error(f"[FAIL] jetson.inference falló con ONNX: {e}")

        # ==============================================================================
        # ESTRATEGIA 3: ULTRALYTICS (Solo ONNX Fallback)
        # ==============================================================================
        # Usamos Ultralytics solo para ONNX, ya que para Engine pide 'tensorrt' pip package
        try:
            from ultralytics import YOLO
            
            # Usar fixed si existe
            target_onnx = path_fixed if os.path.exists(path_fixed) else path_onnx

            if os.path.exists(target_onnx):
                logger.info(f"[TRY] Fallback Ultralytics ONNX: {target_onnx}")
                try:
                    self.model = YOLO(target_onnx, task=task)
                    self.backend = 'ultralytics_onnx'
                    self.model_filename = os.path.basename(target_onnx)
                    logger.info("[EXITO] Ultralytics ONNX cargado.")
                    return
                except Exception as e:
                    logger.error(f"[FAIL] Ultralytics ONNX falló: {e}")
                    
                    # Auto-Reparación ONNX
                    if not os.path.exists(path_fixed):
                        logger.info("[FIX] Reparando ONNX...")
                        try:
                            cmd = ["onnxslim", path_onnx, path_fixed]
                            subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            self.model = YOLO(path_fixed, task=task)
                            self.backend = 'ultralytics_onnx'
                            logger.info("[EXITO] Modelo reparado cargado.")
                            return
                        except:
                            pass

        except ImportError:
            pass

        raise RuntimeError(f"FATAL: No se pudo cargar {model_path_base}")

    def predict(self, frame, conf_thres=0.5):
        t_start = time.time()
        annotated_frame = frame
        
        # --- JETSON INFERENCE (GPU NATIVA) ---
        if self.backend == 'jetson_inference':
            import jetson.utils
            # BGR -> RGB
            img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            cuda_img = jetson.utils.cudaFromNumpy(img_rgb)
            
            # Detectar
            self.net.Detect(cuda_img, overlay='box,labels,conf')
            
            # RGB -> BGR
            annotated_frame = cv2.cvtColor(jetson.utils.cudaToNumpy(cuda_img), cv2.COLOR_RGB2BGR)

        # --- ULTRALYTICS (CPU/ONNX) ---
        elif 'ultralytics' in str(self.backend):
            results = self.model(frame, imgsz=self.target_imgsz, conf=conf_thres, verbose=False)
            annotated_frame = results[0].plot()

        t_end = time.time()
        inference_time = (t_end - t_start) * 1000
        fps = 1.0 / (t_end - t_start) if (t_end - t_start) > 0 else 0
        
        self._draw_stats(annotated_frame, fps, inference_time)
        return annotated_frame

    def _draw_stats(self, img, fps, ms):
        color = (0, 255, 0) if self.backend == 'jetson_inference' else (0, 165, 255)
        cv2.rectangle(img, (5, 5), (350, 85), (0, 0, 0), -1)
        lines = [
            f"Model: {self.model_filename}",
            f"Backend: {str(self.backend).upper()}",
            f"Time: {ms:.1f}ms | FPS: {fps:.1f}"
        ]
        y = 30
        for line in lines:
            cv2.putText(img, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            y += 25