<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use App\Models\ApiKey;
use App\Models\ApiUsageLog;
use App\Models\ApiUsageDaily;
use Illuminate\Support\Facades\DB;

class AdminApiController extends Controller
{
    /**
     * Get API usage overview for admin dashboard
     */
    public function overview(Request $request)
    {
        // Total API keys
        $totalKeys = ApiKey::count();
        $activeKeys = ApiKey::where('is_active', true)->count();

        // Today's usage
        $todayStats = ApiUsageDaily::where('date', today())
            ->selectRaw('
                SUM(request_count) as total_requests,
                SUM(frames_processed) as total_frames,
                SUM(detections_count) as total_detections,
                SUM(bytes_received) as total_bytes,
                SUM(errors_count) as total_errors
            ')
            ->first();

        // Last 7 days trend
        $weeklyTrend = ApiUsageDaily::where('date', '>=', now()->subDays(7))
            ->selectRaw('
                date,
                SUM(request_count) as requests,
                SUM(frames_processed) as frames,
                SUM(detections_count) as detections
            ')
            ->groupBy('date')
            ->orderBy('date')
            ->get();

        // Top API keys by usage (last 7 days)
        $topKeys = ApiUsageDaily::where('date', '>=', now()->subDays(7))
            ->selectRaw('
                api_key_id,
                SUM(request_count) as total_requests,
                SUM(frames_processed) as total_frames
            ')
            ->groupBy('api_key_id')
            ->orderByDesc('total_requests')
            ->limit(10)
            ->with('apiKey:id,name,key_prefix,user_id')
            ->with('apiKey.user:id,name,email')
            ->get();

        // Recent errors
        $recentErrors = ApiUsageLog::where('response_code', '>=', 400)
            ->orderBy('created_at', 'desc')
            ->limit(10)
            ->with('apiKey:id,name,key_prefix')
            ->get();

        // Active sessions (from Redis)
        $activeSessions = $this->getActiveSessions();

        return response()->json([
            'summary' => [
                'total_api_keys' => $totalKeys,
                'active_api_keys' => $activeKeys,
                'today' => [
                    'requests' => (int) ($todayStats->total_requests ?? 0),
                    'frames' => (int) ($todayStats->total_frames ?? 0),
                    'detections' => (int) ($todayStats->total_detections ?? 0),
                    'bytes' => (int) ($todayStats->total_bytes ?? 0),
                    'errors' => (int) ($todayStats->total_errors ?? 0),
                ],
            ],
            'weekly_trend' => $weeklyTrend,
            'top_keys' => $topKeys,
            'recent_errors' => $recentErrors,
            'active_sessions' => $activeSessions,
        ]);
    }

    /**
     * List all API keys with usage stats (admin view)
     */
    public function listKeys(Request $request)
    {
        $query = ApiKey::with('user:id,name,email')
            ->withCount(['usageLogs as total_requests'])
            ->withSum(['dailyStats as total_frames' => function($q) {
                $q->where('date', '>=', now()->subDays(30));
            }], 'frames_processed');

        // Filters
        if ($request->has('user_id')) {
            $query->where('user_id', $request->user_id);
        }
        if ($request->has('is_active')) {
            $query->where('is_active', $request->boolean('is_active'));
        }
        if ($request->has('search')) {
            $search = $request->search;
            $query->where(function($q) use ($search) {
                $q->where('name', 'like', "%{$search}%")
                  ->orWhere('key_prefix', 'like', "%{$search}%");
            });
        }

        $keys = $query->orderBy('created_at', 'desc')
            ->paginate($request->get('per_page', 20));

        return response()->json($keys);
    }

    /**
     * Get detailed stats for a specific API key (admin)
     */
    public function keyStats(Request $request, int $id)
    {
        $apiKey = ApiKey::with('user:id,name,email')->findOrFail($id);

        // Last 30 days stats
        $dailyStats = $apiKey->dailyStats()
            ->where('date', '>=', now()->subDays(30))
            ->orderBy('date')
            ->get();

        // Recent logs
        $recentLogs = $apiKey->usageLogs()
            ->orderBy('created_at', 'desc')
            ->limit(50)
            ->get();

        // Endpoints breakdown
        $endpointsBreakdown = $apiKey->usageLogs()
            ->where('created_at', '>=', now()->subDays(7))
            ->selectRaw('endpoint, COUNT(*) as count, AVG(response_time_ms) as avg_time')
            ->groupBy('endpoint')
            ->get();

        return response()->json([
            'api_key' => $apiKey,
            'daily_stats' => $dailyStats,
            'recent_logs' => $recentLogs,
            'endpoints_breakdown' => $endpointsBreakdown,
        ]);
    }

    /**
     * Toggle API key status (admin)
     */
    public function toggleKey(Request $request, int $id)
    {
        $apiKey = ApiKey::findOrFail($id);
        $apiKey->update(['is_active' => !$apiKey->is_active]);

        return response()->json([
            'message' => $apiKey->is_active ? 'API key activated' : 'API key deactivated',
            'is_active' => $apiKey->is_active,
        ]);
    }

    /**
     * Delete API key (admin)
     */
    public function deleteKey(Request $request, int $id)
    {
        $apiKey = ApiKey::findOrFail($id);
        $apiKey->delete();

        return response()->json([
            'message' => 'API key deleted',
        ]);
    }

    /**
     * Get active API sessions from Redis
     */
    private function getActiveSessions(): array
    {
        try {
            $keys = \Illuminate\Support\Facades\Redis::keys('api_session_*');
            $sessions = [];
            
            foreach ($keys as $key) {
                $data = \Illuminate\Support\Facades\Redis::get($key);
                if ($data) {
                    $session = json_decode($data, true);
                    $session['session_id'] = str_replace('api_session_', '', $key);
                    $sessions[] = $session;
                }
            }
            
            return $sessions;
        } catch (\Exception $e) {
            return [];
        }
    }

    /**
     * Real-time API activity feed (last N requests)
     */
    public function activityFeed(Request $request)
    {
        $limit = $request->get('limit', 20);
        
        $logs = ApiUsageLog::with('apiKey:id,name,key_prefix')
            ->orderBy('created_at', 'desc')
            ->limit($limit)
            ->get();

        return response()->json($logs);
    }
}
