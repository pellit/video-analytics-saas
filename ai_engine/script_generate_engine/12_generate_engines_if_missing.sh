#!/usr/bin/env bash
set -euo pipefail

# Genera los TensorRT .engine para los modelos YOLO (det y pose) si no existen.
# Se ejecuta dentro del contenedor. Requiere trtexec (/usr/src/tensorrt/bin en Jetson).

MODELS_DIR="${MODELS_DIR:-/app/ai_engine/models}"
YOLO_SIZE="${YOLO_SIZE:-640}"
MODEL_NAME_DET="${MODEL_NAME_DETECT:-yolov8n_${YOLO_SIZE}}"
MODEL_NAME_POSE="${MODEL_NAME_POSE:-yolov8s-pose_${YOLO_SIZE}}"

TRTEXEC_BIN="${TRTEXEC_BIN:-/usr/src/tensorrt/bin/trtexec}"

log() { echo "[ENGINE] $*"; }
err() { echo "[ENGINE][ERROR] $*" >&2; }

build_engine() {
  local base="$1"        # sin extensión, ruta completa
  local onnx="${base}.onnx"
  local engine="${base}.engine"
  if [[ ! -f "$onnx" ]]; then
    log "No ONNX found for $base (expected $onnx). Skipping."
    return
  fi
  if [[ -f "$engine" ]]; then
    log "Engine already exists: $engine"
    return
  fi
  if [[ ! -x "$TRTEXEC_BIN" ]]; then
    err "trtexec not found at $TRTEXEC_BIN. Install TensorRT CLI or set TRTEXEC_BIN."
    return
  fi

  log "Building engine from $onnx -> $engine (imgsz=${YOLO_SIZE})"
  # TensorRT build; use explicit shapes for YOLO export and FP16
  if "$TRTEXEC_BIN" --onnx="$onnx" --saveEngine="$engine" \
      --fp16 --workspace=2048 --minShapes=images:1x3x${YOLO_SIZE}x${YOLO_SIZE} \
      --optShapes=images:1x3x${YOLO_SIZE}x${YOLO_SIZE} \
      --maxShapes=images:1x3x${YOLO_SIZE}x${YOLO_SIZE} \
      --verbose > /tmp/trtexec_build.log 2>&1; then
    log "Built engine: $(basename "$engine")"
  else
    err "Failed building $engine. See /tmp/trtexec_build.log"
    return
  fi
}

build_engine "${MODELS_DIR}/${MODEL_NAME_DET}"
build_engine "${MODELS_DIR}/${MODEL_NAME_POSE}"
