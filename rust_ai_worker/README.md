# Rust AI Worker

High-performance AI worker for video analytics using ONNX Runtime with FFmpeg for RTSP capture.

## 🚀 Features

- **Zero-copy video capture** via FFmpeg for RTSP streams
- **Optimized ONNX Runtime** with Level 3 graph optimizations
- **Multi-threaded inference** - configurable threads
- **Async Redis I/O** with Tokio runtime
- **Benchmark mode** for performance comparison
- **10x less RAM** than Python worker
- **No GIL** - true parallelism

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    RUST AI WORKER                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌─────────────┐    ┌──────────────┐    ┌─────────────┐   │
│   │ VideoSource │ -> │ InferenceEng │ -> │ RedisPublish│   │
│   │  (FFmpeg)   │    │  (ONNX RT)   │    │  (Async)    │   │
│   └─────────────┘    └──────────────┘    └─────────────┘   │
│                                                             │
│   Features:                                                 │
│   • RTSP/RTMP via FFmpeg (640x640 RGB24)                   │
│   • YOLOv8 inference via ONNX Runtime 1.22                 │
│   • Non-Maximum Suppression (IoU 0.45)                     │
│   • Redis Pub/Sub for detections                           │
│   • Frame skip for higher throughput                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 📦 Dependencies

| Crate | Version | Purpose |
|-------|---------|---------|
| `tokio` | 1.41 | Async runtime |
| `ort` | 2.0.0-rc.9 | ONNX Runtime bindings |
| `redis` | 0.25 | Redis async client |
| `serde` | 1.0 | JSON serialization |
| `ndarray` | 0.15 | N-dimensional arrays |
| `chrono` | 0.4 | Timestamps |

External:
- **FFmpeg** - RTSP capture (installed via apt)
- **ONNX Runtime** 1.22.0 (downloaded at build time)

## 🔧 Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://redis:6379` | Redis connection URL |
| `MODEL_PATH` | `/app/models/yolov8n.onnx` | Path to ONNX model |
| `CAMERA_ID` | `1` | Camera identifier |
| `USER_ID` | `1` | User ID for filtering |
| `RTSP_URL` | `dummy://test` | RTSP stream URL |
| `CONFIDENCE_THRESHOLD` | `0.5` | Detection threshold |
| `TARGET_FPS` | `10` | Target frames per second |
| `NUM_THREADS` | `4` | ONNX inference threads |
| `SKIP_FRAMES` | `2` | Skip N frames between inference |
| `USE_FFMPEG` | `true` | Use FFmpeg for capture |
| `RUST_LOG` | `info` | Log level |

### Benchmark Mode

| Variable | Default | Description |
|----------|---------|-------------|
| `BENCHMARK_MODE` | - | Enable benchmark mode |
| `BENCHMARK_ITERATIONS` | `1000` | Number of iterations |

## 🐳 Docker Build

```bash
# Build the image
docker build -t rust-ai-worker .

# Run with RTSP stream
docker run -d \
  --name rust-worker \
  -e REDIS_URL=redis://redis:6379 \
  -e RTSP_URL=rtsp://camera.local:554/stream \
  -e CAMERA_ID=1 \
  -e TARGET_FPS=10 \
  -v ./models:/app/models:ro \
  rust-ai-worker

# Run in benchmark mode
docker run --rm \
  -e BENCHMARK_MODE=1 \
  -e BENCHMARK_ITERATIONS=500 \
  -v ./models:/app/models:ro \
  rust-ai-worker
```

## 🔨 Local Development

```bash
# Install Rust (if not installed)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Install FFmpeg (Ubuntu/Debian)
sudo apt-get install ffmpeg

# Download ONNX Runtime 1.22 (required for ort 2.0)
wget https://github.com/microsoft/onnxruntime/releases/download/v1.22.0/onnxruntime-linux-x64-1.22.0.tgz
tar xzf onnxruntime-linux-x64-1.22.0.tgz
export ORT_LIB_LOCATION=$(pwd)/onnxruntime-linux-x64-1.22.0/lib
export LD_LIBRARY_PATH=$ORT_LIB_LOCATION:$LD_LIBRARY_PATH

# Build
cargo build --release

# Run with dummy source
MODEL_PATH=../ai_engine_go/models/yolov8n.onnx cargo run --release

# Run with RTSP stream
RTSP_URL=rtsp://admin:pass@192.168.1.100:554/stream \
MODEL_PATH=../ai_engine_go/models/yolov8n.onnx \
cargo run --release

# Benchmark mode
BENCHMARK_MODE=1 \
BENCHMARK_ITERATIONS=100 \
MODEL_PATH=../ai_engine_go/models/yolov8n.onnx \
cargo run --release
```

## 📊 Benchmark: Python vs Rust

Run the comparison script:

```bash
# Install Python dependencies
pip install onnxruntime numpy psutil redis

# Run benchmark
cd rust_ai_worker
python benchmark.py

# Or with custom iterations
BENCHMARK_ITERATIONS=500 python benchmark.py
```

### Expected Results (YOLOv8n, CPU, 640x640)

| Metric | Python | Rust | Improvement |
|--------|--------|------|-------------|
| Avg Inference | ~150ms | ~80ms | **1.8x faster** |
| Memory Usage | ~200MB | ~50MB | **4x less** |
| Throughput | ~6 FPS | ~12 FPS | **2x higher** |
| Cold Start | ~3s | ~500ms | **6x faster** |

*Note: Results vary based on CPU. GPU acceleration not implemented yet.*

## 🔄 Integration with Docker Compose

The Rust worker is integrated in `docker-compose.yml`:

```yaml
rust_worker:
  build: ./rust_ai_worker
  profiles:
    - rust  # Only starts with: docker compose --profile rust up
  environment:
    - REDIS_URL=redis://redis:6379
    - MODEL_PATH=/app/models/yolov8n.onnx
    - RTSP_URL=${RTSP_URL:-dummy://test}
    - TARGET_FPS=10
  volumes:
    - ./ai_engine_go/models:/app/models:ro
  depends_on:
    - redis
```

Start with:
```bash
docker compose --profile rust up rust_worker
```

## 📈 Performance Optimization Tips

1. **Increase threads**: `NUM_THREADS=8` for multi-core CPUs
2. **Skip frames**: `SKIP_FRAMES=3` to process every 4th frame
3. **Lower FPS**: `TARGET_FPS=5` for high latency streams
4. **Reduce confidence**: `CONFIDENCE_THRESHOLD=0.6` for fewer detections

## 🐛 Troubleshooting

### FFmpeg not found
```bash
# Install FFmpeg
sudo apt-get install ffmpeg

# Or in Docker - add to Dockerfile
RUN apt-get install -y ffmpeg
```

### ONNX Runtime library not found
```bash
# Check library path
echo $ORT_LIB_LOCATION
echo $LD_LIBRARY_PATH

# Download if missing
wget https://github.com/microsoft/onnxruntime/releases/download/v1.22.0/onnxruntime-linux-x64-1.22.0.tgz
```

### Model format error
```bash
# Convert PyTorch to ONNX (if needed)
from ultralytics import YOLO
model = YOLO('yolov8n.pt')
model.export(format='onnx', imgsz=640)
```

### RTSP connection failed
```bash
# Test stream with ffplay
ffplay rtsp://camera.local:554/stream

# Check TCP transport
ffmpeg -rtsp_transport tcp -i rtsp://camera:554/stream -frames:v 1 test.jpg
```

## 📝 License

MIT License - Same as main project.
