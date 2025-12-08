# ==============================================================================
# STAGE 1: Build Stage
# ==============================================================================
FROM rust:1.85-bookworm AS builder

# Install minimal build dependencies
RUN apt-get update && apt-get install -y \
    cmake \
    pkg-config \
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

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libssl3 \
    ca-certificates \
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
ENV LD_LIBRARY_PATH=/usr/local/lib

# Run the binary
ENTRYPOINT ["/app/rust_ai_worker"]
