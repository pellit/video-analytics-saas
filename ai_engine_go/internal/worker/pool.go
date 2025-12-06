package worker

import (
	"context"
	"encoding/json"
	"fmt"
	"image"
	"image/draw"
	"io"
	"log"
	"sync"
	"sync/atomic"
	"time"

	"github.com/go-redis/redis/v8"
	"github.com/pellit/video-analytics-saas/ai_engine_go/internal/detector"
	"github.com/pellit/video-analytics-saas/ai_engine_go/internal/stream"
)

// Task represents a camera processing task
type Task struct {
	CameraID   string
	RTSPURL    string
	ModelID    string
	Threshold  float32
	Camera     *stream.Camera
	Cancel     context.CancelFunc
	
	mu         sync.RWMutex
	running    bool
	lastFrame  []byte
	detections []detector.Detection
	stats      TaskStats
}

// TaskStats holds task performance statistics
type TaskStats struct {
	FramesProcessed uint64
	DetectionsTotal uint64
	AverageFPS      float64
	InferenceTimeMs float64
	LastUpdate      time.Time
}

// Pool manages worker goroutines
type Pool struct {
	numWorkers    int
	detector      *detector.ONNXDetector
	streamManager *stream.Manager
	redis         *redis.Client
	
	tasks        map[string]*Task
	tasksMu      sync.RWMutex
	activeTasks  int32
	
	workChan     chan *Task
}

// NewPool creates a new worker pool
func NewPool(numWorkers int, det *detector.ONNXDetector, sm *stream.Manager, rdb *redis.Client) *Pool {
	return &Pool{
		numWorkers:    numWorkers,
		detector:      det,
		streamManager: sm,
		redis:         rdb,
		tasks:         make(map[string]*Task),
		workChan:      make(chan *Task, 100),
	}
}

// Start starts the worker pool
func (p *Pool) Start(ctx context.Context) {
	for i := 0; i < p.numWorkers; i++ {
		go p.worker(ctx, i)
	}
}

// worker is a goroutine that processes tasks
func (p *Pool) worker(ctx context.Context, id int) {
	log.Printf("👷 Worker %d started", id)
	
	for {
		select {
		case <-ctx.Done():
			log.Printf("👷 Worker %d stopped", id)
			return
		case task := <-p.workChan:
			p.processTask(ctx, task)
		}
	}
}

// processTask processes frames from a camera
func (p *Pool) processTask(ctx context.Context, task *Task) {
	atomic.AddInt32(&p.activeTasks, 1)
	defer atomic.AddInt32(&p.activeTasks, -1)
	
	log.Printf("🎥 Processing camera %s", task.CameraID)
	
	taskCtx, cancel := context.WithCancel(ctx)
	task.Cancel = cancel
	task.running = true
	
	defer func() {
		task.running = false
		cancel()
	}()
	
	// Start camera stream
	camera, err := p.streamManager.StartCamera(
		task.CameraID,
		task.RTSPURL,
		640, 480, 15,
	)
	if err != nil {
		log.Printf("❌ Failed to start camera %s: %v", task.CameraID, err)
		return
	}
	task.Camera = camera
	
	frameCount := uint64(0)
	startTime := time.Now()
	
	for {
		select {
		case <-taskCtx.Done():
			return
		default:
		}
		
		// Get frame
		frame, err := camera.GetFrame(taskCtx)
		if err != nil {
			if taskCtx.Err() != nil {
				return
			}
			log.Printf("⚠️ Camera %s: frame error: %v", task.CameraID, err)
			time.Sleep(100 * time.Millisecond)
			continue
		}
		
		// Run detection
		inferenceStart := time.Now()
		detections, err := p.detector.Detect(frame.Image)
		inferenceTime := time.Since(inferenceStart)
		
		if err != nil {
			log.Printf("⚠️ Detection error: %v", err)
			continue
		}
		
		// Get frame dimensions for normalization
		bounds := frame.Image.Bounds()
		frameW := float64(bounds.Dx())
		frameH := float64(bounds.Dy())
		
		// Encode CLEAN frame to JPEG (no boxes - frontend draws them via canvas)
		rgba := toRGBA(frame.Image)
		jpegData, err := stream.EncodeJPEG(rgba, 85)
		if err != nil {
			continue
		}
		
		// Update task
		task.mu.Lock()
		task.lastFrame = jpegData
		task.detections = detections
		task.stats.FramesProcessed++
		task.stats.DetectionsTotal += uint64(len(detections))
		task.stats.InferenceTimeMs = float64(inferenceTime.Milliseconds())
		task.stats.LastUpdate = time.Now()
		
		frameCount++
		elapsed := time.Since(startTime).Seconds()
		if elapsed > 0 {
			task.stats.AverageFPS = float64(frameCount) / elapsed
		}
		task.mu.Unlock()
		
		// Publish detections to Redis (normalized for canvas overlay)
		if len(detections) > 0 {
			p.publishDetections(taskCtx, task.CameraID, detections, frameW, frameH)
		}
	}
}

// toRGBA converts any image to RGBA
func toRGBA(img image.Image) *image.RGBA {
	if rgba, ok := img.(*image.RGBA); ok {
		return rgba
	}
	
	bounds := img.Bounds()
	rgba := image.NewRGBA(bounds)
	draw.Draw(rgba, bounds, img, bounds.Min, draw.Src)
	return rgba
}

// publishDetections publishes normalized detections to Redis for canvas overlay
func (p *Pool) publishDetections(ctx context.Context, cameraID string, detections []detector.Detection, frameW, frameH float64) {
	// Normalize detections for canvas overlay (same format as Python worker)
	normalizedDetections := make([]map[string]interface{}, 0, len(detections))
	for _, det := range detections {
		x1, y1, x2, y2 := float64(det.BBox[0]), float64(det.BBox[1]), float64(det.BBox[2]), float64(det.BBox[3])
		normalizedDetections = append(normalizedDetections, map[string]interface{}{
			"class":      det.ClassName,
			"confidence": det.Confidence,
			"bbox": map[string]float64{
				"x": x1 / frameW,
				"y": y1 / frameH,
				"w": (x2 - x1) / frameW,
				"h": (y2 - y1) / frameH,
			},
			"track_id": nil, // Go worker doesn't support tracking yet
		})
	}
	
	// Canvas overlay event (same format as Python worker)
	canvasEvent := map[string]interface{}{
		"camera_id":  cameraID,
		"event":      "detections",
		"timestamp":  time.Now().UTC().Unix(),
		"detections": normalizedDetections,
		"frame_size": map[string]int{
			"w": int(frameW),
			"h": int(frameH),
		},
	}
	
	jsonData, err := json.Marshal(canvasEvent)
	if err != nil {
		return
	}
	
	// Publish to same channel as Python worker
	p.redis.Publish(ctx, "camera_detections", string(jsonData))
	
	// Also publish individual detections for alerts (legacy format)
	for _, det := range detections {
		data := map[string]interface{}{
			"camera_id": cameraID,
			"event":     det.ClassName,
			"payload": map[string]interface{}{
				"label": det.ClassName,
				"score": det.Confidence,
				"bbox":  det.BBox,
			},
		}
		jsonData, _ := json.Marshal(data)
		p.redis.Publish(ctx, "detections", string(jsonData))
	}
}

// StartCamera starts processing for a camera
func (p *Pool) StartCamera(cameraID, rtspURL, modelID string, threshold float32) error {
	p.tasksMu.Lock()
	defer p.tasksMu.Unlock()
	
	// Stop existing task
	if task, exists := p.tasks[cameraID]; exists {
		if task.Cancel != nil {
			task.Cancel()
		}
	}
	
	task := &Task{
		CameraID:  cameraID,
		RTSPURL:   rtspURL,
		ModelID:   modelID,
		Threshold: threshold,
	}
	
	p.tasks[cameraID] = task
	
	// Queue task for processing
	select {
	case p.workChan <- task:
		return nil
	default:
		return fmt.Errorf("worker queue full")
	}
}

// StopCamera stops processing for a camera
func (p *Pool) StopCamera(cameraID string) {
	p.tasksMu.Lock()
	defer p.tasksMu.Unlock()
	
	if task, exists := p.tasks[cameraID]; exists {
		if task.Cancel != nil {
			task.Cancel()
		}
		if task.Camera != nil {
			p.streamManager.StopCamera(cameraID)
		}
		delete(p.tasks, cameraID)
	}
}

// UpdateCameraModel updates the model for a camera
func (p *Pool) UpdateCameraModel(cameraID, modelID string, threshold float32) {
	p.tasksMu.Lock()
	defer p.tasksMu.Unlock()
	
	if task, exists := p.tasks[cameraID]; exists {
		task.mu.Lock()
		task.ModelID = modelID
		task.Threshold = threshold
		task.mu.Unlock()
	}
}

// GetCameraStats returns stats for a camera
func (p *Pool) GetCameraStats(cameraID string) map[string]interface{} {
	p.tasksMu.RLock()
	defer p.tasksMu.RUnlock()
	
	task, exists := p.tasks[cameraID]
	if !exists {
		return map[string]interface{}{
			"status": "not_found",
		}
	}
	
	task.mu.RLock()
	defer task.mu.RUnlock()
	
	return map[string]interface{}{
		"camera_id":        cameraID,
		"running":          task.running,
		"model_id":         task.ModelID,
		"frames_processed": task.stats.FramesProcessed,
		"detections_total": task.stats.DetectionsTotal,
		"average_fps":      task.stats.AverageFPS,
		"inference_time_ms": task.stats.InferenceTimeMs,
		"last_update":      task.stats.LastUpdate.Format(time.RFC3339),
	}
}

// ActiveTasks returns the number of active tasks
func (p *Pool) ActiveTasks() int {
	return int(atomic.LoadInt32(&p.activeTasks))
}

// StreamVideo streams video to a writer (for MJPEG streaming)
func (p *Pool) StreamVideo(ctx context.Context, cameraID string, w io.Writer) error {
	p.tasksMu.RLock()
	task, exists := p.tasks[cameraID]
	p.tasksMu.RUnlock()
	
	if !exists {
		return fmt.Errorf("camera not found")
	}
	
	boundary := "frame"
	
	// Create a flusher if available
	type flusher interface {
		Flush() error
	}
	
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}
		
		task.mu.RLock()
		frameData := task.lastFrame
		task.mu.RUnlock()
		
		if len(frameData) == 0 {
			time.Sleep(50 * time.Millisecond)
			continue
		}
		
		// Write MJPEG frame
		header := fmt.Sprintf("--%s\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n", boundary, len(frameData))
		if _, err := w.Write([]byte(header)); err != nil {
			return err
		}
		if _, err := w.Write(frameData); err != nil {
			return err
		}
		if _, err := w.Write([]byte("\r\n")); err != nil {
			return err
		}
		
		// Flush if possible
		if f, ok := w.(flusher); ok {
			f.Flush()
		}
		
		// Target ~15 FPS
		time.Sleep(66 * time.Millisecond)
	}
}
