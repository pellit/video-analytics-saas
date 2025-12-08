//! Rust AI Worker for Video Analytics
//! 
//! High-performance video analysis worker using ONNX Runtime for inference.

use anyhow::{Context, Result};
use ndarray::Array4;
use ort::session::{builder::GraphOptimizationLevel, Session};
use ort::value::Tensor;
use redis::AsyncCommands;
use serde::{Deserialize, Serialize};
use std::env;
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
        
        for (i, input) in session.inputs.iter().enumerate() {
            info!("Input {}: {}", i, input.name);
        }
        for (i, output) in session.outputs.iter().enumerate() {
            info!("Output {}: {}", i, output.name);
        }
        
        Ok(Self { session, confidence_threshold })
    }
    
    fn infer(&mut self, input_data: Array4<f32>) -> Result<Vec<Detection>> {
        // Run inference - ort 2.0 API
        // Convert ndarray to shape + vec for ort::Tensor
        let shape = input_data.shape().to_vec();
        let data_vec: Vec<f32> = input_data.into_raw_vec();
        let input_tensor = Tensor::from_array((shape, data_vec.into_boxed_slice()))?;
        
        let outputs = self.session.run(ort::inputs!["images" => input_tensor])?;
        
        // Get first output - extract data before outputs is dropped
        let (shape, data): (Vec<usize>, Vec<f32>) = {
            let output_tensor = &outputs[0];
            let (shape_ref, data_slice) = output_tensor.try_extract_tensor::<f32>()?;
            let shape: Vec<usize> = shape_ref.iter().map(|&d| d as usize).collect();
            let data: Vec<f32> = data_slice.to_vec();
            (shape, data)
        };
        drop(outputs); // Explicitly drop to release the borrow
        
        let mut detections = Vec::new();
        
        if shape.len() != 3 {
            warn!("Unexpected output shape: {:?}", shape);
            return Ok(detections);
        }
        
        let num_classes = shape[1] - 4;  // 84 - 4 = 80
        let num_predictions = shape[2]; // 8400
        
        for i in 0..num_predictions {
            let cx = data[0 * num_predictions + i];
            let cy = data[1 * num_predictions + i];
            let w = data[2 * num_predictions + i];
            let h = data[3 * num_predictions + i];
            
            let mut best_class = 0;
            let mut best_conf = 0.0f32;
            
            for c in 0..num_classes {
                let conf = data[(4 + c) * num_predictions + i];
                if conf > best_conf {
                    best_conf = conf;
                    best_class = c;
                }
            }
            
            if best_conf < self.confidence_threshold {
                continue;
            }
            
            let x = ((cx - w / 2.0) / 640.0).max(0.0).min(1.0);
            let y = ((cy - h / 2.0) / 640.0).max(0.0).min(1.0);
            let w_norm = (w / 640.0).max(0.0).min(1.0 - x);
            let h_norm = (h / 640.0).max(0.0).min(1.0 - y);
            
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
        
        detections = self.nms(detections, 0.45);
        debug!("Found {} detections", detections.len());
        Ok(detections)
    }
    
    fn nms(&self, mut detections: Vec<Detection>, iou_threshold: f32) -> Vec<Detection> {
        detections.sort_by(|a, b| b.confidence.partial_cmp(&a.confidence).unwrap());
        
        let mut keep = Vec::new();
        let mut suppressed = vec![false; detections.len()];
        
        for i in 0..detections.len() {
            if suppressed[i] { continue; }
            keep.push(detections[i].clone());
            
            for j in (i + 1)..detections.len() {
                if suppressed[j] { continue; }
                let iou = self.compute_iou(&detections[i], &detections[j]);
                if iou > iou_threshold && detections[i].class_id == detections[j].class_id {
                    suppressed[j] = true;
                }
            }
        }
        keep
    }
    
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
}

// ============================================================================
// DUMMY VIDEO SOURCE
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
        
        // Create test pattern [1, 3, 640, 640]
        let mut data = vec![0.0f32; 1 * 3 * 640 * 640];
        for c in 0..3 {
            for y in 0..640 {
                for x in 0..640 {
                    let idx = c * 640 * 640 + y * 640 + x;
                    data[idx] = ((x as f32 / 640.0) + (self.frame_count as f32 * 0.01)) % 1.0;
                }
            }
        }
        
        Array4::from_shape_vec((1, 3, 640, 640), data).expect("shape error")
    }
}

// ============================================================================
// MAIN WORKER LOOP
// ============================================================================

async fn run_worker(config: Config, mut shutdown: broadcast::Receiver<()>) -> Result<()> {
    let mut engine = InferenceEngine::new(&config.model_path, config.confidence_threshold)?;
    let mut publisher = RedisPublisher::new(&config.redis_url, &config.camera_id).await?;
    let mut video = DummyVideoSource::new();
    
    info!("⚠️ Using dummy video (OpenCV pending)");
    
    let frame_duration = Duration::from_millis(1000 / config.target_fps as u64);
    let mut last_frame_time = Instant::now();
    let mut fps_counter = 0u32;
    let mut fps_timer = Instant::now();
    let mut current_fps = 0.0f32;
    let mut frame_number = 0u64;
    let mut total_inference_ms = 0u64;
    
    info!("🚀 Starting loop (target {} FPS)", config.target_fps);
    publisher.set_status(&config.camera_id, "running").await?;
    
    loop {
        if shutdown.try_recv().is_ok() {
            info!("Shutdown signal");
            break;
        }
        
        let elapsed = last_frame_time.elapsed();
        if elapsed < frame_duration {
            tokio::time::sleep(frame_duration - elapsed).await;
        }
        last_frame_time = Instant::now();
        
        let inference_start = Instant::now();
        let input = video.next_frame();
        
        let detections = match engine.infer(input) {
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
        
        if fps_timer.elapsed() >= Duration::from_secs(1) {
            current_fps = fps_counter as f32;
            fps_counter = 0;
            fps_timer = Instant::now();
            
            let avg_ms = total_inference_ms as f64 / frame_number as f64;
            info!("📊 FPS: {:.1} | Avg: {:.1}ms | Frames: {}", current_fps, avg_ms, frame_number);
            let _ = publisher.set_status(&config.camera_id, "running").await;
        }
        
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
    
    publisher.set_status(&config.camera_id, "stopped").await?;
    info!("Worker stopped");
    Ok(())
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
    info!("Config: camera={}, model={}", config.camera_id, config.model_path);
    
    let (shutdown_tx, shutdown_rx) = broadcast::channel::<()>(1);
    
    tokio::spawn(async move {
        tokio::signal::ctrl_c().await.ok();
        info!("Ctrl+C");
        let _ = shutdown_tx.send(());
    });
    
    run_worker(config, shutdown_rx).await?;
    info!("👋 Bye!");
    Ok(())
}
