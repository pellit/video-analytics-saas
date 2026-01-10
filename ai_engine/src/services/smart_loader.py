import os
import cv2
import time
import logging
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
        
        # Rutas
        path_onnx = f"{model_path_base}.onnx"
        
        logger.info(f"[INIT] Buscando modelos en: {model_path_base}")

        # --- INTENTO 1: JETSON INFERENCE (TensorRT Nativo) ---
        # Usamos el ONNX. detectNet creará el .engine automáticamente y lo guardará.
        if os.path.exists(path_onnx):
            try:
                import jetson.inference
                import jetson.utils
                
                logger.info(f"[TRY] Cargando con jetson.inference (TensorRT): {path_onnx}")
                
                # Cargamos detectNet. 
                # threshold: umbral de confianza base
                self.net = jetson.inference.detectNet(
                    argv=[
                        f"--model={path_onnx}", 
                        f"--labels={os.path.join(os.path.dirname(path_onnx), 'classes.txt')}", # Opcional si tienes clases
                        "--input-blob=images", 
                        "--output-cvg=output_0", # Nombres standard YOLOv8 export
                        "--output-bbox=output_0"
                    ],
                    threshold=0.3
                )
                
                self.backend = 'jetson_inference'
                self.model_filename = os.path.basename(path_onnx)
                logger.info(f"[EXITO] Modelo cargado con JETSON INFERENCE (TensorRT)")
                return
            
            except ImportError:
                logger.warning("[WARN] jetson.inference no importable (¿Estás fuera de la Jetson?)")
            except Exception as e:
                logger.error(f"[ERROR] Falló jetson.inference: {e}. Intentando fallback...")

        # --- INTENTO 2: OPENCV CUDA (Fallback) ---
        if os.path.exists(path_onnx):
            logger.info(f"[TRY] Fallback a OpenCV DNN: {path_onnx}")
            try:
                self.model = cv2.dnn.readNetFromONNX(path_onnx)
                
                # Intentar activar CUDA
                try:
                    self.model.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
                    self.model.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
                    accel = "CUDA"
                except:
                    self.model.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
                    self.model.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
                    accel = "CPU"
                
                self.backend = 'opencv'
                self.model_filename = f"{os.path.basename(path_onnx)} [{accel}]"
                logger.info(f"[EXITO] Modelo cargado con OpenCV ({accel})")
                
            except Exception as e:
                logger.error(f"[ERROR] OpenCV falló: {e}")
                raise e

    def predict(self, frame, conf_thres=0.5):
        t_start = time.time()
        
        annotated_frame = frame.copy()
        
        # --- BACKEND: JETSON INFERENCE ---
        if self.backend == 'jetson_inference':
            import jetson.utils
            
            # Convertir frame OpenCV (numpy) a imagen CUDA
            # jetson.utils espera RGBA o RGB float32 o uint8
            # Primero convertimos BGR -> RGB
            img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            cuda_img = jetson.utils.cudaFromNumpy(img_rgb)
            
            # Inferencia
            detections = self.net.Detect(cuda_img, overlay='box,labels,conf')
            
            # Si queremos dibujar nosotros o usar la imagen de overlay:
            # jetson.inference dibuja en cuda_img si pasamos overlay. 
            # Convertimos de vuelta a Numpy para seguir el flujo de la app.
            annotated_frame = jetson.utils.cudaToNumpy(cuda_img)
            annotated_frame = cv2.cvtColor(annotated_frame, cv2.COLOR_RGB2BGR)
            
            # Opcional: Filtrar detecciones por confianza manual si se requiere
            # (detectNet ya filtra por el threshold del init)

        # --- BACKEND: OPENCV ---
        elif self.backend == 'opencv':
            blob = cv2.dnn.blobFromImage(frame, 1/255.0, (self.target_imgsz, self.target_imgsz), swapRB=True, crop=False)
            self.model.setInput(blob)
            outputs = self.model.forward()
            
            # Post-proceso OpenCV para dibujar cajas (simplificado)
            # Para YOLOv8 output: [1, 84, 8400]
            # ... Aquí iría el código de dibujo manual si se necesita ...
            # Por ahora devolvemos el frame limpio si no hay lógica de dibujo
            pass

        t_end = time.time()
        inference_time = (t_end - t_start) * 1000
        fps = 1.0 / (t_end - t_start) if (t_end - t_start) > 0 else 0

        self._draw_stats(annotated_frame, fps, inference_time)
        return annotated_frame

    def _draw_stats(self, img, fps, ms):
        color = (0, 255, 0) if 'jetson' in str(self.backend) else (0, 0, 255)
        lines = [
            f"Model: {self.model_filename}",
            f"Backend: {str(self.backend).upper()}",
            f"Time: {ms:.1f}ms | FPS: {fps:.1f}"
        ]
        
        cv2.rectangle(img, (5, 5), (350, 85), (0, 0, 0), -1)
        y = 30
        for line in lines:
            cv2.putText(img, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            y += 25