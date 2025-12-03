<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Redis;
use App\Models\ApiKey;
use App\Models\ApiUsageLog;
use App\Models\ApiUsageDaily;

class ExternalApiController extends Controller
{
    /**
     * Analyze a single frame/image
     * POST /api/v1/analyze/frame
     * 
     * Accepts: multipart/form-data with 'frame' file or JSON with base64 'image'
     */
    public function analyzeFrame(Request $request)
    {
        $startTime = microtime(true);
        $apiKey = $request->attributes->get('api_key');
        
        try {
            // Accept either file upload or base64
            $imageData = null;
            $payloadSize = 0;

            if ($request->hasFile('frame')) {
                $file = $request->file('frame');
                $imageData = base64_encode(file_get_contents($file->getRealPath()));
                $payloadSize = $file->getSize();
            } elseif ($request->has('image')) {
                $imageData = $request->input('image');
                // Remove data URL prefix if present
                if (str_contains($imageData, ',')) {
                    $imageData = explode(',', $imageData)[1];
                }
                $payloadSize = strlen(base64_decode($imageData));
            } else {
                return $this->errorResponse($request, $apiKey, 'No image provided', 400, $startTime);
            }

            // Options for analysis
            $options = [
                'model' => $request->input('model', 'yolov8n'),
                'detection_classes' => $request->input('classes', []),
                'confidence_threshold' => $request->input('confidence', 0.5),
                'return_annotated' => $request->boolean('return_annotated', false),
                'face_detection' => $request->boolean('face_detection', false),
                'depth_estimation' => $request->boolean('depth_estimation', false),
            ];

            // Send to AI worker via Redis for processing
            $requestId = uniqid('api_', true);
            $message = json_encode([
                'action' => 'ANALYZE_FRAME',
                'request_id' => $requestId,
                'api_key_id' => $apiKey->id,
                'image' => $imageData,
                'options' => $options,
            ]);

            // Use Redis pub/sub for async or a queue
            // For now, we'll use a synchronous approach with Redis blocking pop
            Redis::rpush('api_frame_queue', $message);
            
            // Wait for response (with timeout)
            $response = Redis::blpop("api_response_{$requestId}", 30);
            
            $responseTime = (int)((microtime(true) - $startTime) * 1000);

            if (!$response) {
                return $this->errorResponse($request, $apiKey, 'Analysis timeout', 504, $startTime, $payloadSize);
            }

            $result = json_decode($response[1], true);
            
            // Log usage
            $this->logUsage($request, $apiKey, 200, $responseTime, $payloadSize, [
                'request_id' => $requestId,
                'detections' => count($result['detections'] ?? []),
                'model' => $options['model'],
            ]);

            // Update daily stats
            $dailyStats = ApiUsageDaily::getOrCreateToday($apiKey->id);
            $dailyStats->incrementStats([
                'frames' => 1,
                'detections' => count($result['detections'] ?? []),
                'bytes' => $payloadSize,
                'response_time_ms' => $responseTime,
            ]);

            $apiKey->touchLastUsed();

            return response()->json([
                'success' => true,
                'request_id' => $requestId,
                'processing_time_ms' => $responseTime,
                'detections' => $result['detections'] ?? [],
                'annotated_image' => $result['annotated_image'] ?? null,
                'metadata' => $result['metadata'] ?? [],
            ]);

        } catch (\Exception $e) {
            return $this->errorResponse($request, $apiKey, $e->getMessage(), 500, $startTime);
        }
    }

    /**
     * Analyze a video stream (returns session ID for polling results)
     * POST /api/v1/analyze/stream
     */
    public function analyzeStream(Request $request)
    {
        $startTime = microtime(true);
        $apiKey = $request->attributes->get('api_key');

        $request->validate([
            'url' => 'required|url',
            'duration' => 'integer|min:1|max:300', // Max 5 minutes
            'callback_url' => 'nullable|url',
        ]);

        $sessionId = uniqid('stream_', true);
        
        $message = json_encode([
            'action' => 'ANALYZE_STREAM',
            'session_id' => $sessionId,
            'api_key_id' => $apiKey->id,
            'url' => $request->input('url'),
            'duration' => $request->input('duration', 60),
            'options' => [
                'model' => $request->input('model', 'yolov8n'),
                'detection_classes' => $request->input('classes', []),
                'callback_url' => $request->input('callback_url'),
                'sample_rate' => $request->input('sample_rate', 1), // Analyze every Nth frame
            ],
        ]);

        Redis::publish('video_control', $message);

        // Store session info in Redis
        Redis::setex("api_session_{$sessionId}", 3600, json_encode([
            'api_key_id' => $apiKey->id,
            'status' => 'processing',
            'started_at' => now()->toIso8601String(),
            'url' => $request->input('url'),
        ]));

        $responseTime = (int)((microtime(true) - $startTime) * 1000);
        
        $this->logUsage($request, $apiKey, 202, $responseTime, 0, [
            'session_id' => $sessionId,
            'url' => $request->input('url'),
        ]);

        $apiKey->touchLastUsed();

        return response()->json([
            'success' => true,
            'session_id' => $sessionId,
            'status' => 'processing',
            'poll_url' => url("/api/v1/analyze/status/{$sessionId}"),
            'message' => 'Stream analysis started. Poll the status URL for results.',
        ], 202);
    }

    /**
     * Get status of a stream analysis session
     * GET /api/v1/analyze/status/{sessionId}
     */
    public function getStatus(Request $request, string $sessionId)
    {
        $apiKey = $request->attributes->get('api_key');
        
        $sessionData = Redis::get("api_session_{$sessionId}");
        
        if (!$sessionData) {
            return response()->json([
                'error' => 'Session not found',
                'message' => 'The session may have expired or does not exist'
            ], 404);
        }

        $session = json_decode($sessionData, true);

        // Verify ownership
        if ($session['api_key_id'] !== $apiKey->id) {
            return response()->json([
                'error' => 'Access denied',
                'message' => 'You do not have access to this session'
            ], 403);
        }

        // Get results if available
        $results = Redis::lrange("api_results_{$sessionId}", 0, -1);
        $detections = array_map(fn($r) => json_decode($r, true), $results);

        return response()->json([
            'session_id' => $sessionId,
            'status' => $session['status'],
            'started_at' => $session['started_at'],
            'url' => $session['url'],
            'detections_count' => count($detections),
            'detections' => $detections,
        ]);
    }

    /**
     * Stop a stream analysis session
     * DELETE /api/v1/analyze/status/{sessionId}
     */
    public function stopSession(Request $request, string $sessionId)
    {
        $apiKey = $request->attributes->get('api_key');
        
        $sessionData = Redis::get("api_session_{$sessionId}");
        
        if (!$sessionData) {
            return response()->json(['error' => 'Session not found'], 404);
        }

        $session = json_decode($sessionData, true);

        if ($session['api_key_id'] !== $apiKey->id) {
            return response()->json(['error' => 'Access denied'], 403);
        }

        // Send stop command
        Redis::publish('video_control', json_encode([
            'action' => 'STOP_API_SESSION',
            'session_id' => $sessionId,
        ]));

        // Update session status
        $session['status'] = 'stopped';
        Redis::setex("api_session_{$sessionId}", 3600, json_encode($session));

        return response()->json([
            'success' => true,
            'message' => 'Session stopped',
        ]);
    }

    /**
     * Upload multiple frames for batch analysis
     * POST /api/v1/analyze/batch
     */
    public function analyzeBatch(Request $request)
    {
        $startTime = microtime(true);
        $apiKey = $request->attributes->get('api_key');

        $request->validate([
            'frames' => 'required|array|min:1|max:10',
            'frames.*' => 'required|string', // base64 images
        ]);

        $batchId = uniqid('batch_', true);
        $frames = $request->input('frames');
        $totalSize = 0;

        foreach ($frames as $idx => $frame) {
            if (str_contains($frame, ',')) {
                $frame = explode(',', $frame)[1];
            }
            $totalSize += strlen(base64_decode($frame));

            Redis::rpush('api_frame_queue', json_encode([
                'action' => 'ANALYZE_FRAME',
                'request_id' => "{$batchId}_{$idx}",
                'batch_id' => $batchId,
                'api_key_id' => $apiKey->id,
                'image' => $frame,
                'options' => [
                    'model' => $request->input('model', 'yolov8n'),
                    'detection_classes' => $request->input('classes', []),
                ],
            ]));
        }

        // Wait for all results
        $results = [];
        $timeout = 30 + (count($frames) * 5); // 5 extra seconds per frame
        
        for ($i = 0; $i < count($frames); $i++) {
            $response = Redis::blpop("api_response_{$batchId}_{$i}", $timeout);
            if ($response) {
                $results[] = json_decode($response[1], true);
            }
        }

        $responseTime = (int)((microtime(true) - $startTime) * 1000);

        $totalDetections = array_sum(array_map(fn($r) => count($r['detections'] ?? []), $results));

        $this->logUsage($request, $apiKey, 200, $responseTime, $totalSize, [
            'batch_id' => $batchId,
            'frames_count' => count($frames),
            'detections' => $totalDetections,
        ]);

        $dailyStats = ApiUsageDaily::getOrCreateToday($apiKey->id);
        $dailyStats->incrementStats([
            'frames' => count($frames),
            'detections' => $totalDetections,
            'bytes' => $totalSize,
            'response_time_ms' => $responseTime,
        ]);

        $apiKey->touchLastUsed();

        return response()->json([
            'success' => true,
            'batch_id' => $batchId,
            'frames_processed' => count($results),
            'total_detections' => $totalDetections,
            'processing_time_ms' => $responseTime,
            'results' => $results,
        ]);
    }

    /**
     * Log API usage
     */
    private function logUsage(Request $request, ApiKey $apiKey, int $responseCode, int $responseTimeMs, int $payloadSize = 0, array $metadata = []): void
    {
        ApiUsageLog::create([
            'api_key_id' => $apiKey->id,
            'endpoint' => $request->path(),
            'method' => $request->method(),
            'ip_address' => $request->ip(),
            'user_agent' => substr($request->userAgent() ?? '', 0, 255),
            'response_code' => $responseCode,
            'response_time_ms' => $responseTimeMs,
            'payload_size' => $payloadSize,
            'metadata' => $metadata,
            'created_at' => now(),
        ]);
    }

    /**
     * Return error response and log it
     */
    private function errorResponse(Request $request, ApiKey $apiKey, string $message, int $code, float $startTime, int $payloadSize = 0)
    {
        $responseTime = (int)((microtime(true) - $startTime) * 1000);
        
        $this->logUsage($request, $apiKey, $code, $responseTime, $payloadSize, [
            'error' => $message,
        ]);

        $dailyStats = ApiUsageDaily::getOrCreateToday($apiKey->id);
        $dailyStats->incrementStats(['error' => true]);

        return response()->json([
            'success' => false,
            'error' => $message,
        ], $code);
    }
}
