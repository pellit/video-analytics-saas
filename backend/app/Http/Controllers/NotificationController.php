<?php

namespace App\Http\Controllers;

use App\Models\UserNotification;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;

class NotificationController extends Controller
{
    /**
     * Get all notifications for the authenticated user.
     */
    public function index(Request $request)
    {
        $query = UserNotification::forUser(Auth::id())
            ->orderBy('created_at', 'desc');
        
        // Filter by read status
        if ($request->has('unread_only') && $request->unread_only) {
            $query->unread();
        }
        
        // Filter by type
        if ($request->has('type')) {
            $query->byType($request->type);
        }
        
        // Filter by priority
        if ($request->has('priority')) {
            $query->byPriority($request->priority);
        }
        
        $notifications = $query->paginate($request->per_page ?? 20);
        
        return response()->json($notifications);
    }

    /**
     * Get unread notification count.
     */
    public function unreadCount()
    {
        $count = UserNotification::forUser(Auth::id())
            ->unread()
            ->count();
        
        return response()->json(['count' => $count]);
    }

    /**
     * Mark a notification as read.
     */
    public function markRead(UserNotification $notification)
    {
        // Verify ownership
        if ($notification->user_id !== Auth::id()) {
            return response()->json(['error' => 'Unauthorized'], 403);
        }
        
        $notification->markAsRead();
        
        return response()->json(['success' => true]);
    }

    /**
     * Mark all notifications as read.
     */
    public function markAllRead()
    {
        UserNotification::forUser(Auth::id())
            ->unread()
            ->update([
                'read' => true,
                'read_at' => now(),
            ]);
        
        return response()->json(['success' => true]);
    }

    /**
     * Send a new notification (internal use or admin).
     */
    public function send(Request $request)
    {
        $validated = $request->validate([
            'title' => 'required|string|max:255',
            'message' => 'required|string',
            'priority' => 'in:low,medium,high,critical',
            'type' => 'in:info,success,warning,error,alert',
            'zone_id' => 'nullable|integer',
            'action_url' => 'nullable|string',
        ]);
        
        $notification = UserNotification::create([
            'user_id' => Auth::id(),
            'title' => $validated['title'],
            'message' => $validated['message'],
            'type' => $validated['type'] ?? 'alert',
            'priority' => $validated['priority'] ?? 'medium',
            'action_url' => $validated['action_url'] ?? null,
            'data' => [
                'zone_id' => $validated['zone_id'] ?? null,
            ],
        ]);
        
        // TODO: Implement actual push notification (FCM, WebPush, etc.)
        // For now, we just mark it as "sent" immediately
        $notification->markPushSent();
        
        return response()->json([
            'success' => true,
            'notification' => $notification,
        ]);
    }

    /**
     * Delete a notification.
     */
    public function destroy(UserNotification $notification)
    {
        // Verify ownership
        if ($notification->user_id !== Auth::id()) {
            return response()->json(['error' => 'Unauthorized'], 403);
        }
        
        $notification->delete();
        
        return response()->json(['success' => true]);
    }

    /**
     * Get recent notifications for real-time updates (polling endpoint).
     */
    public function recent(Request $request)
    {
        $since = $request->since 
            ? \Carbon\Carbon::parse($request->since) 
            : now()->subMinutes(5);
        
        $notifications = UserNotification::forUser(Auth::id())
            ->where('created_at', '>', $since)
            ->orderBy('created_at', 'desc')
            ->get();
        
        return response()->json([
            'notifications' => $notifications,
            'timestamp' => now()->toIso8601String(),
        ]);
    }
}
