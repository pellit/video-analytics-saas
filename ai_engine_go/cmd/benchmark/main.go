package main

import (
	"encoding/json"
	"fmt"
	"image"
	"math/rand"
	"os"
	"time"

	ort "github.com/yalue/onnxruntime_go"
)

const (
	ITERATIONS = 100
	WARMUP     = 10
	WIDTH      = 640
	HEIGHT     = 640
)

type Stats struct {
	Mean float64 `json:"mean"`
	Std  float64 `json:"std"`
	Min  float64 `json:"min"`
	Max  float64 `json:"max"`
	P50  float64 `json:"p50"`
	P95  float64 `json:"p95"`
	P99  float64 `json:"p99"`
}

type BenchmarkResult struct {
	Language     string  `json:"language"`
	Runtime      string  `json:"runtime"`
	Model        string  `json:"model"`
	ModelSizeMB  float64 `json:"model_size_mb"`
	LoadTimeS    float64 `json:"load_time_s"`
	InputShape   []int   `json:"input_shape"`
	Iterations   int     `json:"iterations"`
	InferenceMS  Stats   `json:"inference_ms"`
	InferenceFPS float64 `json:"inference_fps"`
	PipelineMS   Stats   `json:"pipeline_ms"`
	PipelineFPS  float64 `json:"pipeline_fps"`
}

func calcStats(times []float64) Stats {
	n := float64(len(times))
	if n == 0 {
		return Stats{}
	}

	// Sort for percentiles
	sorted := make([]float64, len(times))
	copy(sorted, times)
	for i := range sorted {
		for j := i + 1; j < len(sorted); j++ {
			if sorted[i] > sorted[j] {
				sorted[i], sorted[j] = sorted[j], sorted[i]
			}
		}
	}

	// Calculate mean
	var sum float64
	for _, t := range times {
		sum += t
	}
	mean := sum / n

	// Calculate std
	var variance float64
	for _, t := range times {
		diff := t - mean
		variance += diff * diff
	}
	std := 0.0
	if n > 1 {
		std = variance / (n - 1)
		if std > 0 {
			std = std
		}
	}

	// Min/Max
	min := sorted[0]
	max := sorted[len(sorted)-1]

	// Percentiles
	p50 := sorted[int(0.50*n)]
	p95 := sorted[int(0.95*n)]
	p99 := sorted[int(0.99*n)]

	return Stats{
		Mean: mean,
		Std:  std,
		Min:  min,
		Max:  max,
		P50:  p50,
		P95:  p95,
		P99:  p99,
	}
}

func generateTestImage() []float32 {
	data := make([]float32, 1*3*HEIGHT*WIDTH)
	for i := range data {
		data[i] = rand.Float32()
	}
	return data
}

func preprocess(img image.Image) []float32 {
	bounds := img.Bounds()
	w, h := bounds.Dx(), bounds.Dy()

	// Scale factors
	scaleX := float64(w) / float64(WIDTH)
	scaleY := float64(h) / float64(HEIGHT)

	// Output in CHW format
	data := make([]float32, 3*HEIGHT*WIDTH)

	for y := 0; y < HEIGHT; y++ {
		for x := 0; x < WIDTH; x++ {
			srcX := int(float64(x) * scaleX)
			srcY := int(float64(y) * scaleY)
			if srcX >= w {
				srcX = w - 1
			}
			if srcY >= h {
				srcY = h - 1
			}

			r, g, b, _ := img.At(srcX+bounds.Min.X, srcY+bounds.Min.Y).RGBA()
			idx := y*WIDTH + x
			data[idx] = float32(r>>8) / 255.0                // R channel
			data[HEIGHT*WIDTH+idx] = float32(g>>8) / 255.0   // G channel
			data[2*HEIGHT*WIDTH+idx] = float32(b>>8) / 255.0 // B channel
		}
	}

	return data
}

func main() {
	fmt.Fprintln(os.Stderr, "======================================================================")
	fmt.Fprintln(os.Stderr, "🐹 BENCHMARK ONNX INFERENCE - Go")
	fmt.Fprintln(os.Stderr, "======================================================================")

	modelPath := os.Getenv("MODEL_PATH")
	if modelPath == "" {
		modelPath = "/app/models/yolov8n.onnx"
	}

	// Check if model exists
	fileInfo, err := os.Stat(modelPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "❌ Model not found: %s\n", modelPath)
		os.Exit(1)
	}
	modelSizeMB := float64(fileInfo.Size()) / 1024 / 1024

	fmt.Fprintf(os.Stderr, "📦 Model: %s (%.1f MB)\n", modelPath, modelSizeMB)

	// Initialize ONNX Runtime
	if err := ort.InitializeEnvironment(); err != nil {
		fmt.Fprintf(os.Stderr, "❌ Failed to initialize ONNX Runtime: %v\n", err)
		os.Exit(1)
	}
	defer ort.DestroyEnvironment()

	// Create tensors
	inputShape := ort.NewShape(1, 3, HEIGHT, WIDTH)
	inputTensor, err := ort.NewEmptyTensor[float32](inputShape)
	if err != nil {
		fmt.Fprintf(os.Stderr, "❌ Failed to create input tensor: %v\n", err)
		os.Exit(1)
	}
	defer inputTensor.Destroy()

	outputShape := ort.NewShape(1, 84, 8400) // YOLOv8 output
	outputTensor, err := ort.NewEmptyTensor[float32](outputShape)
	if err != nil {
		fmt.Fprintf(os.Stderr, "❌ Failed to create output tensor: %v\n", err)
		os.Exit(1)
	}
	defer outputTensor.Destroy()

	// Load model and measure time
	fmt.Fprintln(os.Stderr, "⏳ Loading model...")
	loadStart := time.Now()

	session, err := ort.NewAdvancedSession(
		modelPath,
		[]string{"images"},
		[]string{"output0"},
		[]ort.ArbitraryTensor{inputTensor},
		[]ort.ArbitraryTensor{outputTensor},
		nil,
	)
	if err != nil {
		fmt.Fprintf(os.Stderr, "❌ Failed to create session: %v\n", err)
		os.Exit(1)
	}
	defer session.Destroy()

	loadTime := time.Since(loadStart).Seconds()
	fmt.Fprintf(os.Stderr, "✅ Model loaded in %.3fs\n", loadTime)

	// Generate test data
	testData := generateTestImage()

	// Warmup
	fmt.Fprintf(os.Stderr, "⏳ Warmup (%d iterations)...\n", WARMUP)
	for i := 0; i < WARMUP; i++ {
		inputSlice := inputTensor.GetData()
		copy(inputSlice, testData)
		if err := session.Run(); err != nil {
			fmt.Fprintf(os.Stderr, "❌ Inference failed: %v\n", err)
			os.Exit(1)
		}
	}

	// Benchmark pure inference
	fmt.Fprintf(os.Stderr, "⏱️ Benchmark inference (%d iterations)...\n", ITERATIONS)
	inferenceTimes := make([]float64, ITERATIONS)
	for i := 0; i < ITERATIONS; i++ {
		inputSlice := inputTensor.GetData()
		copy(inputSlice, testData)

		start := time.Now()
		if err := session.Run(); err != nil {
			fmt.Fprintf(os.Stderr, "❌ Inference failed: %v\n", err)
			os.Exit(1)
		}
		inferenceTimes[i] = float64(time.Since(start).Microseconds()) / 1000.0 // ms
	}

	// Benchmark with preprocessing (simulate raw image)
	fmt.Fprintf(os.Stderr, "⏱️ Benchmark full pipeline (%d iterations)...\n", ITERATIONS)

	// Create a test image (RGBA)
	testImg := image.NewRGBA(image.Rect(0, 0, 640, 480))
	// Fill with random values
	for i := range testImg.Pix {
		testImg.Pix[i] = uint8(rand.Intn(256))
	}

	pipelineTimes := make([]float64, ITERATIONS)
	for i := 0; i < ITERATIONS; i++ {
		start := time.Now()

		// Preprocess
		preprocessed := preprocess(testImg)

		// Copy to tensor
		inputSlice := inputTensor.GetData()
		copy(inputSlice, preprocessed)

		// Run inference
		if err := session.Run(); err != nil {
			fmt.Fprintf(os.Stderr, "❌ Inference failed: %v\n", err)
			os.Exit(1)
		}
		pipelineTimes[i] = float64(time.Since(start).Microseconds()) / 1000.0 // ms
	}

	// Calculate stats
	inferenceStats := calcStats(inferenceTimes)
	pipelineStats := calcStats(pipelineTimes)

	result := BenchmarkResult{
		Language:     "Go",
		Runtime:      "onnxruntime_go",
		Model:        "yolov8n",
		ModelSizeMB:  modelSizeMB,
		LoadTimeS:    loadTime,
		InputShape:   []int{1, 3, HEIGHT, WIDTH},
		Iterations:   ITERATIONS,
		InferenceMS:  inferenceStats,
		InferenceFPS: 1000.0 / inferenceStats.Mean,
		PipelineMS:   pipelineStats,
		PipelineFPS:  1000.0 / pipelineStats.Mean,
	}

	fmt.Fprintf(os.Stderr, "✅ Inference: %.2fms (%.1f FPS)\n", inferenceStats.Mean, result.InferenceFPS)
	fmt.Fprintf(os.Stderr, "✅ Pipeline:  %.2fms (%.1f FPS)\n", pipelineStats.Mean, result.PipelineFPS)
	fmt.Fprintln(os.Stderr, "======================================================================")

	// Output JSON
	jsonOutput, _ := json.MarshalIndent(result, "", "  ")
	fmt.Println(string(jsonOutput))
}
