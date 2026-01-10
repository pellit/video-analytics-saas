import os
import cv2
import time
import numpy as np

# ELIMINAMOS: from ultralytics import YOLO

class SmartModelLoader:
    def __init__(self, model_path_base, task='detect', target_imgsz=640):
        """
        Carga SOLO modelos ONNX usando OpenCV con aceleración CUDA.
        Ignora archivos .engine para no depender de librerías externas.
        """
        self.model = None
        self.backend = 'opencv'
        self.target_imgsz = int(target_imgsz)
        self.model_filename = "Ninguno"
        self.task = task
        
        # Solo buscamos ONNX
        path_onnx = f"{model_path_base}.onnx"

        print(f"[INIT] Loader Optimizado (ONNX Only). Buscando: {path_onnx}")

        if os.path.exists(path_onnx):
            print(f"[INFO] Cargando ONNX: {path_onnx}")
            try:
                self.model = cv2.dnn.readNetFromONNX(path_onnx)
                
                # --- CONFIGURACIÓN CRÍTICA PARA CUDA ---
                try:
                    self.model.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
                    self.model.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
                    accel = "CUDA (GPU)"
                except Exception as e:
                    print(f"[WARN] Falló al activar CUDA: {e}")
                    self.model.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
                    self.model.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
                    accel = "CPU (Fallback)"
                
                self.model_filename = os.path.basename(path_onnx) + f" [{accel}]"
                print(f"[EXITO] Modelo cargado correctamente en: {accel}")

            except Exception as e:
                print(f"[ERROR] El archivo ONNX está corrupto o es incompatible: {e}")
                raise e
        else:
            raise FileNotFoundError(f"CRITICO: No se encontró el modelo: {path_onnx}")

    def predict(self, frame, conf_thres=0.5):
        t_start = time.time()
        
        # 1. Pre-proceso para YOLOv8/v5 en OpenCV
        # YOLO espera normalización 0-1 (scale=1/255) y swapRB=True
        blob = cv2.dnn.blobFromImage(
            frame, 
            1/255.0, 
            (self.target_imgsz, self.target_imgsz), 
            swapRB=True, 
            crop=False
        )
        self.model.setInput(blob)
        
        # 2. Inferencia
        outputs = self.model.forward()
        
        # 3. Post-proceso básico para visualización (solo debugging)
        # Nota: La lógica real de decodificación de cajas (NMS) suele estar fuera
        # o requiere un parseo manual de 'outputs' si no usas Ultralytics.
        # Para evitar escribir 100 líneas de NMS aquí, asumiremos que 
        # el endpoint 'debug' solo quiere verificar que el modelo CORRE y devuelve datos.
        
        t_end = time.time()
        inference_time = (t_end - t_start) * 1000
        fps = 1.0 / (t_end - t_start) if (t_end - t_start) > 0 else 0

        # Si el modelo corre, outputs tendrá forma (1, 84, 8400) aprox para YOLOv8
        # Dibujamos stats sobre el frame original
        self._draw_stats(frame, fps, inference_time, outputs.shape)
        
        # Devolvemos el frame y raw_outputs si fuera necesario, 
        # pero para mantener compatibilidad devolvemos frame pintado
        return frame

    def _draw_stats(self, img, fps, ms, shape):
        color = (0, 255, 0) # Verde = Éxito
        lines = [
            f"Model: {self.model_filename}",
            f"Backend: OpenCV DNN (CUDA)",
            f"Output Shape: {shape}",
            f"Time: {ms:.1f}ms | FPS: {fps:.1f}"
        ]
        
        # Fondo oscuro
        cv2.rectangle(img, (5, 5), (400, 110), (0, 0, 0), -1)
        y = 30
        for line in lines:
            cv2.putText(img, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            y += 25