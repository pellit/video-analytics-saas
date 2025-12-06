package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/go-redis/redis/v8"
	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/cors"
	"github.com/pellit/video-analytics-saas/ai_engine_go/internal/detector"
	"github.com/pellit/video-analytics-saas/ai_engine_go/internal/stream"
	"github.com/pellit/video-analytics-saas/ai_engine_go/internal/worker"
)

type Config struct {
	RedisHost      string
	RedisPort      string
	RedisPassword  string
	WorkerID       string
	HTTPPort       string
	ModelPath      string
	NumWorkers     int
}

func loadConfig() Config {
	return Config{
		RedisHost:     getEnv("REDIS_HOST", "localhost"),
		RedisPort:     getEnv("REDIS_PORT", "6379"),
		RedisPassword: getEnv("REDIS_PASSWORD", ""),
		WorkerID:      getEnv("WORKER_ID", "go-worker-1"),
		HTTPPort:      getEnv("HTTP_PORT", "8002"),
		ModelPath:     getEnv("MODEL_PATH", "./models/yolov8n.onnx"),
		NumWorkers:    getEnvInt("NUM_WORKERS", 4),
	}
}

func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

func getEnvInt(key string, defaultValue int) int {
	if value := os.Getenv(key); value != "" {
		var result int
		fmt.Sscanf(value, "%d", &result)
		return result
	}
	return defaultValue
}

func main() {
	log.Println("🚀 Starting Go AI Worker...")
	
	config := loadConfig()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Initialize Redis client
	rdb := redis.NewClient(&redis.Options{
		Addr:     fmt.Sprintf("%s:%s", config.RedisHost, config.RedisPort),
		Password: config.RedisPassword,
		DB:       0,
	})
	defer rdb.Close()

	// Test Redis connection
	if err := rdb.Ping(ctx).Err(); err != nil {
		log.Fatalf("❌ Failed to connect to Redis: %v", err)
	}
	log.Println("✅ Connected to Redis")

	// Initialize detector
	det, err := detector.NewONNXDetector(config.ModelPath)
	if err != nil {
		log.Fatalf("❌ Failed to load model: %v", err)
	}
	defer det.Close()
	log.Printf("✅ Loaded model: %s", config.ModelPath)

	// Initialize stream manager
	streamManager := stream.NewManager()

	// Initialize worker pool
	workerPool := worker.NewPool(config.NumWorkers, det, streamManager, rdb)
	go workerPool.Start(ctx)
	log.Printf("✅ Started %d worker goroutines", config.NumWorkers)

	// Subscribe to camera commands
	go subscribeToCommands(ctx, rdb, workerPool, config.WorkerID)

	// Start HTTP server
	app := setupHTTPServer(config, rdb, det, workerPool)
	
	// Graceful shutdown
	go func() {
		sigChan := make(chan os.Signal, 1)
		signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
		<-sigChan
		log.Println("🛑 Shutting down...")
		cancel()
		app.Shutdown()
	}()

	// Publish worker status
	go publishHealthStatus(ctx, rdb, config.WorkerID, workerPool)

	log.Printf("🌐 HTTP server starting on port %s", config.HTTPPort)
	if err := app.Listen(":" + config.HTTPPort); err != nil {
		log.Fatalf("❌ HTTP server error: %v", err)
	}
}

func setupHTTPServer(config Config, rdb *redis.Client, det *detector.ONNXDetector, pool *worker.Pool) *fiber.App {
	app := fiber.New(fiber.Config{
		DisableStartupMessage: true,
	})

	app.Use(cors.New())

	// Health check
	app.Get("/health", func(c *fiber.Ctx) error {
		return c.JSON(fiber.Map{
			"status":       "healthy",
			"worker_id":    config.WorkerID,
			"model":        det.ModelName(),
			"active_tasks": pool.ActiveTasks(),
			"timestamp":    time.Now().UTC().Format(time.RFC3339),
		})
	})

	// List available models
	app.Get("/models", func(c *fiber.Ctx) error {
		models := []fiber.Map{
			{
				"id":          "yolov8n",
				"name":        "YOLOv8 Nano (Go)",
				"description": "Go implementation with ONNX Runtime",
				"fps":         "40-60",
				"accuracy":    "medium-high",
				"device":      "cpu",
			},
		}
		return c.JSON(fiber.Map{
			"models":         models,
			"current_model": det.ModelName(),
		})
	})

	// Video feed endpoint
	app.Get("/video_feed/:camera_id", func(c *fiber.Ctx) error {
		cameraID := c.Params("camera_id")
		
		c.Set("Content-Type", "multipart/x-mixed-replace; boundary=frame")
		c.Set("Cache-Control", "no-cache")
		
		return pool.StreamVideo(c.Context(), cameraID, c.Response().BodyWriter())
	})

	// Start camera processing
	app.Post("/camera/:camera_id/start", func(c *fiber.Ctx) error {
		cameraID := c.Params("camera_id")
		
		var body struct {
			RTSPURL   string  `json:"rtsp_url"`
			ModelID   string  `json:"model_id"`
			Threshold float32 `json:"threshold"`
		}
		if err := c.BodyParser(&body); err != nil {
			return c.Status(400).JSON(fiber.Map{"error": "invalid request body"})
		}

		if err := pool.StartCamera(cameraID, body.RTSPURL, body.ModelID, body.Threshold); err != nil {
			return c.Status(500).JSON(fiber.Map{"error": err.Error()})
		}

		return c.JSON(fiber.Map{
			"status":    "started",
			"camera_id": cameraID,
		})
	})

	// Stop camera processing
	app.Post("/camera/:camera_id/stop", func(c *fiber.Ctx) error {
		cameraID := c.Params("camera_id")
		pool.StopCamera(cameraID)
		return c.JSON(fiber.Map{
			"status":    "stopped",
			"camera_id": cameraID,
		})
	})

	// Get camera stats
	app.Get("/camera/:camera_id/stats", func(c *fiber.Ctx) error {
		cameraID := c.Params("camera_id")
		stats := pool.GetCameraStats(cameraID)
		return c.JSON(stats)
	})

	return app
}

func subscribeToCommands(ctx context.Context, rdb *redis.Client, pool *worker.Pool, workerID string) {
	pubsub := rdb.Subscribe(ctx, "camera_commands", fmt.Sprintf("worker:%s:commands", workerID))
	defer pubsub.Close()

	ch := pubsub.Channel()
	for {
		select {
		case <-ctx.Done():
			return
		case msg := <-ch:
			handleCommand(ctx, msg, pool, rdb)
		}
	}
}

func handleCommand(ctx context.Context, msg *redis.Message, pool *worker.Pool, rdb *redis.Client) {
	var cmd struct {
		Action    string  `json:"action"`
		CameraID  string  `json:"camera_id"`
		RTSPURL   string  `json:"rtsp_url"`
		ModelID   string  `json:"model_id"`
		Threshold float32 `json:"threshold"`
	}
	
	if err := json.Unmarshal([]byte(msg.Payload), &cmd); err != nil {
		log.Printf("⚠️ Invalid command: %v", err)
		return
	}

	log.Printf("📨 Received command: %s for camera %s", cmd.Action, cmd.CameraID)

	switch cmd.Action {
	case "start":
		if err := pool.StartCamera(cmd.CameraID, cmd.RTSPURL, cmd.ModelID, cmd.Threshold); err != nil {
			log.Printf("❌ Failed to start camera %s: %v", cmd.CameraID, err)
		}
	case "stop":
		pool.StopCamera(cmd.CameraID)
	case "update_model":
		pool.UpdateCameraModel(cmd.CameraID, cmd.ModelID, cmd.Threshold)
	}
}

func publishHealthStatus(ctx context.Context, rdb *redis.Client, workerID string, pool *worker.Pool) {
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			status := map[string]interface{}{
				"worker_id":    workerID,
				"status":       "healthy",
				"active_tasks": pool.ActiveTasks(),
				"timestamp":    time.Now().UTC().Format(time.RFC3339),
				"implementation": "go",
			}
			data, _ := json.Marshal(status)
			rdb.Publish(ctx, "worker_health", string(data))
		}
	}
}
