//! Rust AI Worker for Video Analytics
//! 
//! High-performance video analysis worker using ONNX Runtime for inference.
//! Supports RTSP streams via FFmpeg and optimized batch processing.

use anyhow::{Context, Result};
use ndarray::Array4;
use ort::session::{builder::GraphOptimizationLevel, Session};
use ort::value::Tensor;
use redis::AsyncCommands;
use serde::{Deserialize, Serialize};
use std::env;
use std::process::{Child, Command, Stdio};
use std::io::Read;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, Instant};
use tokio::sync::broadcast;
use tracing::{debug, error, info, warn};

// ============================================================================
// CONFIGURATION
// ============================================================================

#[derive(Debug, Clone)]
struct Config {
    redis_url: String,
    model_path: String,
    camera_id: String,
    user_id: i32,
    rtsp_url: String,
    confidence_threshold: f32,
    target_fps: u32,
    use_ffmpeg: bool,
    num_threads: usize,
    skip_frames: u32,
}

impl Config {
    fn from_env() -> Result<Self> {
        dotenvy::dotenv().ok();
        
        let rtsp_url = env::var("RTSP_URL").ok();
        let use_ffmpeg = rtsp_url.is_some() && env::var("USE_FFMPEG").unwrap_or("true".into()) == "true";
        
        Ok(Self {
            redis_url: env::var("REDIS_URL").unwrap_or_else(|_| "redis://redis:6379".into()),
            model_path: env::var("MODEL_PATH").unwrap_or_else(|_| "/app/models/yolov8n.onnx".into()),
            camera_id: env::var("CAMERA_ID").unwrap_or_else(|_| "1".into()),
            user_id: env::var("USER_ID").unwrap_or_else(|_| "1".into()).parse().unwrap_or(1),
            rtsp_url: rtsp_url.unwrap_or_else(|| "dummy://test".into()),
            confidence_threshold: env::var("CONFIDENCE_THRESHOLD")
                .unwrap_or_else(|_| "0.5".into())
                .parse()
                .unwrap_or(0.5),
            target_fps: env::var("TARGET_FPS")
                .unwrap_or_else(|_| "10".into())
                .parse()
                .unwrap_or(10),
            use_ffmpeg,
            num_threads: env::var("NUM_THREADS")
                .unwrap_or_else(|_| "4".into())
                .parse()
                .unwrap_or(4),
            skip_frames: env::var("SKIP_FRAMES")
                .unwrap_or_else(|_| "2".into())
                .parse()
                .unwrap_or(2),
        })
    }
}

// ============================================================================
// DATA STRUCTURES
// ============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
struct Detection {
    x: f32,
    y: f32,
    w: f32,
    h: f32,
    class: String,
    confidence: f32,
    class_id: i32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct CameraEvent {
    #[serde(rename = "type")]
    event_type: String,
    camera_id: String,
    user_id: i32,
    detections: Vec<Detection>,
    frame_number: u64,
    processing_ms: u64,
    fps: f32,
    timestamp: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct BenchmarkResult {
    worker_type: String,
    avg_inference_ms: f64,
    min_inference_ms: u64,
    max_inference_ms: u64,
    fps: f32,
    total_frames: u64,
    memory_mb: f64,
}

// ============================================================================
// COCO CLASS LABELS
// ============================================================================

const COCO_CLASSES: [&str; 80] = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
    "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench",
    "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra",
    "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
    "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup",
    "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier",
    "toothbrush"
];

// ============================================================================
// OPTIMIZED ONNX INFERENCE ENGINE
// ============================================================================

struct InferenceEngine {
    session: Session,
    confidence_threshold: f32,
    // Statistics
    inference_count: AtomicU64,
    total_time_us: AtomicU64,
    min_time_us: AtomicU64,
    max_time_us: AtomicU64,
}

impl InferenceEngine {
    fn new(model_path: &str, confidence_threshold: f32, num_threads: usize) -> Result<Self> {
        info!("Loading ONNX model from: {}", model_path);
        info!("Using {} inference threads", num_threads);
        
        // Optimized session configuration
        let session = Session::builder()?
            .with_optimization_level(GraphOptimizationLevel::Level3)?
            .with_intra_threads(num_threads)?
            .commit_from_file(model_path)
            .context("Failed to load ONNX model")?;
        
        info!("✅ Model loaded successfully");
        
        for (i, input) in session.inputs.iter().enumerate() {
            info!("Input {}: {}", i, input.name);
        }
        for (i, output) in session.outputs.iter().enumerate() {
            info!("Output {}: {}", i, output.name);
        }
        
        Ok(Self { 
            session, 
            confidence_threshold,
            inference_count: AtomicU64::new(0),
            total_time_us: AtomicU64::new(0),
            min_time_us: AtomicU64::new(u64::MAX),
            max_time_us: AtomicU64::new(0),
        })
    }
    
    fn infer(&mut self, input_data: Array4<f32>) -> Result<Vec<Detection>> {
        let start = Instant::now();
        
        // Convert ndarray to shape + vec for ort::Tensor
        let shape = input_data.shape().to_vec();
        let data_vec: Vec<f32> = input_data.into_raw_vec();
        let input_tensor = Tensor::from_array((shape, data_vec.into_boxed_slice()))?;
        
        let outputs = self.session.run(ort::inputs!["images" => input_tensor])?;
        
        // Extract output data
        let (shape, data): (Vec<usize>, Vec<f32>) = {
            let output_tensor = &outputs[0];
            let (shape_ref, data_slice) = output_tensor.try_extract_tensor::<f32>()?;
            let shape: Vec<usize> = shape_ref.iter().map(|&d| d as usize).collect();
            let data: Vec<f32> = data_slice.to_vec();
            (shape, data)
        };
        drop(outputs);
        
        // Update statistics
        let elapsed_us = start.elapsed().as_micros() as u64;
        self.inference_count.fetch_add(1, Ordering::Relaxed);
        self.total_time_us.fetch_add(elapsed_us, Ordering::Relaxed);
        self.min_time_us.fetch_min(elapsed_us, Ordering::Relaxed);
        self.max_time_us.fetch_max(elapsed_us, Ordering::Relaxed);
        
        // Parse detections
        let detections = self.parse_yolo_output(&shape, &data);
        
        // Apply NMS
        let detections = self.nms(detections, 0.45);
        debug!("Found {} detections in {}us", detections.len(), elapsed_us);
        
        Ok(detections)
    }
    
    #[inline]
    fn parse_yolo_output(&self, shape: &[usize], data: &[f32]) -> Vec<Detection> {
        let mut detections = Vec::with_capacity(100); // Pre-allocate
        
        if shape.len() != 3 {
            warn!("Unexpected output shape: {:?}", shape);
            return detections;
        }
        
        let num_classes = shape[1] - 4;  // 84 - 4 = 80
        let num_predictions = shape[2]; // 8400
        
        for i in 0..num_predictions {
            // Get bounding box
            let cx = data[0 * num_predictions + i];
            let cy = data[1 * num_predictions + i];
            let w = data[2 * num_predictions + i];
            let h = data[3 * num_predictions + i];
            
            // Find best class with SIMD-friendly loop
            let mut best_class = 0usize;
            let mut best_conf = 0.0f32;
            
            for c in 0..num_classes {
                let conf = data[(4 + c) * num_predictions + i];
                if conf > best_conf {
                    best_conf = conf;
                    best_class = c;
                }
            }
            
            // Early exit for low confidence
            if best_conf < self.confidence_threshold {
                continue;
            }
            
            // Normalize coordinates
            let x = ((cx - w / 2.0) / 640.0).clamp(0.0, 1.0);
            let y = ((cy - h / 2.0) / 640.0).clamp(0.0, 1.0);
            let w_norm = (w / 640.0).clamp(0.0, 1.0 - x);
            let h_norm = (h / 640.0).clamp(0.0, 1.0 - y);
            
            let class_name = if best_class < COCO_CLASSES.len() {
                COCO_CLASSES[best_class].to_string()
            } else {
                format!("class_{}", best_class)
            };
            
            detections.push(Detection {
                x, y, w: w_norm, h: h_norm,
                class: class_name,
                confidence: best_conf,
                class_id: best_class as i32,
            });
        }
        
        detections
    }
    
    fn nms(&self, mut detections: Vec<Detection>, iou_threshold: f32) -> Vec<Detection> {
        if detections.len() <= 1 {
            return detections;
        }
        
        // Sort by confidence descending
        detections.sort_unstable_by(|a, b| {
            b.confidence.partial_cmp(&a.confidence).unwrap_or(std::cmp::Ordering::Equal)
        });
        
        let mut keep = Vec::with_capacity(detections.len());
        let mut suppressed = vec![false; detections.len()];
        
        for i in 0..detections.len() {
            if suppressed[i] { continue; }
            keep.push(detections[i].clone());
            
            for j in (i + 1)..detections.len() {
                if suppressed[j] { continue; }
                if detections[i].class_id != detections[j].class_id { continue; }
                
                let iou = self.compute_iou(&detections[i], &detections[j]);
                if iou > iou_threshold {
                    suppressed[j] = true;
                }
            }
        }
        keep
    }
    
    #[inline]
    fn compute_iou(&self, a: &Detection, b: &Detection) -> f32 {
        let x1 = a.x.max(b.x);
        let y1 = a.y.max(b.y);
        let x2 = (a.x + a.w).min(b.x + b.w);
        let y2 = (a.y + a.h).min(b.y + b.h);
        
        let intersection = (x2 - x1).max(0.0) * (y2 - y1).max(0.0);
        let area_a = a.w * a.h;
        let area_b = b.w * b.h;
        let union = area_a + area_b - intersection;
        
        if union > 0.0 { intersection / union } else { 0.0 }
    }
    
    fn get_stats(&self) -> (f64, u64, u64, u64) {
        let count = self.inference_count.load(Ordering::Relaxed);
        let total = self.total_time_us.load(Ordering::Relaxed);
        let min = self.min_time_us.load(Ordering::Relaxed);
        let max = self.max_time_us.load(Ordering::Relaxed);
        
        let avg = if count > 0 { total as f64 / count as f64 / 1000.0 } else { 0.0 };
        (avg, min / 1000, max / 1000, count)
    }
    
    fn reset_stats(&self) {
        self.inference_count.store(0, Ordering::Relaxed);
        self.total_time_us.store(0, Ordering::Relaxed);
        self.min_time_us.store(u64::MAX, Ordering::Relaxed);
        self.max_time_us.store(0, Ordering::Relaxed);
    }
}

// ============================================================================
// FFMPEG VIDEO SOURCE (RTSP)
// ============================================================================

struct FFmpegVideoSource {
    process: Child,
    width: u32,
    height: u32,
    frame_count: u64,
    frame_buffer: Vec<u8>,
}

impl FFmpegVideoSource {
    fn new(rtsp_url: &str, target_fps: u32) -> Result<Self> {
        info!("Opening RTSP stream via FFmpeg: {}", rtsp_url);
        
        // Target dimensions
        let width = 640u32;
        let height = 640u32;
        
        // FFmpeg command to decode RTSP and output raw RGB frames
        let process = Command::new("ffmpeg")
            .args([
                "-rtsp_transport", "tcp",
                "-i", rtsp_url,
                "-vf", &format!("scale={}:{},fps={}", width, height, target_fps),
                "-f", "rawvideo",
                "-pix_fmt", "rgb24",
                "-an",  // No audio
                "-"     // Output to stdout
            ])
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .context("Failed to start FFmpeg - is it installed?")?;
        
        info!("✅ FFmpeg started for RTSP capture");
        
        // Pre-allocate frame buffer (RGB24: 3 bytes per pixel)
        let frame_buffer = vec![0u8; (width * height * 3) as usize];
        
        Ok(Self {
            process,
            width,
            height,
            frame_count: 0,
            frame_buffer,
        })
    }
    
    fn next_frame(&mut self) -> Option<Array4<f32>> {
        let stdout = self.process.stdout.as_mut()?;
        
        // Read exactly one frame worth of RGB data
        let frame_size = (self.width * self.height * 3) as usize;
        self.frame_buffer.resize(frame_size, 0);
        
        match stdout.read_exact(&mut self.frame_buffer) {
            Ok(_) => {
                self.frame_count += 1;
                Some(self.rgb_to_tensor())
            }
            Err(_) => None
        }
    }
    
    fn rgb_to_tensor(&self) -> Array4<f32> {
        let w = self.width as usize;
        let h = self.height as usize;
        
        // Convert RGB bytes to CHW float tensor with normalization
        let mut data = vec![0.0f32; 1 * 3 * h * w];
        
        for y in 0..h {
            for x in 0..w {
                let pixel_idx = (y * w + x) * 3;
                let r = self.frame_buffer[pixel_idx] as f32 / 255.0;
                let g = self.frame_buffer[pixel_idx + 1] as f32 / 255.0;
                let b = self.frame_buffer[pixel_idx + 2] as f32 / 255.0;
                
                // CHW format
                data[0 * h * w + y * w + x] = r;
                data[1 * h * w + y * w + x] = g;
                data[2 * h * w + y * w + x] = b;
            }
        }
        
        Array4::from_shape_vec((1, 3, h, w), data).expect("shape error")
    }
    
    fn frame_count(&self) -> u64 {
        self.frame_count
    }
}

impl Drop for FFmpegVideoSource {
    fn drop(&mut self) {
        let _ = self.process.kill();
    }
}

// ============================================================================
// DUMMY VIDEO SOURCE (for testing without RTSP)
// ============================================================================

struct DummyVideoSource {
    frame_count: u64,
}

impl DummyVideoSource {
    fn new() -> Self {
        Self { frame_count: 0 }
    }
    
    fn next_frame(&mut self) -> Array4<f32> {
        self.frame_count += 1;
        
        // Create minimal test pattern [1, 3, 640, 640]
        // Optimized: use zeros with small variation
        let size = 1 * 3 * 640 * 640;
        let mut data = vec![0.5f32; size];
        
        // Add minimal variation to prevent optimization artifacts
        let offset = (self.frame_count % 100) as f32 * 0.001;
        data[0] = offset;
        data[size - 1] = offset;
        
        Array4::from_shape_vec((1, 3, 640, 640), data).expect("shape error")
    }
    
    fn frame_count(&self) -> u64 {
        self.frame_count
    }
}

// ============================================================================
// REDIS PUBLISHER
// ============================================================================

struct RedisPublisher {
    connection: redis::aio::MultiplexedConnection,
    channel: String,
}

impl RedisPublisher {
    async fn new(redis_url: &str, camera_id: &str) -> Result<Self> {
        info!("Connecting to Redis: {}", redis_url);
        let client = redis::Client::open(redis_url)?;
        let connection = client.get_multiplexed_async_connection().await?;
        let channel = format!("camera:{}:detections", camera_id);
        info!("✅ Redis connected");
        Ok(Self { connection, channel })
    }
    
    async fn publish(&mut self, event: &CameraEvent) -> Result<()> {
        let json = serde_json::to_string(event)?;
        self.connection.publish::<_, _, ()>(&self.channel, &json).await?;
        self.connection.publish::<_, _, ()>("detections", &json).await?;
        Ok(())
    }
    
    async fn set_status(&mut self, camera_id: &str, status: &str) -> Result<()> {
        let key = format!("camera:{}:status", camera_id);
        self.connection.set_ex::<_, _, ()>(&key, status, 30).await?;
        Ok(())
    }
    
    async fn publish_benchmark(&mut self, benchmark: &BenchmarkResult) -> Result<()> {
        let json = serde_json::to_string(benchmark)?;
        self.connection.publish::<_, _, ()>("benchmarks", &json).await?;
        self.connection.set::<_, _, ()>("benchmark:rust_worker", &json).await?;
        Ok(())
    }
}

// ============================================================================
// VIDEO SOURCE TRAIT
// ============================================================================

enum VideoSource {
    FFmpeg(FFmpegVideoSource),
    Dummy(DummyVideoSource),
}

impl VideoSource {
    fn next_frame(&mut self) -> Option<Array4<f32>> {
        match self {
            VideoSource::FFmpeg(src) => src.next_frame(),
            VideoSource::Dummy(src) => Some(src.next_frame()),
        }
    }
    
    fn frame_count(&self) -> u64 {
        match self {
            VideoSource::FFmpeg(src) => src.frame_count(),
            VideoSource::Dummy(src) => src.frame_count(),
        }
    }
}

// ============================================================================
// MAIN WORKER LOOP
// ============================================================================

async fn run_worker(config: Config, mut shutdown: broadcast::Receiver<()>) -> Result<()> {
    let mut engine = InferenceEngine::new(&config.model_path, config.confidence_threshold, config.num_threads)?;
    let mut publisher = RedisPublisher::new(&config.redis_url, &config.camera_id).await?;
    
    // Initialize video source
    let mut video = if config.use_ffmpeg && !config.rtsp_url.starts_with("dummy://") {
        match FFmpegVideoSource::new(&config.rtsp_url, config.target_fps) {
            Ok(src) => {
                info!("📹 Using FFmpeg for RTSP: {}", config.rtsp_url);
                VideoSource::FFmpeg(src)
            }
            Err(e) => {
                warn!("⚠️ FFmpeg failed ({}), using dummy source", e);
                VideoSource::Dummy(DummyVideoSource::new())
            }
        }
    } else {
        info!("⚠️ Using dummy video source (set RTSP_URL for real video)");
        VideoSource::Dummy(DummyVideoSource::new())
    };
    
    let frame_duration = Duration::from_millis(1000 / config.target_fps as u64);
    let mut last_frame_time = Instant::now();
    let mut fps_counter = 0u32;
    let mut fps_timer = Instant::now();
    let mut current_fps = 0.0f32;
    let mut frame_number = 0u64;
    let mut skip_counter = 0u32;
    
    info!("🚀 Starting processing loop");
    info!("   Target FPS: {}", config.target_fps);
    info!("   Skip frames: {} (process 1 in {})", config.skip_frames, config.skip_frames + 1);
    info!("   Confidence: {}", config.confidence_threshold);
    publisher.set_status(&config.camera_id, "running").await?;
    
    loop {
        // Check shutdown
        if shutdown.try_recv().is_ok() {
            info!("Shutdown signal received");
            break;
        }
        
        // Rate limiting
        let elapsed = last_frame_time.elapsed();
        if elapsed < frame_duration {
            tokio::time::sleep(frame_duration - elapsed).await;
        }
        last_frame_time = Instant::now();
        
        // Get frame
        let frame = match video.next_frame() {
            Some(f) => f,
            None => {
                warn!("Video source ended");
                break;
            }
        };
        
        frame_number = video.frame_count();
        
        // Skip frames for higher throughput
        skip_counter += 1;
        if skip_counter <= config.skip_frames {
            continue;
        }
        skip_counter = 0;
        
        // Run inference
        let inference_start = Instant::now();
        let detections = match engine.infer(frame) {
            Ok(dets) => dets,
            Err(e) => {
                error!("Inference error: {}", e);
                continue;
            }
        };
        let inference_ms = inference_start.elapsed().as_millis() as u64;
        
        fps_counter += 1;
        
        // Log stats every second
        if fps_timer.elapsed() >= Duration::from_secs(1) {
            current_fps = fps_counter as f32;
            fps_counter = 0;
            fps_timer = Instant::now();
            
            let (avg_ms, min_ms, max_ms, count) = engine.get_stats();
            info!("📊 FPS: {:.1} | Inference: avg={:.1}ms min={}ms max={}ms | Frames: {}", 
                  current_fps, avg_ms, min_ms, max_ms, count);
            
            let _ = publisher.set_status(&config.camera_id, "running").await;
        }
        
        // Publish detections
        if !detections.is_empty() || frame_number % 30 == 0 {
            let event = CameraEvent {
                event_type: "detections".to_string(),
                camera_id: config.camera_id.clone(),
                user_id: config.user_id,
                detections,
                frame_number,
                processing_ms: inference_ms,
                fps: current_fps,
                timestamp: chrono::Utc::now().to_rfc3339(),
            };
            
            if let Err(e) = publisher.publish(&event).await {
                error!("Publish error: {}", e);
            }
        }
    }
    
    // Final stats
    let (avg_ms, min_ms, max_ms, count) = engine.get_stats();
    info!("📈 Final Statistics:");
    info!("   Total frames processed: {}", count);
    info!("   Avg inference time: {:.2}ms", avg_ms);
    info!("   Min inference time: {}ms", min_ms);
    info!("   Max inference time: {}ms", max_ms);
    
    // Publish benchmark
    let benchmark = BenchmarkResult {
        worker_type: "rust".to_string(),
        avg_inference_ms: avg_ms,
        min_inference_ms: min_ms,
        max_inference_ms: max_ms,
        fps: current_fps,
        total_frames: count,
        memory_mb: get_memory_usage_mb(),
    };
    let _ = publisher.publish_benchmark(&benchmark).await;
    
    publisher.set_status(&config.camera_id, "stopped").await?;
    info!("Worker stopped");
    Ok(())
}

// ============================================================================
// BENCHMARK MODE
// ============================================================================

async fn run_benchmark(config: Config, iterations: u64) -> Result<BenchmarkResult> {
    info!("🏁 Running benchmark mode ({} iterations)", iterations);
    
    let mut engine = InferenceEngine::new(&config.model_path, config.confidence_threshold, config.num_threads)?;
    let mut dummy = DummyVideoSource::new();
    
    // Warmup
    info!("Warmup (10 iterations)...");
    for _ in 0..10 {
        let frame = dummy.next_frame();
        let _ = engine.infer(frame)?;
    }
    
    // Reset stats after warmup
    engine.reset_stats();
    
    // Benchmark
    info!("Running benchmark...");
    let start = Instant::now();
    
    for i in 0..iterations {
        let frame = dummy.next_frame();
        let detections = engine.infer(frame)?;
        
        if i % 100 == 0 {
            debug!("Iteration {}/{}, detections: {}", i, iterations, detections.len());
        }
    }
    
    let total_time = start.elapsed();
    let (avg_ms, min_ms, max_ms, count) = engine.get_stats();
    let fps = count as f32 / total_time.as_secs_f32();
    
    let result = BenchmarkResult {
        worker_type: "rust".to_string(),
        avg_inference_ms: avg_ms,
        min_inference_ms: min_ms,
        max_inference_ms: max_ms,
        fps,
        total_frames: count,
        memory_mb: get_memory_usage_mb(),
    };
    
    info!("🏆 Benchmark Results:");
    info!("   Worker: Rust");
    info!("   Iterations: {}", iterations);
    info!("   Total time: {:.2}s", total_time.as_secs_f32());
    info!("   Throughput: {:.2} FPS", fps);
    info!("   Avg inference: {:.2}ms", avg_ms);
    info!("   Min inference: {}ms", min_ms);
    info!("   Max inference: {}ms", max_ms);
    info!("   Memory: {:.1}MB", result.memory_mb);
    
    Ok(result)
}

fn get_memory_usage_mb() -> f64 {
    // Try to read from /proc/self/status on Linux
    if let Ok(status) = std::fs::read_to_string("/proc/self/status") {
        for line in status.lines() {
            if line.starts_with("VmRSS:") {
                if let Some(kb_str) = line.split_whitespace().nth(1) {
                    if let Ok(kb) = kb_str.parse::<f64>() {
                        return kb / 1024.0;
                    }
                }
            }
        }
    }
    0.0
}

// ============================================================================
// MAIN
// ============================================================================

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info"))
        )
        .with_target(false)
        .init();
    
    info!("🦀 Rust AI Worker v{}", env!("CARGO_PKG_VERSION"));
    
    let config = Config::from_env()?;
    info!("Configuration:");
    info!("   Camera ID: {}", config.camera_id);
    info!("   Model: {}", config.model_path);
    info!("   Threads: {}", config.num_threads);
    info!("   Target FPS: {}", config.target_fps);
    
    // Check for benchmark mode
    if env::var("BENCHMARK_MODE").is_ok() {
        let iterations: u64 = env::var("BENCHMARK_ITERATIONS")
            .unwrap_or_else(|_| "1000".into())
            .parse()
            .unwrap_or(1000);
        
        let result = run_benchmark(config.clone(), iterations).await?;
        
        // Publish to Redis if available
        if let Ok(mut publisher) = RedisPublisher::new(&config.redis_url, &config.camera_id).await {
            let _ = publisher.publish_benchmark(&result).await;
        }
        
        return Ok(());
    }
    
    let (shutdown_tx, shutdown_rx) = broadcast::channel::<()>(1);
    
    tokio::spawn(async move {
        tokio::signal::ctrl_c().await.ok();
        info!("Ctrl+C received");
        let _ = shutdown_tx.send(());
    });
    
    run_worker(config, shutdown_rx).await?;
    info!("👋 Bye!");
    Ok(())
}
