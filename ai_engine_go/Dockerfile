# Build stage - using Ubuntu for glibc compatibility with ONNX Runtime
FROM golang:1.22 AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git gcc g++ wget ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install ONNX Runtime for build
RUN wget -q https://github.com/microsoft/onnxruntime/releases/download/v1.17.1/onnxruntime-linux-x64-1.17.1.tgz \
    && tar -xzf onnxruntime-linux-x64-1.17.1.tgz \
    && mv onnxruntime-linux-x64-1.17.1/lib/* /usr/local/lib/ \
    && mv onnxruntime-linux-x64-1.17.1/include/* /usr/local/include/ \
    && rm -rf onnxruntime-linux-x64-1.17.1* \
    && ldconfig

WORKDIR /app

# Copy go mod file
COPY go.mod ./

# Copy source code
COPY . .

# Set CGO and ONNX Runtime paths, then build
ENV CGO_ENABLED=1
ENV CGO_LDFLAGS="-L/usr/local/lib -lonnxruntime"
ENV CGO_CFLAGS="-I/usr/local/include"
ENV LD_LIBRARY_PATH=/usr/local/lib

RUN go mod tidy && go build -o /worker ./cmd/worker

# Runtime stage
FROM ubuntu:22.04

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install ONNX Runtime
RUN wget -q https://github.com/microsoft/onnxruntime/releases/download/v1.17.1/onnxruntime-linux-x64-1.17.1.tgz \
    && tar -xzf onnxruntime-linux-x64-1.17.1.tgz \
    && mv onnxruntime-linux-x64-1.17.1/lib/* /usr/local/lib/ \
    && mv onnxruntime-linux-x64-1.17.1/include/* /usr/local/include/ \
    && rm -rf onnxruntime-linux-x64-1.17.1* \
    && ldconfig

WORKDIR /app

# Copy binary from builder
COPY --from=builder /worker /app/worker

# Create models directory and copy model
RUN mkdir -p /app/models
COPY models/yolov8n.onnx /app/models/

# Environment variables
ENV REDIS_HOST=redis \
    REDIS_PORT=6379 \
    HTTP_PORT=8002 \
    MODEL_PATH=/app/models/yolov8n.onnx \
    NUM_WORKERS=4

EXPOSE 8002

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost:8002/health || exit 1

CMD ["/app/worker"]
