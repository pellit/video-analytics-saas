<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use Laravel\Sanctum\PersonalAccessToken;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Redis;
use Symfony\Component\HttpFoundation\StreamedResponse;

class SseController extends Controller
{
    public function stream(Request $request)
    {
        // Try normal bearer auth first
        $user = $request->user();
        // Fallback: accept ?token=xxxx to support EventSource (can't set Authorization header easily)
        if (!$user) {
            $token = $request->query('token') ?? $request->query('_t');
            if ($token) {
                $pat = PersonalAccessToken::findToken($token);
                if ($pat) {
                    $user = $pat->tokenable; // the user
                    Auth::setUser($user);
                }
            }
        }
        if (!$user) return response()->json(['message' => 'Unauthorized'], 401);

        $response = new StreamedResponse(function () use ($user) {
            \Illuminate\Support\Facades\Log::info("SSE: Starting stream for user " . $user->id);
            try {
                // Set headers for SSE
                echo "retry: 2000\n\n";
                if (ob_get_level() > 0) ob_flush();
                flush();

                $pubsub = Redis::connection()->pubSub();
                $pubsub->subscribe(['alerts', 'detections', 'bev_events']);

                foreach ($pubsub as $message) {
                    if ($message->kind === 'message') {
                        try {
                            $payload = json_decode($message->payload, true);
                            // Filter by user_id: only send messages that belong to this user
                            if (isset($payload['user_id']) && intval($payload['user_id']) !== intval($user->id)) {
                                continue;
                            }
                            // SSE event name is the Redis channel (map bev_events to 'bev' for frontend)
                            $eventName = $message->channel === 'bev_events' ? 'bev' : $message->channel;
                            echo "event: {$eventName}\n";
                            echo 'data: ' . json_encode($payload) . "\n\n";
                            if (ob_get_level() > 0) ob_flush();
                            flush();
                        } catch (\Exception $e) {
                            \Illuminate\Support\Facades\Log::error("SSE Payload Error: " . $e->getMessage());
                        }
                    }
                }
            } catch (\Exception $e) {
                \Illuminate\Support\Facades\Log::error("SSE Stream Error: " . $e->getMessage());
                echo "event: error\n";
                echo 'data: {"message": "Server Error"}' . "\n\n";
                if (ob_get_level() > 0) ob_flush();
                flush();
            }
        });

        $response->headers->set('Content-Type', 'text/event-stream');
        $response->headers->set('Cache-Control', 'no-cache');
        $response->headers->set('Connection', 'keep-alive');
        $response->headers->set('X-Accel-Buffering', 'no');

        return $response;
    }
}
