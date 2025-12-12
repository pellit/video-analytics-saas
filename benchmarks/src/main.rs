use std::time::Instant;
use serde::{Deserialize, Serialize};
use rand::Rng;

const ITERATIONS: usize = 100;
const WARMUP: usize = 10;
const IMAGE_W: usize = 1920;
const IMAGE_H: usize = 1080;
const TARGET_W: usize = 640;
const TARGET_H: usize = 640;

#[derive(Serialize, Deserialize)]
struct Stats {
    mean: f64,
    std: f64,
    min: f64,
    max: f64,
}

#[derive(Serialize, Deserialize)]
struct CodecStats {
    encode_ms: Stats,
    decode_ms: Stats,
}

#[derive(Serialize, Deserialize)]
struct Results {
    language: String,
    iterations: usize,
    image_size: Vec<usize>,
    target_size: Vec<usize>,
    benchmarks: std::collections::HashMap<String, serde_json::Value>,
}

fn calc_stats(times: &[f64]) -> Stats {
    let n = times.len() as f64;
    let mean = times.iter().sum::<f64>() / n;
    let variance = times.iter().map(|t| (t - mean).powi(2)).sum::<f64>() / n;
    let std = variance.sqrt();
    let min = times.iter().cloned().fold(f64::INFINITY, f64::min);
    let max = times.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    
    Stats { mean, std, min, max }
}

fn generate_test_image() -> Vec<u8> {
    let mut rng = rand::thread_rng();
    (0..IMAGE_W * IMAGE_H * 3)
        .map(|_| rng.gen::<u8>())
        .collect()
}

fn benchmark_jpeg_codec() -> CodecStats {
    let img = generate_test_image();
    
    // Create image buffer for encoding
    let img_buffer: image::RgbImage = image::ImageBuffer::from_raw(
        IMAGE_W as u32, 
        IMAGE_H as u32, 
        img.clone()
    ).unwrap();
    
    // Warmup
    for _ in 0..WARMUP {
        let mut encoded = Vec::new();
        let mut encoder = image::codecs::jpeg::JpegEncoder::new_with_quality(&mut encoded, 85);
        encoder.encode(&img_buffer, IMAGE_W as u32, IMAGE_H as u32, image::ExtendedColorType::Rgb8).ok();
        let _ = image::load_from_memory_with_format(&encoded, image::ImageFormat::Jpeg);
    }
    
    // Benchmark encode
    let mut encode_times = Vec::with_capacity(ITERATIONS);
    for _ in 0..ITERATIONS {
        let mut encoded = Vec::new();
        let start = Instant::now();
        let mut encoder = image::codecs::jpeg::JpegEncoder::new_with_quality(&mut encoded, 85);
        encoder.encode(&img_buffer, IMAGE_W as u32, IMAGE_H as u32, image::ExtendedColorType::Rgb8).ok();
        encode_times.push(start.elapsed().as_secs_f64() * 1000.0);
    }
    
    // Encode once for decode benchmark
    let mut encoded = Vec::new();
    let mut encoder = image::codecs::jpeg::JpegEncoder::new_with_quality(&mut encoded, 85);
    encoder.encode(&img_buffer, IMAGE_W as u32, IMAGE_H as u32, image::ExtendedColorType::Rgb8).ok();
    
    // Benchmark decode
    let mut decode_times = Vec::with_capacity(ITERATIONS);
    for _ in 0..ITERATIONS {
        let start = Instant::now();
        let _ = image::load_from_memory_with_format(&encoded, image::ImageFormat::Jpeg);
        decode_times.push(start.elapsed().as_secs_f64() * 1000.0);
    }
    
    CodecStats {
        encode_ms: calc_stats(&encode_times),
        decode_ms: calc_stats(&decode_times),
    }
}

fn benchmark_resize() -> Stats {
    let img = generate_test_image();
    let img_buffer: image::RgbImage = image::ImageBuffer::from_raw(
        IMAGE_W as u32, 
        IMAGE_H as u32, 
        img
    ).unwrap();
    let dyn_img = image::DynamicImage::ImageRgb8(img_buffer);
    
    // Warmup
    for _ in 0..WARMUP {
        let _ = dyn_img.resize_exact(TARGET_W as u32, TARGET_H as u32, image::imageops::FilterType::Triangle);
    }
    
    let mut times = Vec::with_capacity(ITERATIONS);
    for _ in 0..ITERATIONS {
        let start = Instant::now();
        let _ = dyn_img.resize_exact(TARGET_W as u32, TARGET_H as u32, image::imageops::FilterType::Triangle);
        times.push(start.elapsed().as_secs_f64() * 1000.0);
    }
    
    calc_stats(&times)
}

fn benchmark_color_conversion() -> Stats {
    let img = generate_test_image();
    
    // BGR to RGB swap
    let convert = |data: &[u8]| -> Vec<u8> {
        data.chunks(3)
            .flat_map(|chunk| [chunk[2], chunk[1], chunk[0]])
            .collect()
    };
    
    // Warmup
    for _ in 0..WARMUP {
        let _ = convert(&img);
    }
    
    let mut times = Vec::with_capacity(ITERATIONS);
    for _ in 0..ITERATIONS {
        let start = Instant::now();
        let _ = convert(&img);
        times.push(start.elapsed().as_secs_f64() * 1000.0);
    }
    
    calc_stats(&times)
}

fn benchmark_preprocessing() -> Stats {
    let img = generate_test_image();
    let img_buffer: image::RgbImage = image::ImageBuffer::from_raw(
        IMAGE_W as u32, 
        IMAGE_H as u32, 
        img
    ).unwrap();
    let dyn_img = image::DynamicImage::ImageRgb8(img_buffer);
    
    let preprocess = |img: &image::DynamicImage| -> Vec<f32> {
        // Resize
        let resized = img.resize_exact(TARGET_W as u32, TARGET_H as u32, image::imageops::FilterType::Triangle);
        let rgb = resized.to_rgb8();
        
        // Normalize to float32 [0,1] in CHW format
        let mut result = vec![0.0f32; 3 * TARGET_W * TARGET_H];
        for (i, pixel) in rgb.pixels().enumerate() {
            result[i] = pixel[0] as f32 / 255.0;  // R channel
            result[TARGET_W * TARGET_H + i] = pixel[1] as f32 / 255.0;  // G channel
            result[2 * TARGET_W * TARGET_H + i] = pixel[2] as f32 / 255.0;  // B channel
        }
        result
    };
    
    // Warmup
    for _ in 0..WARMUP {
        let _ = preprocess(&dyn_img);
    }
    
    let mut times = Vec::with_capacity(ITERATIONS);
    for _ in 0..ITERATIONS {
        let start = Instant::now();
        let _ = preprocess(&dyn_img);
        times.push(start.elapsed().as_secs_f64() * 1000.0);
    }
    
    calc_stats(&times)
}

fn benchmark_nms() -> Stats {
    let mut rng = rand::thread_rng();
    let num_boxes = 1000;
    
    let boxes: Vec<[f32; 4]> = (0..num_boxes)
        .map(|_| [
            rng.gen::<f32>() * 640.0,
            rng.gen::<f32>() * 640.0,
            rng.gen::<f32>() * 640.0,
            rng.gen::<f32>() * 640.0,
        ])
        .collect();
    
    let scores: Vec<f32> = (0..num_boxes).map(|_| rng.gen::<f32>()).collect();
    
    let nms = |boxes: &[[f32; 4]], scores: &[f32], threshold: f32| -> Vec<usize> {
        let mut indices: Vec<usize> = (0..scores.len()).collect();
        indices.sort_by(|&a, &b| scores[b].partial_cmp(&scores[a]).unwrap());
        
        let mut keep = Vec::new();
        let mut suppressed = vec![false; boxes.len()];
        
        for &idx in &indices {
            if suppressed[idx] {
                continue;
            }
            keep.push(idx);
            
            for &other_idx in &indices {
                if suppressed[other_idx] || other_idx == idx {
                    continue;
                }
                
                // Calculate IoU
                let x1 = boxes[idx][0].max(boxes[other_idx][0]);
                let y1 = boxes[idx][1].max(boxes[other_idx][1]);
                let x2 = boxes[idx][2].min(boxes[other_idx][2]);
                let y2 = boxes[idx][3].min(boxes[other_idx][3]);
                
                if x2 > x1 && y2 > y1 {
                    let intersection = (x2 - x1) * (y2 - y1);
                    let area1 = (boxes[idx][2] - boxes[idx][0]) * (boxes[idx][3] - boxes[idx][1]);
                    let area2 = (boxes[other_idx][2] - boxes[other_idx][0]) * (boxes[other_idx][3] - boxes[other_idx][1]);
                    let iou = intersection / (area1 + area2 - intersection);
                    
                    if iou > threshold {
                        suppressed[other_idx] = true;
                    }
                }
            }
        }
        keep
    };
    
    // Warmup
    for _ in 0..WARMUP {
        let _ = nms(&boxes, &scores, 0.45);
    }
    
    let mut times = Vec::with_capacity(ITERATIONS);
    for _ in 0..ITERATIONS {
        let start = Instant::now();
        let _ = nms(&boxes, &scores, 0.45);
        times.push(start.elapsed().as_secs_f64() * 1000.0);
    }
    
    calc_stats(&times)
}

fn benchmark_matrix_ops() -> Stats {
    let mut rng = rand::thread_rng();
    let size = 256;
    
    let a: Vec<Vec<f32>> = (0..size)
        .map(|_| (0..size).map(|_| rng.gen::<f32>()).collect())
        .collect();
    
    let b: Vec<Vec<f32>> = (0..size)
        .map(|_| (0..size).map(|_| rng.gen::<f32>()).collect())
        .collect();
    
    let matmul = |a: &[Vec<f32>], b: &[Vec<f32>]| -> Vec<Vec<f32>> {
        let n = a.len();
        let mut result = vec![vec![0.0f32; n]; n];
        for i in 0..n {
            for j in 0..n {
                for k in 0..n {
                    result[i][j] += a[i][k] * b[k][j];
                }
            }
        }
        result
    };
    
    // Warmup (smaller matrix)
    let small_a: Vec<Vec<f32>> = (0..64).map(|_| (0..64).map(|_| rng.gen::<f32>()).collect()).collect();
    let small_b: Vec<Vec<f32>> = (0..64).map(|_| (0..64).map(|_| rng.gen::<f32>()).collect()).collect();
    for _ in 0..WARMUP {
        let _ = matmul(&small_a, &small_b);
    }
    
    let mut times = Vec::with_capacity(ITERATIONS);
    for _ in 0..ITERATIONS {
        let start = Instant::now();
        let _ = matmul(&a, &b);
        times.push(start.elapsed().as_secs_f64() * 1000.0);
    }
    
    calc_stats(&times)
}

fn benchmark_json_serialization() -> Stats {
    #[derive(Serialize)]
    struct Detection {
        class: String,
        confidence: f64,
        bbox: Vec<i32>,
        track_id: i32,
    }
    
    let detections: Vec<Detection> = (0..50)
        .map(|i| Detection {
            class: "person".to_string(),
            confidence: 0.95,
            bbox: vec![100, 200, 300, 400],
            track_id: i,
        })
        .collect();
    
    // Warmup
    for _ in 0..WARMUP {
        let _ = serde_json::to_string(&detections);
    }
    
    let mut times = Vec::with_capacity(ITERATIONS);
    for _ in 0..ITERATIONS {
        let start = Instant::now();
        let _ = serde_json::to_string(&detections);
        times.push(start.elapsed().as_secs_f64() * 1000.0);
    }
    
    calc_stats(&times)
}

fn main() {
    eprintln!("============================================================");
    eprintln!("BENCHMARK RUST - Video Analytics");
    eprintln!("Iterations: {}, Warmup: {}", ITERATIONS, WARMUP);
    eprintln!("Image size: [{}, {}] -> [{}, {}]", IMAGE_W, IMAGE_H, TARGET_W, TARGET_H);
    eprintln!("============================================================");
    
    let mut results = Results {
        language: "Rust".to_string(),
        iterations: ITERATIONS,
        image_size: vec![IMAGE_W, IMAGE_H],
        target_size: vec![TARGET_W, TARGET_H],
        benchmarks: std::collections::HashMap::new(),
    };
    
    eprintln!("\n[1/7] JPEG Encode/Decode...");
    results.benchmarks.insert("jpeg_codec".to_string(), serde_json::to_value(benchmark_jpeg_codec()).unwrap());
    
    eprintln!("[2/7] Resize...");
    results.benchmarks.insert("resize".to_string(), serde_json::to_value(benchmark_resize()).unwrap());
    
    eprintln!("[3/7] Color Conversion...");
    results.benchmarks.insert("color_conversion".to_string(), serde_json::to_value(benchmark_color_conversion()).unwrap());
    
    eprintln!("[4/7] Full Preprocessing Pipeline...");
    results.benchmarks.insert("preprocessing".to_string(), serde_json::to_value(benchmark_preprocessing()).unwrap());
    
    eprintln!("[5/7] NMS Simulation...");
    results.benchmarks.insert("nms".to_string(), serde_json::to_value(benchmark_nms()).unwrap());
    
    eprintln!("[6/7] Matrix Operations...");
    results.benchmarks.insert("matrix_ops".to_string(), serde_json::to_value(benchmark_matrix_ops()).unwrap());
    
    eprintln!("[7/7] JSON Serialization...");
    results.benchmarks.insert("json_serialization".to_string(), serde_json::to_value(benchmark_json_serialization()).unwrap());
    
    eprintln!("\n✅ Benchmark completado!");
    
    // Output JSON to stdout
    println!("{}", serde_json::to_string_pretty(&results).unwrap());
}
