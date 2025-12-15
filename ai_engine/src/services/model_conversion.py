"""Utilities for converting AI model weights via API endpoints."""
from __future__ import annotations

import importlib
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, Tuple

import torch

from ..schemas.model_conversion import OnnxToTensorRTConfig, PyTorchToOnnxConfig


class ModelConversionError(RuntimeError):
    """Custom error raised when a conversion step fails."""


def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _load_pytorch_model(weight_path: Path, config: PyTorchToOnnxConfig) -> torch.nn.Module:
    map_location = torch.device("cpu")
    if config.framework == "torchscript":
        try:
            module = torch.jit.load(weight_path.as_posix(), map_location=map_location)
            module.eval()
            return module
        except Exception as exc:  # pragma: no cover - relies on torch runtime
            raise ModelConversionError(f"No se pudo cargar TorchScript: {exc}") from exc

    if config.framework == "state_dict":
        if not config.model_class:
            raise ModelConversionError(
                "Debes proporcionar 'model_class' (module:Class) para convertir un state_dict."
            )
        if ":" not in config.model_class:
            raise ModelConversionError("Formato inválido para model_class. Usa 'package.module:ClassName'.")
        module_path, class_name = config.model_class.split(":", 1)
        try:
            module = importlib.import_module(module_path)
        except ModuleNotFoundError as exc:  # pragma: no cover - import resolution
            raise ModelConversionError(f"No se pudo importar '{module_path}': {exc}") from exc
        try:
            model_cls = getattr(module, class_name)
        except AttributeError as exc:
            raise ModelConversionError(f"'{class_name}' no encontrado en '{module_path}'.") from exc
        try:
            instance = model_cls(**(config.model_kwargs or {}))
        except Exception as exc:  # pragma: no cover - user supplied kwargs
            raise ModelConversionError(f"Error instanciando '{class_name}': {exc}") from exc
        checkpoint = torch.load(weight_path.as_posix(), map_location=map_location)
        if config.state_dict_key:
            checkpoint = checkpoint.get(config.state_dict_key)
            if checkpoint is None:
                raise ModelConversionError(
                    f"La clave '{config.state_dict_key}' no existe dentro del checkpoint."
                )
        missing, unexpected = instance.load_state_dict(checkpoint, strict=False)
        if missing:
            print(f"⚠️ Parámetros faltantes al cargar el modelo: {missing}")
        if unexpected:
            print(f"⚠️ Parámetros inesperados en el checkpoint: {unexpected}")
        instance.eval()
        return instance

    raise ModelConversionError(
        f"Framework '{config.framework}' no soportado para exportar vía torch.onnx.export"
    )


def _maybe_simplify_onnx(output_path: Path) -> None:
    try:
        import onnx  # type: ignore
        from onnxsim import simplify  # type: ignore
    except ImportError:
        raise ModelConversionError(
            "onnxsim no está instalado. Instálalo para usar la opción 'simplify'."
        )

    print("⚙️ Simplificando grafo ONNX con onnx-simplifier...")
    model = onnx.load(output_path.as_posix())
    simplified_model, check = simplify(model)
    if not check:
        raise ModelConversionError("La verificación del modelo simplificado falló.")
    onnx.save(simplified_model, output_path.as_posix())


def convert_pytorch_checkpoint_to_onnx(
    weight_path: str, output_path: str, config: PyTorchToOnnxConfig
) -> Dict[str, Any]:
    """Convert a PyTorch checkpoint (.pt/.pth) into an ONNX graph."""

    input_shape = config.resolved_input_shape()
    output_path_obj = Path(output_path)
    _ensure_parent_dir(output_path_obj)
    start_time = time.perf_counter()

    if config.framework == "ultralytics":
        try:
            from ultralytics import YOLO  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ModelConversionError(f"Ultralytics no está instalado: {exc}") from exc

        print(
            f"🚀 Exportando modelo Ultralytics a ONNX ({config.model_name}) con img={input_shape[2]}"
        )
        try:
            model = YOLO(weight_path)
            exported_path = model.export(
                format="onnx",
                imgsz=(input_shape[2], input_shape[3]),
                batch=input_shape[0],
                half=config.half_precision,
                dynamic=config.dynamic_batch,
                opset=config.opset,
                simplify=config.simplify,
                device="cpu",
            )
        except Exception as exc:  # pragma: no cover - depends on ultralytics runtime
            raise ModelConversionError(f"Error exportando con Ultralytics: {exc}") from exc
        shutil.move(exported_path, output_path_obj)
    else:
        model = _load_pytorch_model(Path(weight_path), config)
        dtype = torch.float16 if config.input_dtype == "float16" or config.half_precision else torch.float32
        if hasattr(model, "to"):
            model = model.to(dtype=dtype)  # type: ignore[assignment]
        dummy_input = torch.randn(*input_shape, dtype=dtype)
        input_names = [config.input_name]
        output_names = config.output_names or ["output"]
        dynamic_axes = None
        if config.dynamic_batch:
            dynamic_axes = {input_names[0]: {0: "batch"}}
            for name in output_names:
                dynamic_axes[name] = {0: "batch"}

        print(
            f"🚀 Exportando PyTorch->ONNX | shape={input_shape} | opset={config.opset} | dtype={dtype}"
        )
        try:
            with torch.no_grad():
                torch.onnx.export(
                    model,
                    dummy_input,
                    output_path_obj.as_posix(),
                    export_params=True,
                    opset_version=config.opset,
                    do_constant_folding=True,
                    input_names=input_names,
                    output_names=output_names,
                    dynamic_axes=dynamic_axes,
                )
        except Exception as exc:  # pragma: no cover - depends on torch runtime
            raise ModelConversionError(f"torch.onnx.export falló: {exc}") from exc
        if config.simplify:
            _maybe_simplify_onnx(output_path_obj)

    duration = time.perf_counter() - start_time
    size_mb = output_path_obj.stat().st_size / (1024 * 1024)
    return {
        "model_name": config.model_name,
        "output_path": output_path_obj.as_posix(),
        "output_size_mb": round(size_mb, 3),
        "input_shape": input_shape,
        "duration_s": round(duration, 3),
        "framework": config.framework,
    }


def _resolve_shape_from_dims(
    dims: Tuple[int, ...],
    tensor_name: str,
    config: OnnxToTensorRTConfig,
) -> Tuple[Tuple[int, ...], Tuple[int, ...], Tuple[int, ...]]:
    override_shape = config.input_shapes.get(tensor_name)
    if override_shape:
        resolved = tuple(int(v) for v in override_shape)
        return resolved, resolved, resolved

    resolved = []
    for axis, dim in enumerate(dims):
        if dim >= 0:
            resolved.append(int(dim))
            continue
        if axis == 0:
            resolved.append(int(config.max_batch_size))
            continue
        raise ModelConversionError(
            f"El tensor '{tensor_name}' tiene una dimensión dinámica en el eje {axis}. "
            "Proporciona 'input_shapes' o un perfil personalizado para continuar."
        )

    resolved_shape = tuple(resolved)
    return resolved_shape, resolved_shape, resolved_shape


def convert_onnx_to_tensorrt(
    onnx_path: str, engine_path: str, config: OnnxToTensorRTConfig
) -> Dict[str, Any]:
    """Convert an ONNX graph into a TensorRT serialized engine."""

    try:
        import tensorrt as trt  # type: ignore
    except ImportError as exc:  # pragma: no cover - Jetson specific dep
        raise ModelConversionError(f"TensorRT no está disponible en este entorno: {exc}") from exc

    logger = trt.Logger(trt.Logger.WARNING)
    builder = trt.Builder(logger)
    flag = 1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH)
    network = builder.create_network(flag)
    parser = trt.OnnxParser(network, logger)

    with open(onnx_path, "rb") as f:
        model_bytes = f.read()
    if not parser.parse(model_bytes):
        errors = [str(parser.get_error(i)) for i in range(parser.num_errors)]
        raise ModelConversionError("Error al parsear el ONNX:\n" + "\n".join(errors))

    config_trt = builder.create_builder_config()
    workspace_bytes = int(config.workspace_size_mb) * 1024 * 1024
    if hasattr(config_trt, "set_memory_pool_limit"):
        config_trt.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, workspace_bytes)
    else:  # pragma: no cover - legacy TRT versions
        config_trt.max_workspace_size = workspace_bytes

    precision = "fp32"
    if config.fp16 and builder.platform_has_fast_fp16:
        config_trt.set_flag(trt.BuilderFlag.FP16)
        precision = "fp16"

    profile = builder.create_optimization_profile()
    profile_specs = []
    if config.input_profiles:
        for tensor_name, spec in config.input_profiles.items():
            profile.set_shape(
                tensor_name,
                tuple(int(v) for v in spec.min),
                tuple(int(v) for v in spec.opt),
                tuple(int(v) for v in spec.max),
            )
            profile_specs.append(
                {
                    "tensor": tensor_name,
                    "min": list(spec.min),
                    "opt": list(spec.opt),
                    "max": list(spec.max),
                }
            )
    else:
        for idx in range(network.num_inputs):
            tensor = network.get_input(idx)
            min_shape, opt_shape, max_shape = _resolve_shape_from_dims(
                tuple(tensor.shape), tensor.name, config
            )
            profile.set_shape(tensor.name, min_shape, opt_shape, max_shape)
            profile_specs.append(
                {
                    "tensor": tensor.name,
                    "min": list(min_shape),
                    "opt": list(opt_shape),
                    "max": list(max_shape),
                }
            )
    config_trt.add_optimization_profile(profile)

    print(
        f"🚀 Construyendo TensorRT engine ({config.model_name}) | precision={precision} | workspace={config.workspace_size_mb}MB"
    )
    build_start = time.perf_counter()
    serialized = builder.build_serialized_network(network, config_trt)
    duration = time.perf_counter() - build_start
    if serialized is None:
        raise ModelConversionError("TensorRT no pudo generar el engine.")

    engine_path_obj = Path(engine_path)
    _ensure_parent_dir(engine_path_obj)
    with open(engine_path_obj, "wb") as f:
        f.write(bytes(serialized))

    size_mb = engine_path_obj.stat().st_size / (1024 * 1024)
    return {
        "model_name": config.model_name,
        "engine_path": engine_path_obj.as_posix(),
        "engine_size_mb": round(size_mb, 3),
        "precision": precision,
        "workspace_mb": config.workspace_size_mb,
        "profiles": profile_specs,
        "duration_s": round(duration, 3),
    }
