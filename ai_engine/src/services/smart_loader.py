import os
import cv2
import time
from .trt_loader import YoloTRT, YoloPostProcessor # Importamos la clase nueva

class SmartModelLoader:
    def __init__(self, model_path_base, task='detect', target_imgsz=640):
        self.model = None
        self.postprocessor = None
        self.backend = None
        self.target_imgsz = int(target_imgsz)
        self.model_filename = "Ninguno"
        
        path_engine = f"{model_path_base}.engine"
        path_onnx = f"{model_path_base}.onnx"

        # --- 1. TENSORRT NATIVO (Sin Ultralytics) ---
        if os.path.exists(path_engine):
            print(f"[INFO] Engine encontrado: {path_engine}")
            try:
                # Usamos nuestra clase nativa
                self.model = YoloTRT(path_engine)
                self.postprocessor = YoloPostProcessor(conf_thres=0.45)
                self.backend = 'tensorrt_native'
                self.model_filename = os.path.basename(path_engine)
                print(f"[EXITO] Cargado Engine con TRT Nativo")
                return
            except Exception as e:
                print(f"[ERROR] Engine nativo falló: {e}. Intentando ONNX...")

        # --- 2. FALLBACK ONNX ---
        # (El resto de tu código para ONNX/OpenCV sigue aquí igual que antes)
        if os.path.exists(path_onnx):
             # ... carga cv2.dnn ...
             pass

    def predict(self, frame, conf_thres=0.5):
        t_start = time.time()
        
        if self.backend == 'tensorrt_native':
            # 1. Inferencia nativa
            raw_output = self.model.infer(frame)
            
            # 2. Post-procesamiento manual (Decodificar cajas)
            # Actualizamos el umbral dinámicamente si cambió
            self.postprocessor.conf_thres = conf_thres
            detections = self.postprocessor.process(raw_output, frame.shape)
            
            # 3. Dibujar (para mantener compatibilidad visual)
            annotated_frame = frame.copy()
            for det in detections:
                x1, y1, x2, y2 = map(int, det['bbox'])
                cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                
        elif self.backend == 'opencv':
            # ... tu lógica existente de OpenCV ...
            annotated_frame = frame

        # ... (cálculo de FPS y dibujo de stats igual que antes) ...
        return annotated_frame