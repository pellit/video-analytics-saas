package stream

import (
	"bytes"
	"context"
	"fmt"
	"image"
	"image/jpeg"
	"io"
	"log"
	"os/exec"
	"sync"
	"time"
)

// Frame represents a video frame
type Frame struct {
	Image     image.Image
	Timestamp time.Time
	Width     int
	Height    int
}

// Camera represents a camera stream
type Camera struct {
	ID        string
	RTSPURL   string
	Width     int
	Height    int
	FPS       int
	
	mu        sync.RWMutex
	running   bool
	cancel    context.CancelFunc
	frames    chan *Frame
	lastFrame *Frame
	cmd       *exec.Cmd
	stats     CameraStats
}

// CameraStats holds camera performance statistics
type CameraStats struct {
	FramesProcessed uint64
	FramesDropped   uint64
	LastFrameTime   time.Time
	AverageFPS      float64
	ProcessingTimeMs float64
	StartTime       time.Time
}

// Manager manages multiple camera streams
type Manager struct {
	cameras map[string]*Camera
	mu      sync.RWMutex
}

// NewManager creates a new stream manager
func NewManager() *Manager {
	return &Manager{
		cameras: make(map[string]*Camera),
	}
}

// StartCamera starts streaming from a camera
func (m *Manager) StartCamera(id, rtspURL string, width, height, fps int) (*Camera, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	
	// Stop existing camera if running
	if cam, exists := m.cameras[id]; exists {
		cam.Stop()
	}
	
	ctx, cancel := context.WithCancel(context.Background())
	
	cam := &Camera{
		ID:      id,
		RTSPURL: rtspURL,
		Width:   width,
		Height:  height,
		FPS:     fps,
		running: true,
		cancel:  cancel,
		frames:  make(chan *Frame, 5),
		stats: CameraStats{
			StartTime: time.Now(),
		},
	}
	
	m.cameras[id] = cam
	
	go cam.capture(ctx)
	
	log.Printf("📹 Started camera %s: %s", id, rtspURL)
	return cam, nil
}

// StopCamera stops a camera stream
func (m *Manager) StopCamera(id string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	
	if cam, exists := m.cameras[id]; exists {
		cam.Stop()
		delete(m.cameras, id)
		log.Printf("🛑 Stopped camera %s", id)
	}
}

// GetCamera returns a camera by ID
func (m *Manager) GetCamera(id string) *Camera {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.cameras[id]
}

// GetAllCameras returns all cameras
func (m *Manager) GetAllCameras() []*Camera {
	m.mu.RLock()
	defer m.mu.RUnlock()
	
	cameras := make([]*Camera, 0, len(m.cameras))
	for _, cam := range m.cameras {
		cameras = append(cameras, cam)
	}
	return cameras
}

// Stop stops the camera stream
func (c *Camera) Stop() {
	c.mu.Lock()
	defer c.mu.Unlock()
	
	c.running = false
	if c.cancel != nil {
		c.cancel()
	}
	if c.cmd != nil && c.cmd.Process != nil {
		c.cmd.Process.Kill()
	}
	close(c.frames)
}

// IsRunning returns whether the camera is running
func (c *Camera) IsRunning() bool {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.running
}

// GetFrame returns the next frame from the camera
func (c *Camera) GetFrame(ctx context.Context) (*Frame, error) {
	select {
	case <-ctx.Done():
		return nil, ctx.Err()
	case frame, ok := <-c.frames:
		if !ok {
			return nil, fmt.Errorf("camera stopped")
		}
		return frame, nil
	case <-time.After(5 * time.Second):
		return nil, fmt.Errorf("timeout waiting for frame")
	}
}

// GetLastFrame returns the most recent frame
func (c *Camera) GetLastFrame() *Frame {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.lastFrame
}

// GetStats returns camera statistics
func (c *Camera) GetStats() CameraStats {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.stats
}

// capture reads frames from RTSP using ffmpeg
func (c *Camera) capture(ctx context.Context) {
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}
		
		if err := c.runFFmpeg(ctx); err != nil {
			log.Printf("⚠️ Camera %s: ffmpeg error: %v, retrying...", c.ID, err)
			time.Sleep(2 * time.Second)
		}
	}
}

func (c *Camera) runFFmpeg(ctx context.Context) error {
	// FFmpeg command to read RTSP and output raw frames
	args := []string{
		"-rtsp_transport", "tcp",
		"-i", c.RTSPURL,
		"-f", "image2pipe",
		"-pix_fmt", "rgb24",
		"-vcodec", "mjpeg",
		"-q:v", "5",
		"-r", fmt.Sprintf("%d", c.FPS),
		"-vf", fmt.Sprintf("scale=%d:%d", c.Width, c.Height),
		"-an",
		"-",
	}
	
	c.mu.Lock()
	c.cmd = exec.CommandContext(ctx, "ffmpeg", args...)
	stdout, err := c.cmd.StdoutPipe()
	c.mu.Unlock()
	
	if err != nil {
		return fmt.Errorf("failed to create stdout pipe: %w", err)
	}
	
	if err := c.cmd.Start(); err != nil {
		return fmt.Errorf("failed to start ffmpeg: %w", err)
	}
	
	// Read JPEG frames from ffmpeg output
	buf := make([]byte, 1024*1024) // 1MB buffer
	jpegData := bytes.Buffer{}
	
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}
		
		n, err := stdout.Read(buf)
		if err != nil {
			if err == io.EOF {
				break
			}
			return fmt.Errorf("read error: %w", err)
		}
		
		jpegData.Write(buf[:n])
		
		// Try to decode complete JPEG frames
		for {
			frame, remaining, err := extractJPEGFrame(jpegData.Bytes())
			if err != nil || frame == nil {
				break
			}
			
			// Create frame
			f := &Frame{
				Image:     frame,
				Timestamp: time.Now(),
				Width:     frame.Bounds().Dx(),
				Height:    frame.Bounds().Dy(),
			}
			
			c.mu.Lock()
			c.lastFrame = f
			c.stats.FramesProcessed++
			c.stats.LastFrameTime = time.Now()
			c.mu.Unlock()
			
			// Try to send frame (non-blocking)
			select {
			case c.frames <- f:
			default:
				c.mu.Lock()
				c.stats.FramesDropped++
				c.mu.Unlock()
			}
			
			// Keep remaining data
			jpegData.Reset()
			jpegData.Write(remaining)
		}
	}
	
	return c.cmd.Wait()
}

// extractJPEGFrame extracts a complete JPEG frame from data
func extractJPEGFrame(data []byte) (image.Image, []byte, error) {
	// Find JPEG start marker (FFD8)
	start := bytes.Index(data, []byte{0xFF, 0xD8})
	if start < 0 {
		return nil, data, nil
	}
	
	// Find JPEG end marker (FFD9)
	end := bytes.Index(data[start:], []byte{0xFF, 0xD9})
	if end < 0 {
		return nil, data, nil
	}
	
	end += start + 2 // Include the marker itself
	
	// Decode JPEG
	img, err := jpeg.Decode(bytes.NewReader(data[start:end]))
	if err != nil {
		// Skip invalid data
		return nil, data[end:], nil
	}
	
	return img, data[end:], nil
}

// EncodeJPEG encodes an image to JPEG
func EncodeJPEG(img image.Image, quality int) ([]byte, error) {
	var buf bytes.Buffer
	err := jpeg.Encode(&buf, img, &jpeg.Options{Quality: quality})
	return buf.Bytes(), err
}
