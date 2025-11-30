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
            // Set headers for SSE
            echo "retry: 2000\n\n";
            ob_flush();
            flush();

            $pubsub = Redis::connection()->pubSub();
            $pubsub->subscribe(['alerts', 'detections']);

            foreach ($pubsub as $message) {
                if ($message->kind === 'message') {
                    try {
                        $payload = json_decode($message->payload, true);
                        // Filter by user_id: only send messages that belong to this user
                        if (isset($payload['user_id']) && intval($payload['user_id']) !== intval($user->id)) {
                            continue;
                        }
                        // SSE event name is the Redis channel
                        echo "event: {$message->channel}\n";
                        echo 'data: ' . json_encode($payload) . "\n\n";
                        ob_flush();
                        flush();
                    } catch (\Exception $e) {
                        // ignore
                    }
                }
            }
        }, 200, [
            'Content-Type' => 'text/event-stream',
            'Cache-Control' => 'no-cache',
            'Connection' => 'keep-alive',
        ]);

        return $response;
    }
}
