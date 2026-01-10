import cv2
import tensorrt as trt
import pycuda.driver as cuda
import pycuda.autoinit
import numpy as np
import time

class YoloTRT:
    def __init__(self, engine_path):
        self.logger = trt.Logger(trt.Logger.WARNING)
        self.engine_path = engine_path
        self.context = None
        self.inputs = []
        self.outputs = []
        self.bindings = []
        self.stream = None
        
        self._load_engine()
        self._allocate_buffers()

    def _load_engine(self):
        print(f"[TRT] Cargando engine: {self.engine_path}")
        with open(self.engine_path, "rb") as f, trt.Runtime(self.logger) as runtime:
            self.engine = runtime.deserialize_cuda_engine(f.read())
            
        if not self.engine:
            raise RuntimeError("Falló la carga del engine TensorRT")
            
        self.context = self.engine.create_execution_context()
        self.stream = cuda.Stream()

    def _allocate_buffers(self):
        """Reserva memoria en Host (CPU) y Device (GPU) para entradas/salidas"""
        for binding in self.engine:
            # Obtener tamaño y tipo
            # Nota: En TRT 8.5+ usar get_binding_shape es deprecated, pero común en Jetpack 4.6
            shape = self.engine.get_binding_shape(binding)
            dtype = trt.nptype(self.engine.get_binding_dtype(binding))
            size = trt.volume(shape)
            
            # Crear buffers
            host_mem = cuda.pagelocked_empty(size, dtype)
            device_mem = cuda.mem_alloc(host_mem.nbytes)
            
            self.bindings.append(int(device_mem))
            
            if self.engine.binding_is_input(binding):
                self.input_w = shape[3]
                self.input_h = shape[2]
                self.inputs.append({'host': host_mem, 'device': device_mem, 'shape': shape})
            else:
                self.outputs.append({'host': host_mem, 'device': device_mem, 'shape': shape})

    def infer(self, img):
        """Ejecuta la inferencia"""
        # 1. Preprocesamiento (Resize + Normalize + Transpose)
        img_resized = cv2.resize(img, (self.input_w, self.input_h))
        # Convertir a float32, normalizar 0-1, transponer a CHW (3, 640, 640)
        input_data = img_resized.transpose((2, 0, 1)).astype(np.float32) / 255.0
        input_data = np.expand_dims(input_data, axis=0) # Batch dimension (1, 3, 640, 640)
        
        # Copiar imagen al buffer de entrada en CPU
        np.copyto(self.inputs[0]['host'], input_data.ravel())

        # 2. Transferencia Host -> Device
        cuda.memcpy_htod_async(self.inputs[0]['device'], self.inputs[0]['host'], self.stream)
        
        # 3. Ejecutar Inferencia
        self.context.execute_async_v2(bindings=self.bindings, stream_handle=self.stream.handle)
        
        # 4. Transferencia Device -> Host
        for out in self.outputs:
            cuda.memcpy_dtoh_async(out['host'], out['device'], self.stream)
            
        # Sincronizar stream
        self.stream.synchronize()
        
        # 5. Retornar salida cruda (YOLO output)
        return [out['host'] for out in self.outputs]

class YoloPostProcessor:
    """Decodifica la salida cruda de YOLOv8 [1, 84, 8400] a Cajas [x,y,w,h]"""
    def __init__(self, conf_thres=0.5, nms_thres=0.45):
        self.conf_thres = conf_thres
        self.nms_thres = nms_thres

    def process(self, trt_output, orig_shape):
        # trt_output es una lista plana, re-formateamos a [1, 84, 8400]
        # 84 = 4 coords + 80 clases (para COCO)
        output = trt_output[0].reshape(1, 84, 8400) # Ajustar según tu modelo (8400 anclas)
        output = np.squeeze(output).T # Transponer a [8400, 84]
        
        # Filtrar por confianza
        scores = np.max(output[:, 4:], axis=1)
        keep = scores > self.conf_thres
        output = output[keep]
        scores = scores[keep]
        
        if len(output) == 0:
            return [], None

        # Obtener IDs de clase
        class_ids = np.argmax(output[:, 4:], axis=1)
        
        # Obtener cajas (xc, yc, w, h) -> (x1, y1, x2, y2)
        boxes = output[:, :4]
        input_h, input_w = 640, 640 # Tamaño entrada del modelo
        orig_h, orig_w = orig_shape[:2]
        
        # Escalar cajas a imagen original
        scale_x = orig_w / input_w
        scale_y = orig_h / input_h
        
        boxes[:, 0] *= scale_x # cx
        boxes[:, 1] *= scale_y # cy
        boxes[:, 2] *= scale_x # w
        boxes[:, 3] *= scale_y # h
        
        # Convertir a XYXY (top-left, bottom-right) para NMS
        xyxy = np.zeros_like(boxes)
        xyxy[:, 0] = boxes[:, 0] - boxes[:, 2] / 2
        xyxy[:, 1] = boxes[:, 1] - boxes[:, 3] / 2
        xyxy[:, 2] = boxes[:, 0] + boxes[:, 2] / 2
        xyxy[:, 3] = boxes[:, 1] + boxes[:, 3] / 2
        
        # Non-Maximum Suppression (NMS)
        indices = cv2.dnn.NMSBoxes(
            bboxes=boxes.tolist(), # NMSBoxes de OpenCV espera xywh
            scores=scores.tolist(),
            score_threshold=self.conf_thres,
            nms_threshold=self.nms_thres
        )
        
        final_dets = []
        if len(indices) > 0:
            for i in indices.flatten():
                # Formato final simple
                final_dets.append({
                    "class_id": int(class_ids[i]),
                    "score": float(scores[i]),
                    "bbox": xyxy[i].tolist() # [x1, y1, x2, y2]
                })
                
        return final_dets