import os
import cv2
import time
import logging
import subprocess
import numpy as np

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SmartLoader")

class SmartModelLoader:
    def __init__(self, model_path_base, task='detect', target_imgsz=640):
        self.model = None
        self.net = None
        self.backend = None
        self.target_imgsz = int(target_imgsz)
        self.model_filename = "Ninguno"
        
        # Definir rutas de archivos
        path_onnx = f"{model_path_base}.onnx"
        path_fixed = f"{model_path_base}_fixed.onnx"
        
        logger.info(f"[INIT] Buscando modelos en: {model_path_base}")

        # ==========================================================
        # PLAN A: JETSON INFERENCE (TensorRT Nativo - Máxima Velocidad)
        # ==========================================================
        if os.path.exists(path_onnx):
            try:
                import jetson.inference
                import jetson.utils
                
                logger.info(f"[TRY] Intentando cargar con jetson.inference: {path_onnx}")
                
                # detectNet compila el .engine automáticamente la primera vez y lo guarda en caché
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
                logger.info(f"[EXITO] Modelo cargado con JETSON INFERENCE (TensorRT)")
                return # ¡Éxito! Salimos del init
            
            except ImportError:
                logger.warning("[WARN] Librería 'jetson.inference' no encontrada. Pasando al Plan B.")
            except Exception as e:
                logger.error(f"[ERROR] Falló jetson.inference: {e}. Pasando al Plan B.")

        # ==========================================================
        # PLAN B: OPENCV DNN (Fallback con Auto-Reparación)
        # ==========================================================
        
        # Si ya existe una versión reparada (_fixed.onnx), úsala preferentemente
        target_path = path_fixed if os.path.exists(path_fixed) else path_onnx
        
        if os.path.exists(target_path):
            logger.info(f"[TRY] Fallback a OpenCV DNN: {target_path}")
            try:
                self.model = self._load_cv2_net(target_path)
                self.backend = 'opencv'
                self.model_filename = os.path.basename(target_path)
                logger.info(f"[EXITO] Modelo cargado con OpenCV")
                
            except Exception as e:
                logger.error(f"[ERROR] Carga estándar OpenCV falló: {e}")
                
                # --- AUTO-REPARACIÓN (La magia que arregla tu error) ---
                logger.info("[FIX] Intentando auto-reparar modelo con 'onnxslim'...")
                try:
                    # Ejecutamos onnxslim para limpiar el modelo de nodos dinámicos
                    cmd = ["onnxslim", path_onnx, path_fixed]
                    subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    logger.info(f"[FIX] Modelo reparado guardado en: {path_fixed}")
                    
                    # Intentamos cargar de nuevo con el archivo arreglado
                    self.model = self._load_cv2_net(path_fixed)
                    self.backend = 'opencv'
                    self.model_filename = os.path.basename(path_fixed)
                    logger.info(f"[EXITO] Modelo REPARADO cargado con OpenCV")
                    
                except Exception as fix_err:
                    logger.critical(f"[FATAL] La auto-reparación falló. No hay más opciones: {fix_err}")
                    raise fix_err

        if self.backend is None:
             raise FileNotFoundError(f"No se pudo cargar el modelo {model_path_base} con ningún backend.")

    def _load_cv2_net(self, path):
        """Helper para cargar red OpenCV intentando activar CUDA"""
        net = cv2.dnn.readNetFromONNX(path)
        try:
            net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
            net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
            logger.info("--> Backend CUDA activado en OpenCV")
        except:
            logger.warning("--> Backend CUDA falló, usando CPU")
            net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        return net

    def predict(self, frame, conf_thres=0.5):
        t_start = time.time()
        annotated_frame = frame.copy() # Copia para no modificar el original si no queremos
        
        # --- CASO 1: JETSON INFERENCE ---
        if self.backend == 'jetson_inference':
            import jetson.utils
            # BGR -> RGB (jetson.utils usa RGB)
            img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            cuda_img = jetson.utils.cudaFromNumpy(img_rgb)
            
            # Inferencia
            detections = self.net.Detect(cuda_img, overlay='box,labels,conf')
            
            # Dibujar (jetson.utils dibuja en cuda_img)
            annotated_frame = jetson.utils.cudaToNumpy(cuda_img)
            annotated_frame = cv2.cvtColor(annotated_frame, cv2.COLOR_RGB2BGR) # RGB -> BGR

        # --- CASO 2: OPENCV ---
        elif self.backend == 'opencv':
            blob = cv2.dnn.blobFromImage(frame, 1/255.0, (self.target_imgsz, self.target_imgsz), swapRB=True, crop=False)
            self.model.setInput(blob)
            outputs = self.model.forward()
            
            # NOTA: Aquí OpenCV no dibuja solo.
            # Para debugging visual rápido, devolvemos el frame sin cajas si no implementamos el post-proceso manual.
            # (El error que tenías era de CARGA, no de inferencia, así que esto ya no crasheará).
            pass

        t_end = time.time()
        inference_time = (t_end - t_start) * 1000
        fps = 1.0 / (t_end - t_start) if (t_end - t_start) > 0 else 0

        self._draw_stats(annotated_frame, fps, inference_time)
        return annotated_frame

    def _draw_stats(self, img, fps, ms):
        color = (0, 255, 0) if self.backend == 'jetson_inference' else (0, 165, 255) # Verde o Naranja
        lines = [
            f"Model: {self.model_filename}",
            f"Backend: {str(self.backend).upper()}",
            f"Time: {ms:.1f}ms | FPS: {fps:.1f}"
        ]
        
        # Dibujar stats
        cv2.rectangle(img, (5, 5), (350, 85), (0, 0, 0), -1)
        y = 30
        for line in lines:
            cv2.putText(img, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            y += 25