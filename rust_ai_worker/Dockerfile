# ==============================================================================
# STAGE 1: Build Stage
# ==============================================================================
# Use Rust with all build dependencies
FROM rust:1.83-bookworm AS builder

# Install build dependencies for OpenCV and ONNX Runtime
RUN apt-get update && apt-get install -y \
    cmake \
    pkg-config \
    libclang-dev \
    clang \
    # OpenCV dependencies
    libopencv-dev \
    libopencv-videoio-dev \
    libopencv-imgproc-dev \
    libopencv-core-dev \
    # FFmpeg for video codecs
    libavcodec-dev \
    libavformat-dev \
    libavutil-dev \
    libswscale-dev \
    # SSL
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy manifests first for better layer caching
COPY Cargo.toml Cargo.lock* ./

# Create dummy main.rs for dependency caching
RUN mkdir src && \
    echo "fn main() {}" > src/main.rs && \
    cargo build --release && \
    rm -rf src

# Copy actual source code
COPY src ./src

# Build the actual application (touch main.rs to force rebuild)
RUN touch src/main.rs && \
    cargo build --release

# ==============================================================================
# STAGE 2: Runtime Stage
# ==============================================================================
FROM debian:bookworm-slim AS runtime

# Install runtime dependencies only (much smaller)
RUN apt-get update && apt-get install -y --no-install-recommends \
    # OpenCV runtime libraries
    libopencv-videoio406 \
    libopencv-imgproc406 \
    libopencv-core406 \
    # FFmpeg runtime
    libavcodec59 \
    libavformat59 \
    libavutil57 \
    libswscale6 \
    # SSL runtime
    libssl3 \
    ca-certificates \
    # For debugging (optional, can remove in production)
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN useradd -m -u 1000 -s /bin/bash worker

# Create directories
WORKDIR /app
RUN mkdir -p /app/models && chown -R worker:worker /app

# Copy the compiled binary from builder stage
COPY --from=builder /app/target/release/rust_ai_worker /app/rust_ai_worker

# Download ONNX Runtime library (needed at runtime)
ARG ORT_VERSION=1.19.2
RUN curl -L -o /tmp/ort.tgz \
    https://github.com/microsoft/onnxruntime/releases/download/v${ORT_VERSION}/onnxruntime-linux-x64-${ORT_VERSION}.tgz && \
    tar -xzf /tmp/ort.tgz -C /tmp && \
    cp /tmp/onnxruntime-linux-x64-${ORT_VERSION}/lib/*.so* /usr/local/lib/ && \
    ldconfig && \
    rm -rf /tmp/ort.tgz /tmp/onnxruntime-linux-x64-${ORT_VERSION}

# Set ownership
RUN chown worker:worker /app/rust_ai_worker

# Switch to non-root user
USER worker

# Environment variables
ENV RUST_LOG=info
ENV RUST_BACKTRACE=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the binary
ENTRYPOINT ["/app/rust_ai_worker"]
