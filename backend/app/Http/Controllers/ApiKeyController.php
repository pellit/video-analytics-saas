<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use App\Models\ApiKey;
use App\Models\ApiUsageDaily;
use App\Models\ApiUsageLog;

class ApiKeyController extends Controller
{
    /**
     * List user's API keys
     */
    public function index(Request $request)
    {
        $keys = Auth::user()->apiKeys()
            ->select('id', 'name', 'key_prefix', 'description', 'permissions', 'rate_limit', 'daily_limit', 'is_active', 'last_used_at', 'expires_at', 'created_at')
            ->withCount(['usageLogs as total_requests'])
            ->orderBy('created_at', 'desc')
            ->get();

        return response()->json($keys);
    }

    /**
     * Create a new API key
     */
    public function store(Request $request)
    {
        $validated = $request->validate([
            'name' => 'required|string|max:255',
            'description' => 'nullable|string|max:1000',
            'permissions' => 'nullable|array',
            'permissions.*' => 'string|in:analyze,stream,batch',
            'rate_limit' => 'nullable|integer|min:1|max:1000',
            'daily_limit' => 'nullable|integer|min:1|max:100000',
            'expires_at' => 'nullable|date|after:today',
        ]);

        // Check user's key limit (e.g., max 5 keys per user)
        $existingCount = Auth::user()->apiKeys()->count();
        if ($existingCount >= 5) {
            return response()->json([
                'error' => 'API key limit reached',
                'message' => 'You can have a maximum of 5 API keys',
            ], 400);
        }

        $result = ApiKey::generate(Auth::id(), $validated['name'], [
            'description' => $validated['description'] ?? null,
            'permissions' => $validated['permissions'] ?? ['analyze'],
            'rate_limit' => $validated['rate_limit'] ?? 100,
            'daily_limit' => $validated['daily_limit'] ?? 10000,
            'expires_at' => $validated['expires_at'] ?? null,
        ]);

        return response()->json([
            'message' => 'API key created successfully',
            'api_key' => [
                'id' => $result['api_key']->id,
                'name' => $result['api_key']->name,
                'key_prefix' => $result['api_key']->key_prefix,
                'permissions' => $result['api_key']->permissions,
            ],
            'raw_key' => $result['raw_key'], // Only shown once!
            'warning' => 'Save this key now! It will not be shown again.',
        ], 201);
    }

    /**
     * Get API key details with usage stats
     */
    public function show(Request $request, int $id)
    {
        $apiKey = Auth::user()->apiKeys()->findOrFail($id);
        
        // Get usage stats for last 30 days
        $dailyStats = $apiKey->dailyStats()
            ->where('date', '>=', now()->subDays(30))
            ->orderBy('date', 'desc')
            ->get();

        // Today's stats
        $todayStats = ApiUsageDaily::where('api_key_id', $id)
            ->where('date', today())
            ->first();

        return response()->json([
            'api_key' => [
                'id' => $apiKey->id,
                'name' => $apiKey->name,
                'key_prefix' => $apiKey->key_prefix,
                'description' => $apiKey->description,
                'permissions' => $apiKey->permissions,
                'rate_limit' => $apiKey->rate_limit,
                'daily_limit' => $apiKey->daily_limit,
                'is_active' => $apiKey->is_active,
                'last_used_at' => $apiKey->last_used_at,
                'expires_at' => $apiKey->expires_at,
                'created_at' => $apiKey->created_at,
            ],
            'today' => $todayStats ? [
                'requests' => $todayStats->request_count,
                'frames' => $todayStats->frames_processed,
                'detections' => $todayStats->detections_count,
                'errors' => $todayStats->errors_count,
            ] : null,
            'history' => $dailyStats,
        ]);
    }

    /**
     * Update API key
     */
    public function update(Request $request, int $id)
    {
        $apiKey = Auth::user()->apiKeys()->findOrFail($id);

        $validated = $request->validate([
            'name' => 'sometimes|string|max:255',
            'description' => 'nullable|string|max:1000',
            'permissions' => 'sometimes|array',
            'rate_limit' => 'sometimes|integer|min:1|max:1000',
            'daily_limit' => 'sometimes|integer|min:1|max:100000',
            'is_active' => 'sometimes|boolean',
        ]);

        $apiKey->update($validated);

        return response()->json([
            'message' => 'API key updated',
            'api_key' => $apiKey->fresh(),
        ]);
    }

    /**
     * Delete (revoke) API key
     */
    public function destroy(Request $request, int $id)
    {
        $apiKey = Auth::user()->apiKeys()->findOrFail($id);
        $apiKey->delete();

        return response()->json([
            'message' => 'API key revoked',
        ]);
    }

    /**
     * Regenerate API key (creates new key, invalidates old)
     */
    public function regenerate(Request $request, int $id)
    {
        $oldKey = Auth::user()->apiKeys()->findOrFail($id);
        
        // Create new key with same settings
        $result = ApiKey::generate(Auth::id(), $oldKey->name, [
            'description' => $oldKey->description,
            'permissions' => $oldKey->permissions,
            'rate_limit' => $oldKey->rate_limit,
            'daily_limit' => $oldKey->daily_limit,
            'expires_at' => $oldKey->expires_at,
        ]);

        // Delete old key
        $oldKey->delete();

        return response()->json([
            'message' => 'API key regenerated',
            'api_key' => [
                'id' => $result['api_key']->id,
                'name' => $result['api_key']->name,
                'key_prefix' => $result['api_key']->key_prefix,
            ],
            'raw_key' => $result['raw_key'],
            'warning' => 'Save this key now! It will not be shown again.',
        ]);
    }
}
