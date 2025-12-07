//! Rust AI Worker for Video Analytics
//! 
//! High-performance video analysis worker using ONNX Runtime for inference.
//! Designed to replace Python worker with 10x less RAM and 5x more FPS.

use anyhow::{Context, Result};
use ndarray::{Array, Array4, ArrayView4, s};
use opencv::{
    core::{Mat, Size, Vector, CV_32F, CV_8UC3},
    imgproc,
    prelude::*,
    videoio::{VideoCapture, CAP_ANY, CAP_PROP_FRAME_WIDTH, CAP_PROP_FRAME_HEIGHT},
};
use ort::{GraphOptimizationLevel, Session};
use redis::AsyncCommands;
use serde::{Deserialize, Serialize};
use std::env;
use std::sync::Arc;
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
    input_width: i32,
    input_height: i32,
}

impl Config {
    fn from_env() -> Result<Self> {
        dotenvy::dotenv().ok();
        
        Ok(Self {
            redis_url: env::var("REDIS_URL").unwrap_or_else(|_| "redis://redis:6379".into()),
            model_path: env::var("MODEL_PATH").unwrap_or_else(|_| "/app/models/yolov8n.onnx".into()),
            camera_id: env::var("CAMERA_ID").unwrap_or_else(|_| "1".into()),
            user_id: env::var("USER_ID").unwrap_or_else(|_| "1".into()).parse().unwrap_or(1),
            rtsp_url: env::var("RTSP_URL").context("RTSP_URL environment variable required")?,
            confidence_threshold: env::var("CONFIDENCE_THRESHOLD")
                .unwrap_or_else(|_| "0.5".into())
                .parse()
                .unwrap_or(0.5),
            target_fps: env::var("TARGET_FPS")
                .unwrap_or_else(|_| "25".into())
                .parse()
                .unwrap_or(25),
            input_width: 640,
            input_height: 640,
        })
    }
}

// ============================================================================
// DATA STRUCTURES
// ============================================================================

/// Single detection result
#[derive(Debug, Clone, Serialize, Deserialize)]
struct Detection {
    /// Normalized x coordinate (0-1)
    x: f32,
    /// Normalized y coordinate (0-1)
    y: f32,
    /// Normalized width (0-1)
    w: f32,
    /// Normalized height (0-1)
    h: f32,
    /// Class label
    class: String,
    /// Confidence score (0-1)
    confidence: f32,
    /// Class ID
    class_id: i32,
}

/// Event sent to Redis
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

/// Statistics for monitoring
#[derive(Debug, Default)]
struct Stats {
    frames_processed: u64,
    total_detections: u64,
    avg_inference_ms: f64,
    current_fps: f32,
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
// ONNX INFERENCE ENGINE
// ============================================================================

struct InferenceEngine {
    session: Session,
    input_width: i32,
    input_height: i32,
    confidence_threshold: f32,
}

impl InferenceEngine {
    fn new(model_path: &str, confidence_threshold: f32) -> Result<Self> {
        info!("Loading ONNX model from: {}", model_path);
        
        let session = Session::builder()?
            .with_optimization_level(GraphOptimizationLevel::Level3)?
            .with_intra_threads(4)?
            .commit_from_file(model_path)
            .context("Failed to load ONNX model")?;
        
        info!("✅ Model loaded successfully");
        
        // Log model inputs/outputs
        for (i, input) in session.inputs.iter().enumerate() {
            info!("Input {}: {} - {:?}", i, input.name, input.input_type);
        }
        for (i, output) in session.outputs.iter().enumerate() {
            info!("Output {}: {} - {:?}", i, output.name, output.output_type);
        }
        
        Ok(Self {
            session,
            input_width: 640,
            input_height: 640,
            confidence_threshold,
        })
    }
    
    /// Preprocess frame: BGR -> RGB, resize, normalize to 0-1, NCHW format
    fn preprocess(&self, frame: &Mat) -> Result<Array4<f32>> {
        let mut resized = Mat::default();
        let mut rgb = Mat::default();
        
        // Resize to model input size
        imgproc::resize(
            frame,
            &mut resized,
            Size::new(self.input_width, self.input_height),
            0.0,
            0.0,
            imgproc::INTER_LINEAR,
        )?;
        
        // BGR to RGB
        imgproc::cvt_color(&resized, &mut rgb, imgproc::COLOR_BGR2RGB, 0)?;
        
        // Convert to float and normalize
        let mut float_mat = Mat::default();
        rgb.convert_to(&mut float_mat, CV_32F, 1.0 / 255.0, 0.0)?;
        
        // Get raw data
        let rows = float_mat.rows() as usize;
        let cols = float_mat.cols() as usize;
        let channels = 3usize;
        
        // Create ndarray from Mat data
        let data: Vec<f32> = float_mat
            .data_bytes()?
            .chunks(4)
            .map(|chunk| f32::from_le_bytes([chunk[0], chunk[1], chunk[2], chunk[3]]))
            .collect();
        
        // Reshape to NCHW format: [1, 3, 640, 640]
        let array = Array::from_shape_vec((rows, cols, channels), data)?;
        let array = array.permuted_axes([2, 0, 1]); // HWC -> CHW
        let array = array.insert_axis(ndarray::Axis(0)); // Add batch dimension
        
        Ok(array.to_owned())
    }
    
    /// Run inference and extract detections
    fn infer(&self, input: ArrayView4<f32>, original_width: i32, original_height: i32) -> Result<Vec<Detection>> {
        let outputs = self.session.run(ort::inputs![input]?)?;
        
        // YOLOv8 output shape: [1, 84, 8400] where 84 = 4 (bbox) + 80 (classes)
        let output = outputs[0].try_extract_tensor::<f32>()?;
        let output = output.view();
        
        let mut detections = Vec::new();
        
        // Get dimensions
        let shape = output.shape();
        if shape.len() != 3 {
            warn!("Unexpected output shape: {:?}", shape);
            return Ok(detections);
        }
        
        let num_classes = shape[1] - 4; // 84 - 4 = 80 classes
        let num_predictions = shape[2]; // 8400
        
        // Process each prediction
        for i in 0..num_predictions {
            // Get bounding box (center x, center y, width, height)
            let cx = output[[0, 0, i]];
            let cy = output[[0, 1, i]];
            let w = output[[0, 2, i]];
            let h = output[[0, 3, i]];
            
            // Find best class
            let mut best_class = 0;
            let mut best_conf = 0.0f32;
            
            for c in 0..num_classes {
                let conf = output[[0, 4 + c, i]];
                if conf > best_conf {
                    best_conf = conf;
                    best_class = c;
                }
            }
            
            // Filter by confidence
            if best_conf < self.confidence_threshold {
                continue;
            }
            
            // Convert to normalized coordinates (0-1)
            let x = (cx - w / 2.0) / self.input_width as f32;
            let y = (cy - h / 2.0) / self.input_height as f32;
            let w_norm = w / self.input_width as f32;
            let h_norm = h / self.input_height as f32;
            
            // Clamp to valid range
            let x = x.max(0.0).min(1.0);
            let y = y.max(0.0).min(1.0);
            let w_norm = w_norm.max(0.0).min(1.0 - x);
            let h_norm = h_norm.max(0.0).min(1.0 - y);
            
            let class_name = if best_class < COCO_CLASSES.len() {
                COCO_CLASSES[best_class].to_string()
            } else {
                format!("class_{}", best_class)
            };
            
            detections.push(Detection {
                x,
                y,
                w: w_norm,
                h: h_norm,
                class: class_name,
                confidence: best_conf,
                class_id: best_class as i32,
            });
        }
        
        // Apply NMS (simple version - filter overlapping boxes)
        detections = self.nms(detections, 0.45);
        
        debug!("Found {} detections", detections.len());
        Ok(detections)
    }
    
    /// Simple Non-Maximum Suppression
    fn nms(&self, mut detections: Vec<Detection>, iou_threshold: f32) -> Vec<Detection> {
        // Sort by confidence (descending)
        detections.sort_by(|a, b| b.confidence.partial_cmp(&a.confidence).unwrap());
        
        let mut keep = Vec::new();
        let mut suppressed = vec![false; detections.len()];
        
        for i in 0..detections.len() {
            if suppressed[i] {
                continue;
            }
            
            keep.push(detections[i].clone());
            
            for j in (i + 1)..detections.len() {
                if suppressed[j] {
                    continue;
                }
                
                let iou = self.compute_iou(&detections[i], &detections[j]);
                if iou > iou_threshold && detections[i].class_id == detections[j].class_id {
                    suppressed[j] = true;
                }
            }
        }
        
        keep
    }
    
    /// Compute Intersection over Union
    fn compute_iou(&self, a: &Detection, b: &Detection) -> f32 {
        let x1 = a.x.max(b.x);
        let y1 = a.y.max(b.y);
        let x2 = (a.x + a.w).min(b.x + b.w);
        let y2 = (a.y + a.h).min(b.y + b.h);
        
        let intersection = (x2 - x1).max(0.0) * (y2 - y1).max(0.0);
        let area_a = a.w * a.h;
        let area_b = b.w * b.h;
        let union = area_a + area_b - intersection;
        
        if union > 0.0 {
            intersection / union
        } else {
            0.0
        }
    }
}

// ============================================================================
// VIDEO CAPTURE
// ============================================================================

struct VideoStream {
    capture: VideoCapture,
    width: i32,
    height: i32,
}

impl VideoStream {
    fn new(url: &str) -> Result<Self> {
        info!("Opening video stream: {}", url);
        
        let mut capture = VideoCapture::from_file(url, CAP_ANY)?;
        
        if !capture.is_opened()? {
            anyhow::bail!("Failed to open video stream: {}", url);
        }
        
        let width = capture.get(CAP_PROP_FRAME_WIDTH)? as i32;
        let height = capture.get(CAP_PROP_FRAME_HEIGHT)? as i32;
        
        info!("✅ Stream opened: {}x{}", width, height);
        
        Ok(Self {
            capture,
            width,
            height,
        })
    }
    
    fn read_frame(&mut self) -> Result<Option<Mat>> {
        let mut frame = Mat::default();
        
        if self.capture.read(&mut frame)? && !frame.empty() {
            Ok(Some(frame))
        } else {
            Ok(None)
        }
    }
    
    fn reconnect(&mut self, url: &str) -> Result<()> {
        warn!("Attempting to reconnect to stream...");
        
        // Close current capture
        drop(std::mem::take(&mut self.capture));
        
        // Wait before reconnecting
        std::thread::sleep(Duration::from_secs(2));
        
        // Try to reconnect
        self.capture = VideoCapture::from_file(url, CAP_ANY)?;
        
        if !self.capture.is_opened()? {
            anyhow::bail!("Reconnection failed");
        }
        
        self.width = self.capture.get(CAP_PROP_FRAME_WIDTH)? as i32;
        self.height = self.capture.get(CAP_PROP_FRAME_HEIGHT)? as i32;
        
        info!("✅ Reconnected successfully");
        Ok(())
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
        
        info!("✅ Redis connected, publishing to: {}", channel);
        
        Ok(Self {
            connection,
            channel,
        })
    }
    
    async fn publish(&mut self, event: &CameraEvent) -> Result<()> {
        let json = serde_json::to_string(event)?;
        
        // Publish to camera-specific channel
        self.connection.publish::<_, _, ()>(&self.channel, &json).await?;
        
        // Also publish to general detections channel (for compatibility)
        self.connection.publish::<_, _, ()>("detections", &json).await?;
        
        Ok(())
    }
    
    async fn set_status(&mut self, camera_id: &str, status: &str) -> Result<()> {
        let key = format!("camera:{}:status", camera_id);
        self.connection.set_ex::<_, _, ()>(&key, status, 30).await?;
        Ok(())
    }
}

// ============================================================================
// MAIN WORKER LOOP
// ============================================================================

async fn run_worker(config: Config, mut shutdown: broadcast::Receiver<()>) -> Result<()> {
    // Initialize components
    let engine = InferenceEngine::new(&config.model_path, config.confidence_threshold)?;
    let mut stream = VideoStream::new(&config.rtsp_url)?;
    let mut publisher = RedisPublisher::new(&config.redis_url, &config.camera_id).await?;
    
    // Frame timing
    let frame_duration = Duration::from_millis(1000 / config.target_fps as u64);
    let mut last_frame_time = Instant::now();
    let mut fps_counter = 0u32;
    let mut fps_timer = Instant::now();
    let mut current_fps = 0.0f32;
    
    // Statistics
    let mut frame_number = 0u64;
    let mut total_inference_ms = 0u64;
    let mut consecutive_errors = 0u32;
    
    info!("🚀 Starting main processing loop (target {} FPS)", config.target_fps);
    
    // Set initial status
    publisher.set_status(&config.camera_id, "running").await?;
    
    loop {
        // Check for shutdown signal
        if shutdown.try_recv().is_ok() {
            info!("Shutdown signal received");
            break;
        }
        
        // Maintain target FPS
        let elapsed = last_frame_time.elapsed();
        if elapsed < frame_duration {
            tokio::time::sleep(frame_duration - elapsed).await;
        }
        last_frame_time = Instant::now();
        
        // Read frame
        let frame = match stream.read_frame() {
            Ok(Some(frame)) => {
                consecutive_errors = 0;
                frame
            }
            Ok(None) => {
                warn!("Empty frame received");
                consecutive_errors += 1;
                
                if consecutive_errors > 10 {
                    if let Err(e) = stream.reconnect(&config.rtsp_url) {
                        error!("Reconnection failed: {}", e);
                        tokio::time::sleep(Duration::from_secs(5)).await;
                    }
                    consecutive_errors = 0;
                }
                continue;
            }
            Err(e) => {
                error!("Frame read error: {}", e);
                consecutive_errors += 1;
                
                if consecutive_errors > 10 {
                    if let Err(e) = stream.reconnect(&config.rtsp_url) {
                        error!("Reconnection failed: {}", e);
                        tokio::time::sleep(Duration::from_secs(5)).await;
                    }
                    consecutive_errors = 0;
                }
                continue;
            }
        };
        
        // Preprocess
        let inference_start = Instant::now();
        let input = match engine.preprocess(&frame) {
            Ok(input) => input,
            Err(e) => {
                error!("Preprocessing error: {}", e);
                continue;
            }
        };
        
        // Inference
        let detections = match engine.infer(input.view(), stream.width, stream.height) {
            Ok(dets) => dets,
            Err(e) => {
                error!("Inference error: {}", e);
                continue;
            }
        };
        
        let inference_ms = inference_start.elapsed().as_millis() as u64;
        total_inference_ms += inference_ms;
        frame_number += 1;
        fps_counter += 1;
        
        // Update FPS every second
        if fps_timer.elapsed() >= Duration::from_secs(1) {
            current_fps = fps_counter as f32;
            fps_counter = 0;
            fps_timer = Instant::now();
            
            let avg_ms = if frame_number > 0 {
                total_inference_ms as f64 / frame_number as f64
            } else {
                0.0
            };
            
            info!(
                "📊 FPS: {:.1} | Avg inference: {:.1}ms | Frames: {} | Detections: {}",
                current_fps, avg_ms, frame_number, detections.len()
            );
            
            // Update status in Redis
            let _ = publisher.set_status(&config.camera_id, "running").await;
        }
        
        // Publish event (only if there are detections or periodically)
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
                error!("Failed to publish event: {}", e);
            }
        }
    }
    
    // Cleanup
    publisher.set_status(&config.camera_id, "stopped").await?;
    info!("Worker stopped gracefully");
    
    Ok(())
}

// ============================================================================
// MAIN ENTRY POINT
// ============================================================================

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize logging
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info"))
        )
        .with_target(false)
        .with_thread_ids(true)
        .init();
    
    info!("🦀 Rust AI Worker v{}", env!("CARGO_PKG_VERSION"));
    info!("Starting high-performance video analytics worker...");
    
    // Load configuration
    let config = Config::from_env()?;
    info!("Configuration loaded:");
    info!("  Camera ID: {}", config.camera_id);
    info!("  User ID: {}", config.user_id);
    info!("  RTSP URL: {}", config.rtsp_url);
    info!("  Model: {}", config.model_path);
    info!("  Confidence threshold: {}", config.confidence_threshold);
    info!("  Target FPS: {}", config.target_fps);
    
    // Setup shutdown signal
    let (shutdown_tx, shutdown_rx) = broadcast::channel::<()>(1);
    
    // Handle Ctrl+C
    let shutdown_tx_clone = shutdown_tx.clone();
    tokio::spawn(async move {
        tokio::signal::ctrl_c().await.ok();
        info!("Received Ctrl+C, initiating shutdown...");
        let _ = shutdown_tx_clone.send(());
    });
    
    // Run worker
    if let Err(e) = run_worker(config, shutdown_rx).await {
        error!("Worker error: {}", e);
        return Err(e);
    }
    
    info!("👋 Goodbye!");
    Ok(())
}
