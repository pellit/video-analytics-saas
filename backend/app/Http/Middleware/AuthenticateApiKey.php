<?php

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;
use App\Models\ApiKey;

class AuthenticateApiKey
{
    /**
     * Handle an incoming request.
     *
     * @param  \Closure(\Illuminate\Http\Request): (\Symfony\Component\HttpFoundation\Response)  $next
     */
    public function handle(Request $request, Closure $next, string $permission = null): Response
    {
        $apiKeyHeader = $request->header('X-API-Key') ?? $request->header('Authorization');
        
        // Remove "Bearer " prefix if present
        if ($apiKeyHeader && str_starts_with($apiKeyHeader, 'Bearer ')) {
            $apiKeyHeader = substr($apiKeyHeader, 7);
        }

        if (!$apiKeyHeader) {
            return response()->json([
                'error' => 'API key required',
                'message' => 'Please provide your API key in the X-API-Key header'
            ], 401);
        }

        $apiKey = ApiKey::findByKey($apiKeyHeader);

        if (!$apiKey) {
            return response()->json([
                'error' => 'Invalid API key',
                'message' => 'The provided API key is invalid or has expired'
            ], 401);
        }

        // Check permission if specified
        if ($permission && !$apiKey->hasPermission($permission)) {
            return response()->json([
                'error' => 'Permission denied',
                'message' => "This API key does not have the '{$permission}' permission"
            ], 403);
        }

        // Check rate limit
        if ($apiKey->isRateLimitExceeded()) {
            return response()->json([
                'error' => 'Rate limit exceeded',
                'message' => "You have exceeded the rate limit of {$apiKey->rate_limit} requests per minute",
                'retry_after' => 60
            ], 429);
        }

        // Check daily limit
        if ($apiKey->getTodayUsageCount() >= $apiKey->daily_limit) {
            return response()->json([
                'error' => 'Daily limit exceeded',
                'message' => "You have exceeded the daily limit of {$apiKey->daily_limit} requests",
                'retry_after' => now()->endOfDay()->diffInSeconds()
            ], 429);
        }

        // Increment rate limit counter
        $apiKey->incrementRateLimit();

        // Store API key in request for later use
        $request->attributes->set('api_key', $apiKey);
        $request->attributes->set('api_key_start_time', microtime(true));

        return $next($request);
    }
}
