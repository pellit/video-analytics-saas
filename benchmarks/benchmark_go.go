package main

import (
	"encoding/json"
	"fmt"
	"image"
	"image/color"
	"image/jpeg"
	"bytes"
	"math"
	"math/rand"
	"os"
	"sort"
	"time"
)

const (
	ITERATIONS  = 100
	WARMUP      = 10
	IMAGE_W     = 1920
	IMAGE_H     = 1080
	TARGET_W    = 640
	TARGET_H    = 640
)

type Stats struct {
	Mean float64 `json:"mean"`
	Std  float64 `json:"std"`
	Min  float64 `json:"min"`
	Max  float64 `json:"max"`
}

type CodecStats struct {
	EncodeMs Stats `json:"encode_ms"`
	DecodeMs Stats `json:"decode_ms"`
}

type Results struct {
	Language   string                 `json:"language"`
	Iterations int                    `json:"iterations"`
	ImageSize  []int                  `json:"image_size"`
	TargetSize []int                  `json:"target_size"`
	Benchmarks map[string]interface{} `json:"benchmarks"`
}

func generateTestImage() *image.RGBA {
	img := image.NewRGBA(image.Rect(0, 0, IMAGE_W, IMAGE_H))
	for y := 0; y < IMAGE_H; y++ {
		for x := 0; x < IMAGE_W; x++ {
			img.Set(x, y, color.RGBA{
				R: uint8(rand.Intn(256)),
				G: uint8(rand.Intn(256)),
				B: uint8(rand.Intn(256)),
				A: 255,
			})
		}
	}
	return img
}

func calcStats(times []float64) Stats {
	n := float64(len(times))
	
	// Mean
	sum := 0.0
	for _, t := range times {
		sum += t
	}
	mean := sum / n
	
	// Std
	sumSq := 0.0
	for _, t := range times {
		sumSq += (t - mean) * (t - mean)
	}
	std := math.Sqrt(sumSq / n)
	
	// Min/Max
	sorted := make([]float64, len(times))
	copy(sorted, times)
	sort.Float64s(sorted)
	
	return Stats{
		Mean: mean,
		Std:  std,
		Min:  sorted[0],
		Max:  sorted[len(sorted)-1],
	}
}

func benchmarkJPEGCodec() CodecStats {
	img := generateTestImage()
	
	// Warmup
	for i := 0; i < WARMUP; i++ {
		var buf bytes.Buffer
		jpeg.Encode(&buf, img, &jpeg.Options{Quality: 85})
		jpeg.Decode(&buf)
	}
	
	// Benchmark encode
	encodeTimes := make([]float64, ITERATIONS)
	for i := 0; i < ITERATIONS; i++ {
		var buf bytes.Buffer
		start := time.Now()
		jpeg.Encode(&buf, img, &jpeg.Options{Quality: 85})
		encodeTimes[i] = float64(time.Since(start).Microseconds()) / 1000.0
	}
	
	// Encode once for decode benchmark
	var encoded bytes.Buffer
	jpeg.Encode(&encoded, img, &jpeg.Options{Quality: 85})
	encodedBytes := encoded.Bytes()
	
	// Benchmark decode
	decodeTimes := make([]float64, ITERATIONS)
	for i := 0; i < ITERATIONS; i++ {
		reader := bytes.NewReader(encodedBytes)
		start := time.Now()
		jpeg.Decode(reader)
		decodeTimes[i] = float64(time.Since(start).Microseconds()) / 1000.0
	}
	
	return CodecStats{
		EncodeMs: calcStats(encodeTimes),
		DecodeMs: calcStats(decodeTimes),
	}
}

func benchmarkResize() Stats {
	img := generateTestImage()
	
	// Simple nearest-neighbor resize (Go stdlib doesn't have bilinear)
	resize := func(src *image.RGBA, newW, newH int) *image.RGBA {
		dst := image.NewRGBA(image.Rect(0, 0, newW, newH))
		srcBounds := src.Bounds()
		srcW := srcBounds.Dx()
		srcH := srcBounds.Dy()
		
		for y := 0; y < newH; y++ {
			for x := 0; x < newW; x++ {
				srcX := x * srcW / newW
				srcY := y * srcH / newH
				dst.Set(x, y, src.At(srcX, srcY))
			}
		}
		return dst
	}
	
	// Warmup
	for i := 0; i < WARMUP; i++ {
		resize(img, TARGET_W, TARGET_H)
	}
	
	times := make([]float64, ITERATIONS)
	for i := 0; i < ITERATIONS; i++ {
		start := time.Now()
		resize(img, TARGET_W, TARGET_H)
		times[i] = float64(time.Since(start).Microseconds()) / 1000.0
	}
	
	return calcStats(times)
}

func benchmarkColorConversion() Stats {
	img := generateTestImage()
	
	// BGR to RGB (swap R and B channels)
	convertBGRtoRGB := func(src *image.RGBA) *image.RGBA {
		bounds := src.Bounds()
		dst := image.NewRGBA(bounds)
		for y := bounds.Min.Y; y < bounds.Max.Y; y++ {
			for x := bounds.Min.X; x < bounds.Max.X; x++ {
				r, g, b, a := src.At(x, y).RGBA()
				dst.Set(x, y, color.RGBA{
					R: uint8(b >> 8),
					G: uint8(g >> 8),
					B: uint8(r >> 8),
					A: uint8(a >> 8),
				})
			}
		}
		return dst
	}
	
	// Warmup
	for i := 0; i < WARMUP; i++ {
		convertBGRtoRGB(img)
	}
	
	times := make([]float64, ITERATIONS)
	for i := 0; i < ITERATIONS; i++ {
		start := time.Now()
		convertBGRtoRGB(img)
		times[i] = float64(time.Since(start).Microseconds()) / 1000.0
	}
	
	return calcStats(times)
}

func benchmarkPreprocessing() Stats {
	img := generateTestImage()
	
	// Full preprocessing pipeline
	preprocess := func(src *image.RGBA) []float32 {
		// Resize
		dst := image.NewRGBA(image.Rect(0, 0, TARGET_W, TARGET_H))
		srcBounds := src.Bounds()
		srcW := srcBounds.Dx()
		srcH := srcBounds.Dy()
		
		for y := 0; y < TARGET_H; y++ {
			for x := 0; x < TARGET_W; x++ {
				srcX := x * srcW / TARGET_W
				srcY := y * srcH / TARGET_H
				dst.Set(x, y, src.At(srcX, srcY))
			}
		}
		
		// Normalize to float32 [0,1] in CHW format
		result := make([]float32, 3*TARGET_W*TARGET_H)
		for y := 0; y < TARGET_H; y++ {
			for x := 0; x < TARGET_W; x++ {
				r, g, b, _ := dst.At(x, y).RGBA()
				idx := y*TARGET_W + x
				result[idx] = float32(r>>8) / 255.0                    // R channel
				result[TARGET_W*TARGET_H+idx] = float32(g>>8) / 255.0  // G channel
				result[2*TARGET_W*TARGET_H+idx] = float32(b>>8) / 255.0 // B channel
			}
		}
		return result
	}
	
	// Warmup
	for i := 0; i < WARMUP; i++ {
		preprocess(img)
	}
	
	times := make([]float64, ITERATIONS)
	for i := 0; i < ITERATIONS; i++ {
		start := time.Now()
		preprocess(img)
		times[i] = float64(time.Since(start).Microseconds()) / 1000.0
	}
	
	return calcStats(times)
}

func benchmarkNMS() Stats {
	// Simulate 1000 detections
	numBoxes := 1000
	boxes := make([][4]float32, numBoxes)
	scores := make([]float32, numBoxes)
	
	for i := 0; i < numBoxes; i++ {
		boxes[i] = [4]float32{
			rand.Float32() * 640,
			rand.Float32() * 640,
			rand.Float32() * 640,
			rand.Float32() * 640,
		}
		scores[i] = rand.Float32()
	}
	
	// Simple NMS implementation
	nms := func(boxes [][4]float32, scores []float32, threshold float32) []int {
		indices := make([]int, len(scores))
		for i := range indices {
			indices[i] = i
		}
		
		// Sort by score descending
		sort.Slice(indices, func(i, j int) bool {
			return scores[indices[i]] > scores[indices[j]]
		})
		
		keep := []int{}
		suppressed := make([]bool, len(boxes))
		
		for _, idx := range indices {
			if suppressed[idx] {
				continue
			}
			keep = append(keep, idx)
			
			// Suppress overlapping boxes
			for _, otherIdx := range indices {
				if suppressed[otherIdx] || otherIdx == idx {
					continue
				}
				
				// Calculate IoU (simplified)
				x1 := math.Max(float64(boxes[idx][0]), float64(boxes[otherIdx][0]))
				y1 := math.Max(float64(boxes[idx][1]), float64(boxes[otherIdx][1]))
				x2 := math.Min(float64(boxes[idx][2]), float64(boxes[otherIdx][2]))
				y2 := math.Min(float64(boxes[idx][3]), float64(boxes[otherIdx][3]))
				
				if x2 > x1 && y2 > y1 {
					intersection := (x2 - x1) * (y2 - y1)
					area1 := float64((boxes[idx][2]-boxes[idx][0]) * (boxes[idx][3]-boxes[idx][1]))
					area2 := float64((boxes[otherIdx][2]-boxes[otherIdx][0]) * (boxes[otherIdx][3]-boxes[otherIdx][1]))
					iou := intersection / (area1 + area2 - intersection)
					
					if iou > float64(threshold) {
						suppressed[otherIdx] = true
					}
				}
			}
		}
		return keep
	}
	
	// Warmup
	for i := 0; i < WARMUP; i++ {
		nms(boxes, scores, 0.45)
	}
	
	times := make([]float64, ITERATIONS)
	for i := 0; i < ITERATIONS; i++ {
		start := time.Now()
		nms(boxes, scores, 0.45)
		times[i] = float64(time.Since(start).Microseconds()) / 1000.0
	}
	
	return calcStats(times)
}

func benchmarkMatrixOps() Stats {
	// Simulate feature map operation
	rows, cols := 256, 6400 // 256 x (80*80)
	matrix := make([][]float32, rows)
	weights := make([][]float32, rows)
	
	for i := 0; i < rows; i++ {
		matrix[i] = make([]float32, cols)
		weights[i] = make([]float32, rows)
		for j := 0; j < cols; j++ {
			matrix[i][j] = rand.Float32()
		}
		for j := 0; j < rows; j++ {
			weights[i][j] = rand.Float32()
		}
	}
	
	// Matrix multiplication
	matmul := func(a [][]float32, b [][]float32) [][]float32 {
		rowsA := len(a)
		colsB := len(b[0])
		colsA := len(a[0])
		
		result := make([][]float32, rowsA)
		for i := 0; i < rowsA; i++ {
			result[i] = make([]float32, colsB)
			for j := 0; j < colsB; j++ {
				for k := 0; k < colsA; k++ {
					result[i][j] += a[i][k] * b[k][j]
				}
			}
		}
		return result
	}
	
	// Warmup (smaller matrix for warmup)
	smallMatrix := make([][]float32, 64)
	for i := 0; i < 64; i++ {
		smallMatrix[i] = make([]float32, 64)
		for j := 0; j < 64; j++ {
			smallMatrix[i][j] = rand.Float32()
		}
	}
	for i := 0; i < WARMUP; i++ {
		matmul(smallMatrix, smallMatrix)
	}
	
	// Use smaller matrix for actual benchmark too (256x256 matmul)
	times := make([]float64, ITERATIONS)
	for i := 0; i < ITERATIONS; i++ {
		start := time.Now()
		matmul(weights, weights) // 256x256 * 256x256
		times[i] = float64(time.Since(start).Microseconds()) / 1000.0
	}
	
	return calcStats(times)
}

func benchmarkJSONSerialization() Stats {
	type Detection struct {
		Class      string  `json:"class"`
		Confidence float64 `json:"confidence"`
		Bbox       []int   `json:"bbox"`
		TrackID    int     `json:"track_id"`
	}
	
	detections := make([]Detection, 50)
	for i := 0; i < 50; i++ {
		detections[i] = Detection{
			Class:      "person",
			Confidence: 0.95,
			Bbox:       []int{100, 200, 300, 400},
			TrackID:    i,
		}
	}
	
	// Warmup
	for i := 0; i < WARMUP; i++ {
		json.Marshal(detections)
	}
	
	times := make([]float64, ITERATIONS)
	for i := 0; i < ITERATIONS; i++ {
		start := time.Now()
		json.Marshal(detections)
		times[i] = float64(time.Since(start).Microseconds()) / 1000.0
	}
	
	return calcStats(times)
}

func main() {
	rand.Seed(time.Now().UnixNano())
	
	fmt.Fprintln(os.Stderr, "============================================================")
	fmt.Fprintln(os.Stderr, "BENCHMARK GO - Video Analytics")
	fmt.Fprintf(os.Stderr, "Iterations: %d, Warmup: %d\n", ITERATIONS, WARMUP)
	fmt.Fprintf(os.Stderr, "Image size: [%d, %d] -> [%d, %d]\n", IMAGE_W, IMAGE_H, TARGET_W, TARGET_H)
	fmt.Fprintln(os.Stderr, "============================================================")
	
	results := Results{
		Language:   "Go",
		Iterations: ITERATIONS,
		ImageSize:  []int{IMAGE_W, IMAGE_H},
		TargetSize: []int{TARGET_W, TARGET_H},
		Benchmarks: make(map[string]interface{}),
	}
	
	fmt.Fprintln(os.Stderr, "\n[1/7] JPEG Encode/Decode...")
	results.Benchmarks["jpeg_codec"] = benchmarkJPEGCodec()
	
	fmt.Fprintln(os.Stderr, "[2/7] Resize...")
	results.Benchmarks["resize"] = benchmarkResize()
	
	fmt.Fprintln(os.Stderr, "[3/7] Color Conversion...")
	results.Benchmarks["color_conversion"] = benchmarkColorConversion()
	
	fmt.Fprintln(os.Stderr, "[4/7] Full Preprocessing Pipeline...")
	results.Benchmarks["preprocessing"] = benchmarkPreprocessing()
	
	fmt.Fprintln(os.Stderr, "[5/7] NMS Simulation...")
	results.Benchmarks["nms"] = benchmarkNMS()
	
	fmt.Fprintln(os.Stderr, "[6/7] Matrix Operations...")
	results.Benchmarks["matrix_ops"] = benchmarkMatrixOps()
	
	fmt.Fprintln(os.Stderr, "[7/7] JSON Serialization...")
	results.Benchmarks["json_serialization"] = benchmarkJSONSerialization()
	
	fmt.Fprintln(os.Stderr, "\n✅ Benchmark completado!")
	
	// Output JSON to stdout
	output, _ := json.MarshalIndent(results, "", "  ")
	fmt.Println(string(output))
}
