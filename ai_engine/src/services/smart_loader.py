import os
import cv2
import time
from ultralytics import YOLO

class SmartModelLoader:
    def __init__(self, model_path_base, task='detect', target_imgsz=416):
        """
        model_path_base: Ruta completa SIN extensión (ej: /app/ai_engine/models/best)
        target_imgsz: Tamaño definido en el docker-compose (ej: 416)
        """
        self.model = None
        self.backend = None
        self.target_imgsz = int(target_imgsz) # Aseguramos que sea entero
        self.model_filename = "Ninguno"
        
        # Rutas esperadas
        path_engine = f"{model_path_base}.engine"
        path_onnx = f"{model_path_base}.onnx"

        print(f"[INIT] Buscando modelos en base a: {model_path_base}")
        print(f"[INIT] Tamaño configurado (YOLO_SIZE): {self.target_imgsz}")

        # --- 1. INTENTO TENSORRT (.engine) ---
        if os.path.exists(path_engine):
            print(f"[INFO] Engine encontrado: {path_engine}")
            try:
                self.model = YOLO(path_engine, task=task)
                self.backend = 'tensorrt'
                self.model_filename = os.path.basename(path_engine)
                print(f"[EXITO] Cargado Engine TensorRT Nativo")
            except Exception as e:
                print(f"[ERROR] Engine falló: {e}")
        
        # --- 2. FALLBACK ONNX (.onnx) ---
        if self.model is None and os.path.exists(path_onnx):
            print(f"[INFO] Usando Fallback ONNX: {path_onnx}")
            try:
                self.model = cv2.dnn.readNetFromONNX(path_onnx)
                try:
                    self.model.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
                    self.model.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
                    accel = "CUDA"
                except:
                    accel = "CPU"
                
                self.backend = 'opencv'
                self.model_filename = os.path.basename(path_onnx) + f" [{accel}]"
                print(f"[EXITO] Cargado ONNX con OpenCV ({accel})")

            except Exception as e:
                print(f"[ERROR] ONNX inválido: {e}")

        if self.model is None:
            # Mensaje de error claro si no encuentra nada en la carpeta montada
            raise FileNotFoundError(f"CRITICO: No hay 'best.engine' ni 'best.onnx' en {model_path_base}. Verifica tu volumen docker.")

    def predict(self, frame, conf_thres=0.5):
        t_start = time.time()
        
        if self.backend == 'tensorrt':
            # Ultralytics se encarga del resize, pero le recordamos el tamaño
            results = self.model(frame, verbose=False, conf=conf_thres, imgsz=self.target_imgsz)
            annotated_frame = results[0].plot() 
            
        elif self.backend == 'opencv':
            # Resize manual estricto al tamaño del compose
            blob = cv2.dnn.blobFromImage(frame, 1/255.0, (self.target_imgsz, self.target_imgsz), swapRB=True, crop=False)
            self.model.setInput(blob)
            outputs = self.model.forward()
            # (Aquí iría tu post-proceso de cajas para ONNX. Por ahora devolvemos frame)
            annotated_frame = frame # Placeholder si usas ONNX puro

        t_end = time.time()
        inference_time = (t_end - t_start) * 1000
        fps = 1.0 / (t_end - t_start) if (t_end - t_start) > 0 else 0

        self._draw_stats(annotated_frame, fps, inference_time)
        return annotated_frame

    def _draw_stats(self, img, fps, ms):
        color = (0, 255, 0) if self.backend == 'tensorrt' else (0, 0, 255)
        lines = [
            f"Model: {self.model_filename}",
            f"Mode: {self.backend.upper()} | Size: {self.target_imgsz}",
            f"Time: {ms:.1f}ms | FPS: {fps:.1f}"
        ]
        cv2.rectangle(img, (5, 5), (350, 85), (0, 0, 0), -1)
        y = 30
        for line in lines:
            cv2.putText(img, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            y += 25