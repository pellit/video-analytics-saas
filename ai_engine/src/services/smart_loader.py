import os
import time
import logging
import subprocess
import cv2
import numpy as np

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SmartLoader")

class SmartModelLoader:
    def __init__(self, model_path_base, task='detect', target_imgsz=640):
        self.model = None
        self.backend = None
        self.target_imgsz = int(target_imgsz)
        self.model_filename = "Ninguno"
        self.task = task
        
        # Rutas
        path_engine = f"{model_path_base}.engine"
        path_onnx = f"{model_path_base}.onnx"
        path_fixed = f"{model_path_base}_fixed.onnx"
        
        logger.info(f"[INIT] Configurando loader para: {model_path_base}")

        # Intentamos importar Ultralytics
        try:
            from ultralytics import YOLO
        except ImportError:
            raise ImportError("CRITICO: Necesitas instalar la librería. Ejecuta: pip install ultralytics")

        # ==========================================================
        # PRIORIDAD 1: ENGINE (TensorRT - GPU Pura)
        # ==========================================================
        if os.path.exists(path_engine):
            logger.info(f"[TRY] Engine detectado: {path_engine}")
            try:
                # task='detect' o 'pose' es importante para que parse la salida bien
                self.model = YOLO(path_engine, task=task)
                self.backend = 'ultralytics_engine'
                self.model_filename = os.path.basename(path_engine)
                
                # Calentamiento rápido
                logger.info("[WARMUP] Calentando motor TensorRT...")
                dummy = np.zeros((self.target_imgsz, self.target_imgsz, 3), dtype=np.uint8)
                self.model(dummy, verbose=False)
                
                logger.info(f"[EXITO] Cargado TENSORRT ENGINE: {self.model_filename}")
                return # Salimos, ya tenemos lo mejor
            except Exception as e:
                logger.error(f"[ERROR] Engine falló al cargar: {e}. Pasando a ONNX...")

        # ==========================================================
        # PRIORIDAD 2: ONNX (Fallback con Auto-Reparación)
        # ==========================================================
        
        # Si ya existe un fixed, úsalo
        current_onnx = path_fixed if os.path.exists(path_fixed) else path_onnx

        if os.path.exists(current_onnx):
            logger.info(f"[TRY] Cargando ONNX con Ultralytics: {current_onnx}")
            try:
                self.model = YOLO(current_onnx, task=task)
                self.backend = 'ultralytics_onnx'
                self.model_filename = os.path.basename(current_onnx)
                logger.info(f"[EXITO] Cargado ONNX")
                
            except Exception as e:
                logger.error(f"[ERROR] ONNX corrupto: {e}")
                
                # --- AUTO-REPARACIÓN ONNXSLIM ---
                logger.info("[FIX] Ejecutando onnxslim para reparar modelo...")
                try:
                    cmd = ["onnxslim", path_onnx, path_fixed]
                    subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    
                    # Cargar el reparado
                    self.model = YOLO(path_fixed, task=task)
                    self.backend = 'ultralytics_onnx_fixed'
                    self.model_filename = os.path.basename(path_fixed)
                    logger.info(f"[EXITO] Modelo REPARADO cargado.")
                    
                except Exception as fix_err:
                    raise RuntimeError(f"FATAL: No se pudo cargar ni reparar el modelo. {fix_err}")

        if self.model is None:
            raise FileNotFoundError(f"No se encontraron modelos válidos en {model_path_base}")

    def predict(self, frame, conf_thres=0.5):
        t_start = time.time()
        
        # Ultralytics maneja todo: preproceso, inferencia y NMS
        # imgsz: forzamos el tamaño para que coincida con el engine
        results = self.model(frame, 
                             imgsz=self.target_imgsz, 
                             conf=conf_thres, 
                             verbose=False)
        
        # Extraemos el frame pintado para mantener compatibilidad con tu API
        annotated_frame = results[0].plot()

        t_end = time.time()
        inference_time = (t_end - t_start) * 1000
        fps = 1.0 / (t_end - t_start) if (t_end - t_start) > 0 else 0

        self._draw_stats(annotated_frame, fps, inference_time)
        return annotated_frame

    def _draw_stats(self, img, fps, ms):
        # Verde si es Engine, Naranja si es ONNX
        color = (0, 255, 0) if 'engine' in self.backend else (0, 165, 255)
        
        lines = [
            f"Model: {self.model_filename}",
            f"Backend: {self.backend.upper()}",
            f"Time: {ms:.1f}ms | FPS: {fps:.1f}"
        ]
        
        cv2.rectangle(img, (5, 5), (350, 85), (0, 0, 0), -1)
        y = 30
        for line in lines:
            cv2.putText(img, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            y += 25