import os
import traceback
from typing import Any, Dict, List

import cv2
import numpy as np
from fastapi import HTTPException


class TensorRTHitRunner:
    """TensorRT fallback para ejecutar hit_detect.onnx cuando OpenCV falla."""

    def __init__(self, model_path: str):
        try:
            import tensorrt as trt  # type: ignore
            import pycuda.driver as cuda  # type: ignore
            import pycuda.autoinit  # type: ignore  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(f"TensorRT no disponible en este entorno: {exc}")

        self.np = np
        self.trt = trt
        self.cuda = cuda
        self.logger = trt.Logger(trt.Logger.WARNING)
        self.model_path = model_path
        self.stream = cuda.Stream()

        explicit_batch = 1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH)
        builder = trt.Builder(self.logger)
        network = builder.create_network(explicit_batch)
        parser = trt.OnnxParser(network, self.logger)
        with open(model_path, 'rb') as f:
            if not parser.parse(f.read()):
                errors = []
                for idx in range(parser.num_errors):
                    errors.append(str(parser.get_error(idx)))
                raise RuntimeError("Errores al parsear hit_detect.onnx:\n" + "\n".join(errors))
        for out_idx in range(network.num_outputs - 1, -1, -1):
            tensor = network.get_output(out_idx)
            if tensor.name != 'output0':
                network.unmark_output(tensor)

        config = builder.create_builder_config()
        config.max_workspace_size = 1 << 29
        profile = builder.create_optimization_profile()
        input_tensor = network.get_input(0)
        min_shape = tuple(1 if dim == -1 else dim for dim in input_tensor.shape)
        profile.set_shape(input_tensor.name, min_shape, min_shape, min_shape)
        config.add_optimization_profile(profile)

        serialized = builder.build_serialized_network(network, config)
        if not serialized:
            raise RuntimeError('TensorRT no pudo construir el engine para hit_detect.onnx')
        runtime = trt.Runtime(self.logger)
        self.engine = runtime.deserialize_cuda_engine(serialized)
        self.context = self.engine.create_execution_context()

        self.bindings = [0] * self.engine.num_bindings
        self.host_mem = {}
        self.device_mem = {}
        self.input_binding_idx = None
        self.output_binding_idx = None
        for binding_idx in range(self.engine.num_bindings):
            name = self.engine.get_binding_name(binding_idx)
            dtype = trt.nptype(self.engine.get_binding_dtype(binding_idx))
            shape = tuple(self.engine.get_binding_shape(binding_idx))
            shape = tuple(1 if dim == -1 else dim for dim in shape)
            shape = tuple(max(1, dim) for dim in shape)
            size = int(trt.volume(shape))
            host_mem = np.empty(size, dtype=dtype)
            device_mem = cuda.mem_alloc(host_mem.nbytes)
            self.host_mem[name] = host_mem
            self.device_mem[name] = device_mem
            self.bindings[binding_idx] = int(device_mem)
            if self.engine.binding_is_input(binding_idx):
                self.input_binding_idx = binding_idx
                self.input_name = name
                self.input_shape = shape
                height = shape[2] if len(shape) > 2 else 224
                width = shape[3] if len(shape) > 3 else height
                self.input_hw = (width, height)
                self.input_dtype = dtype
            else:
                self.output_binding_idx = binding_idx
                self.output_name = name
                self.output_shape = shape
                self.output_dtype = dtype

        if self.input_binding_idx is None or self.output_binding_idx is None:
            raise RuntimeError('TensorRT engine inválido para hit_detect.onnx')

    def run(self, blob: np.ndarray) -> np.ndarray:
        arr = np.ascontiguousarray(blob.astype(self.input_dtype))
        self.cuda.memcpy_htod_async(self.device_mem[self.input_name], arr, self.stream)
        self.context.set_binding_shape(self.input_binding_idx, arr.shape)
        self.context.execute_async_v2(bindings=self.bindings, stream_handle=self.stream.handle)
        self.cuda.memcpy_dtoh_async(
            self.host_mem[self.output_name],
            self.device_mem[self.output_name],
            self.stream,
        )
        self.stream.synchronize()
        output = self.host_mem[self.output_name].copy()
        return output.reshape(self.output_shape)


class HitDetectionService:
    """Encapsula la ejecución del modelo hit_detect.onnx."""

    def __init__(self, default_model_dirs: List[str]):
        self.default_model_dirs = default_model_dirs
        self._model_override = os.environ.get('HIT_DETECT_MODEL_PATH')
        self._resolved_model_path = None
        self._net = None
        self._backend = None
        self._trt_runner = None
        self._input_hw = (640, 640)

    def _resolve_model_path(self) -> str:
        if self._resolved_model_path:
            return self._resolved_model_path
        candidates = []
        if self._model_override:
            candidates.append(self._model_override)
        candidates.extend(self.default_model_dirs)
        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                self._resolved_model_path = os.path.abspath(candidate)
                return self._resolved_model_path
        raise HTTPException(
            503,
            "hit_detect.onnx no está disponible en el dispositivo. "
            "Configura HIT_DETECT_MODEL_PATH o copia el archivo a ai_engine/models/."
        )

    def _init_trt_runner(self):
        if self._trt_runner:
            self._backend = 'tensorrt'
            return
        model_path = self._resolve_model_path()
        try:
            self._trt_runner = TensorRTHitRunner(model_path)
            self._backend = 'tensorrt'
            self._input_hw = self._trt_runner.input_hw
            print("[HitDetect] TensorRT fallback activo.")
        except Exception as exc_trt:
            traceback.print_exc()
            raise HTTPException(503, f"No se pudo inicializar hit_detect.onnx con TensorRT: {exc_trt}")

    def _load_model(self):
        if self._backend in ('opencv', 'tensorrt'):
            return
        model_path = self._resolve_model_path()
        print(f"[HitDetect] Loading ONNX model from {model_path}")
        try:
            net = cv2.dnn.readNetFromONNX(model_path)
            net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
            net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
            self._net = net
            self._backend = 'opencv'
            return
        except Exception as exc_gpu:
            print(f"[HitDetect] CUDA backend failed: {exc_gpu}. Falling back to CPU.")
            traceback.print_exc()
        try:
            net = cv2.dnn.readNetFromONNX(model_path)
            net.setPreferableBackend(cv2.dnn.DNN_BACKEND_DEFAULT)
            net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
            self._net = net
            self._backend = 'opencv'
            return
        except Exception as exc_cpu:
            print(f"[HitDetect] CPU backend failed: {exc_cpu}")
            traceback.print_exc()
            self._net = None
            self._backend = None
        self._init_trt_runner()

    def _forward(self, blob: np.ndarray) -> np.ndarray:
        if self._backend == 'opencv' and self._net is not None:
            self._net.setInput(blob)
            try:
                return self._net.forward()
            except Exception as exc_forward:
                print(f"[HitDetect] OpenCV forward failed: {exc_forward}. Switching to TensorRT.")
                traceback.print_exc()
                self._net = None
                self._backend = None
                self._init_trt_runner()
        if self._backend == 'tensorrt' and self._trt_runner is not None:
            return self._trt_runner.run(blob)
        raise HTTPException(503, "No se pudo inicializar hit_detect.onnx.")

    def run_on_video(
        self,
        video_path: str,
        frame_stride: int,
        max_frames: int,
        hit_threshold: float
    ) -> Dict[str, Any]:
        self._load_model()
        target_size = self._input_hw
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise HTTPException(400, "Unable to open uploaded video")

        frame_idx = 0
        processed = 0
        detections = []
        debug_logs = []

        while processed < max_frames:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % frame_stride != 0:
                frame_idx += 1
                continue

            resized = cv2.resize(frame, target_size)
            blob = cv2.dnn.blobFromImage(
                resized,
                scalefactor=1 / 255.0,
                size=target_size,
                swapRB=True,
                crop=False,
            )
            output = self._forward(blob)

            flat = output.flatten().tolist()
            if not flat:
                probability = 0.0
            elif len(flat) == 1:
                probability = float(flat[0])
            else:
                probability = float(flat[-1])

            detections.append({
                "frame": frame_idx,
                "hit_probability": round(probability, 4),
                "raw_output": flat
            })
            if len(debug_logs) < 10:
                debug_logs.append({
                    "frame": frame_idx,
                    "blob_shape": list(blob.shape),
                    "output_shape": list(output.shape) if hasattr(output, "shape") else None,
                    "hit_probability": round(probability, 4)
                })

            processed += 1
            frame_idx += 1

        cap.release()

        hits = [det for det in detections if det["hit_probability"] >= hit_threshold]

        return {
            "frames_analyzed": processed,
            "detections": detections,
            "hits_detected": len(hits),
            "hit_threshold": hit_threshold,
            "hit_frames": [det["frame"] for det in hits],
            "debug_logs": debug_logs
        }
