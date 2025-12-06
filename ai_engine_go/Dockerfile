# Build stage
FROM golang:1.22-alpine AS builder

# Install build dependencies
RUN apk add --no-cache git gcc musl-dev

WORKDIR /app

# Copy go mod files
COPY go.mod go.sum ./
RUN go mod download

# Copy source code
COPY . .

# Build the binary
RUN CGO_ENABLED=0 GOOS=linux go build -o /worker ./cmd/worker

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

# Create models directory
RUN mkdir -p /app/models

# Copy models (will be mounted or downloaded)
COPY models/*.onnx /app/models/

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
