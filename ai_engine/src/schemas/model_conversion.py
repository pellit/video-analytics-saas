"""Pydantic schemas for model conversion APIs."""
from __future__ import annotations

from typing import Dict, List, Optional, Literal, Any

from pydantic import BaseModel, Field, conint, validator


class PyTorchToOnnxConfig(BaseModel):
    """Configuration payload for converting PyTorch checkpoints to ONNX."""

    model_name: str = Field(..., description="Human friendly name used for logging")
    output_filename: Optional[str] = Field(
        None,
        description="Custom ONNX filename. Defaults to '<model_name>.onnx' when omitted.",
    )
    framework: Literal["torchscript", "state_dict", "ultralytics"] = Field(
        "torchscript",
        description="Loading strategy used to hydrate the checkpoint before export.",
    )
    model_class: Optional[str] = Field(
        None,
        description="Python path to the model class (module:Class). Required when using 'state_dict'.",
    )
    model_kwargs: Dict[str, Any] = Field(
        default_factory=dict,
        description="Keyword arguments passed to the model class constructor when needed.",
    )
    state_dict_key: Optional[str] = Field(
        None,
        description="Optional key that contains the actual state_dict inside the checkpoint file.",
    )
    batch_size: conint(ge=1, le=64) = Field(
        1, description="Batch dimension used during export and in the resulting ONNX graph."
    )
    input_channels: conint(ge=1, le=32) = Field(3, description="Number of channels in the dummy input.")
    input_height: conint(ge=32, le=4096) = Field(640, description="Input height used for the dummy tensor.")
    input_width: conint(ge=32, le=4096) = Field(640, description="Input width used for the dummy tensor.")
    input_shape: Optional[List[conint(ge=1)]] = Field(
        None, description="Explicit tensor shape [B, C, H, W]. Overrides individual input_* fields when set."
    )
    input_dtype: Literal["float32", "float16"] = Field(
        "float32", description="Floating point precision used for the dummy tensor."
    )
    opset: conint(ge=9, le=18) = Field(13, description="ONNX opset to use during export.")
    dynamic_batch: bool = Field(True, description="Whether to mark the batch dimension as dynamic.")
    half_precision: bool = Field(
        False,
        description="Casts the model + dummy input to FP16 before export (ignored for frameworks that do not support it).",
    )
    simplify: bool = Field(False, description="Run ONNX graph simplification when supported by the framework.")
    input_name: str = Field("images", description="Input tensor name used inside the ONNX graph.")
    output_names: List[str] = Field(default_factory=lambda: ["output"], description="Output tensor names.")
    overwrite: bool = Field(
        False,
        description="Allow replacing an existing ONNX file with the same destination path.",
    )

    @validator("output_names", each_item=True)
    def _strip_output_names(cls, value: str) -> str:  # noqa: N805
        return value.strip() or "output"

    def resolved_input_shape(self) -> List[int]:
        if self.input_shape and len(self.input_shape) >= 4:
            return [int(x) for x in self.input_shape[:4]]
        return [
            int(self.batch_size),
            int(self.input_channels),
            int(self.input_height),
            int(self.input_width),
        ]


class TensorRTProfile(BaseModel):
    min: List[conint(ge=1)]
    opt: List[conint(ge=1)]
    max: List[conint(ge=1)]

    @validator("opt")
    def _match_opt_shape(cls, value: List[int], values):  # noqa: N805
        min_shape = values.get("min")
        max_shape = values.get("max")
        if min_shape and len(value) != len(min_shape):
            raise ValueError("opt shape rank must match min shape")
        if max_shape and len(value) != len(max_shape):
            raise ValueError("opt shape rank must match max shape")
        return value


class OnnxToTensorRTConfig(BaseModel):
    """Configuration payload for converting ONNX graphs into TensorRT engines."""

    model_name: str = Field(..., description="Identifier used when naming output artifacts.")
    engine_filename: Optional[str] = Field(
        None, description="Override engine filename. Uses '<model_name>.engine' by default."
    )
    onnx_filename: Optional[str] = Field(
        None,
        description="Optional filename used when persisting the uploaded ONNX file in the models directory.",
    )
    workspace_size_mb: conint(ge=32, le=8192) = Field(
        512, description="TensorRT workspace limit in megabytes."
    )
    fp16: bool = Field(True, description="Enable FP16 precision when supported by the platform.")
    max_batch_size: conint(ge=1, le=64) = Field(1, description="Batch dimension used when inferring shapes.")
    input_shapes: Dict[str, List[conint(ge=1)]] = Field(
        default_factory=dict,
        description="Static shape overrides keyed by tensor name when the ONNX graph uses dynamic dims.",
    )
    input_profiles: Dict[str, TensorRTProfile] = Field(
        default_factory=dict,
        description="Optional TensorRT optimization profiles keyed by tensor name.",
    )
    overwrite: bool = Field(
        False,
        description="Allow replacing an existing TensorRT engine with the same destination path.",
    )
    keep_onnx_copy: bool = Field(
        True,
        description="Store the uploaded ONNX inside the models directory next to the generated engine.",
    )

    def resolved_engine_name(self) -> str:
        base = (self.engine_filename or f"{self.model_name}.engine").strip()
        return base or f"{self.model_name}.engine"

    def resolved_onnx_name(self) -> Optional[str]:
        if self.keep_onnx_copy:
            return (self.onnx_filename or f"{self.model_name}.onnx").strip()
        return None
