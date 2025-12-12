//! Benchmark ONNX Inference for Rust
//! 
//! Compares inference performance using ONNX Runtime

use anyhow::Result;
use ndarray::Array4;
use ort::session::{builder::GraphOptimizationLevel, Session};
use ort::value::Tensor;
use serde::Serialize;
use std::env;
use std::time::Instant;
use rand::Rng;

const ITERATIONS: usize = 100;
const WARMUP: usize = 10;
const WIDTH: usize = 640;
const HEIGHT: usize = 640;

#[derive(Serialize)]
struct Stats {
    mean: f64,
    std: f64,
    min: f64,
    max: f64,
    p50: f64,
    p95: f64,
    p99: f64,
}

#[derive(Serialize)]
struct BenchmarkResult {
    language: String,
    runtime: String,
    model: String,
    model_size_mb: f64,
    load_time_s: f64,
    input_shape: Vec<usize>,
    iterations: usize,
    inference_ms: Stats,
    inference_fps: f64,
    pipeline_ms: Stats,
    pipeline_fps: f64,
}

fn calc_stats(times: &[f64]) -> Stats {
    let n = times.len() as f64;
    let mean = times.iter().sum::<f64>() / n;
    let variance = times.iter().map(|t| (t - mean).powi(2)).sum::<f64>() / (n - 1.0);
    let std = variance.sqrt();
    
    let mut sorted = times.to_vec();
    sorted.sort_by(|a, b| a.partial_cmp(b).unwrap());
    
    Stats {
        mean,
        std,
        min: sorted[0],
        max: sorted[sorted.len() - 1],
        p50: sorted[(0.50 * n) as usize],
        p95: sorted[(0.95 * n) as usize],
        p99: sorted[(0.99 * n) as usize],
    }
}

fn generate_test_input() -> Array4<f32> {
    let mut rng = rand::thread_rng();
    Array4::from_shape_fn((1, 3, HEIGHT, WIDTH), |_| rng.gen::<f32>())
}

fn preprocess_image() -> Array4<f32> {
    // Simulate preprocessing a 640x480 BGR image to 640x640 float tensor
    let mut rng = rand::thread_rng();
    
    // Create raw image (simulating BGR 640x480)
    let raw_image: Vec<u8> = (0..640 * 480 * 3).map(|_| rng.gen::<u8>()).collect();
    
    // Resize to 640x640 and convert to float32 CHW format
    let mut output = Array4::zeros((1, 3, HEIGHT, WIDTH));
    
    let scale_x = 640.0 / WIDTH as f32;
    let scale_y = 480.0 / HEIGHT as f32;
    
    for y in 0..HEIGHT {
        for x in 0..WIDTH {
            let src_x = (x as f32 * scale_x).min(639.0) as usize;
            let src_y = (y as f32 * scale_y).min(479.0) as usize;
            let src_idx = (src_y * 640 + src_x) * 3;
            
            // BGR -> RGB and normalize
            output[[0, 0, y, x]] = raw_image[src_idx + 2] as f32 / 255.0; // R
            output[[0, 1, y, x]] = raw_image[src_idx + 1] as f32 / 255.0; // G
            output[[0, 2, y, x]] = raw_image[src_idx + 0] as f32 / 255.0; // B
        }
    }
    
    output
}

fn main() -> Result<()> {
    eprintln!("======================================================================");
    eprintln!("🦀 BENCHMARK ONNX INFERENCE - Rust");
    eprintln!("======================================================================");
    
    let model_path = env::var("MODEL_PATH")
        .unwrap_or_else(|_| "./models/yolov8n.onnx".to_string());
    
    // Check model exists
    let metadata = std::fs::metadata(&model_path)?;
    let model_size_mb = metadata.len() as f64 / 1024.0 / 1024.0;
    
    eprintln!("📦 Model: {} ({:.1} MB)", model_path, model_size_mb);
    
    // Load model
    eprintln!("⏳ Loading model...");
    let load_start = Instant::now();
    
    let mut session = Session::builder()?
        .with_optimization_level(GraphOptimizationLevel::Level3)?
        .with_intra_threads(4)?
        .commit_from_file(&model_path)?;
    
    let load_time = load_start.elapsed().as_secs_f64();
    eprintln!("✅ Model loaded in {:.3}s", load_time);
    
    // Print input/output info
    for (i, input) in session.inputs.iter().enumerate() {
        eprintln!("   Input {}: {}", i, input.name);
    }
    for (i, output) in session.outputs.iter().enumerate() {
        eprintln!("   Output {}: {}", i, output.name);
    }
    
    // Warmup
    eprintln!("⏳ Warmup ({} iterations)...", WARMUP);
    for _ in 0..WARMUP {
        let input_data = generate_test_input();
        let shape = input_data.shape().to_vec();
        let data_vec: Vec<f32> = input_data.into_raw_vec();
        let input_tensor = Tensor::from_array((shape, data_vec.into_boxed_slice()))?;
        let _ = session.run(ort::inputs!["images" => input_tensor])?;
    }
    
    // Benchmark pure inference
    eprintln!("⏱️ Benchmark inference ({} iterations)...", ITERATIONS);
    let mut inference_times = Vec::with_capacity(ITERATIONS);
    
    for _ in 0..ITERATIONS {
        let input_data = generate_test_input();
        let shape = input_data.shape().to_vec();
        let data_vec: Vec<f32> = input_data.into_raw_vec();
        let input_tensor = Tensor::from_array((shape, data_vec.into_boxed_slice()))?;
        
        let start = Instant::now();
        let _ = session.run(ort::inputs!["images" => input_tensor])?;
        inference_times.push(start.elapsed().as_secs_f64() * 1000.0); // ms
    }
    
    // Benchmark with preprocessing
    eprintln!("⏱️ Benchmark full pipeline ({} iterations)...", ITERATIONS);
    let mut pipeline_times = Vec::with_capacity(ITERATIONS);
    
    for _ in 0..ITERATIONS {
        let start = Instant::now();
        
        // Preprocess (simulates image loading + resize + normalization)
        let input_data = preprocess_image();
        
        let shape = input_data.shape().to_vec();
        let data_vec: Vec<f32> = input_data.into_raw_vec();
        let input_tensor = Tensor::from_array((shape, data_vec.into_boxed_slice()))?;
        
        let _ = session.run(ort::inputs!["images" => input_tensor])?;
        pipeline_times.push(start.elapsed().as_secs_f64() * 1000.0); // ms
    }
    
    // Calculate stats
    let inference_stats = calc_stats(&inference_times);
    let pipeline_stats = calc_stats(&pipeline_times);
    
    let result = BenchmarkResult {
        language: "Rust".to_string(),
        runtime: "ort".to_string(),
        model: "yolov8n".to_string(),
        model_size_mb,
        load_time_s: load_time,
        input_shape: vec![1, 3, HEIGHT, WIDTH],
        iterations: ITERATIONS,
        inference_fps: 1000.0 / inference_stats.mean,
        inference_ms: inference_stats,
        pipeline_fps: 1000.0 / pipeline_stats.mean,
        pipeline_ms: pipeline_stats,
    };
    
    eprintln!("✅ Inference: {:.2}ms ({:.1} FPS)", result.inference_ms.mean, result.inference_fps);
    eprintln!("✅ Pipeline:  {:.2}ms ({:.1} FPS)", result.pipeline_ms.mean, result.pipeline_fps);
    eprintln!("======================================================================");
    
    // Output JSON
    println!("{}", serde_json::to_string_pretty(&result)?);
    
    Ok(())
}
