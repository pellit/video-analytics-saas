<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class UserNotification extends Model
{
    use HasFactory;

    protected $fillable = [
        'user_id',
        'title',
        'message',
        'type',
        'priority',
        'source_type',
        'source_id',
        'read',
        'read_at',
        'push_sent',
        'push_sent_at',
        'email_sent',
        'email_sent_at',
        'action_url',
        'action_text',
        'data',
    ];

    protected $casts = [
        'data' => 'array',
        'read' => 'boolean',
        'push_sent' => 'boolean',
        'email_sent' => 'boolean',
        'read_at' => 'datetime',
        'push_sent_at' => 'datetime',
        'email_sent_at' => 'datetime',
    ];

    protected $appends = ['icon', 'time_ago'];

    // Relationships
    public function user()
    {
        return $this->belongsTo(User::class);
    }

    public function source()
    {
        return $this->morphTo();
    }

    // Accessors
    public function getIconAttribute(): string
    {
        return match($this->type) {
            'info' => 'ℹ️',
            'success' => '✅',
            'warning' => '⚠️',
            'error' => '❌',
            'alert' => '🚨',
            default => '📢',
        };
    }

    public function getTimeAgoAttribute(): string
    {
        return $this->created_at->diffForHumans();
    }

    // Scopes
    public function scopeUnread($query)
    {
        return $query->where('read', false);
    }

    public function scopeForUser($query, $userId)
    {
        return $query->where('user_id', $userId);
    }

    public function scopeByPriority($query, $priority)
    {
        return $query->where('priority', $priority);
    }

    public function scopeByType($query, $type)
    {
        return $query->where('type', $type);
    }

    public function scopeRecent($query, $days = 7)
    {
        return $query->where('created_at', '>=', now()->subDays($days));
    }

    public function scopePendingPush($query)
    {
        return $query->where('push_sent', false);
    }

    // Methods
    public function markAsRead(): void
    {
        $this->update([
            'read' => true,
            'read_at' => now(),
        ]);
    }

    public function markPushSent(): void
    {
        $this->update([
            'push_sent' => true,
            'push_sent_at' => now(),
        ]);
    }

    public function markEmailSent(): void
    {
        $this->update([
            'email_sent' => true,
            'email_sent_at' => now(),
        ]);
    }

    // Static factory methods
    public static function createForSatelliteAnalysis(
        SatelliteAnalysis $analysis,
        string $title,
        string $message
    ): self {
        return self::create([
            'user_id' => $analysis->user_id,
            'title' => $title,
            'message' => $message,
            'type' => 'alert',
            'priority' => $analysis->getNotificationPriority(),
            'source_type' => SatelliteAnalysis::class,
            'source_id' => $analysis->id,
            'action_url' => "/satellite/analysis/{$analysis->id}",
            'action_text' => 'Ver Análisis',
            'data' => [
                'zone_name' => $analysis->zone_name,
                'change_percent' => $analysis->change_percent,
                'severity' => $analysis->severity,
            ],
        ]);
    }

    public static function createAlert(
        int $userId,
        string $title,
        string $message,
        string $priority = 'medium',
        ?string $actionUrl = null
    ): self {
        return self::create([
            'user_id' => $userId,
            'title' => $title,
            'message' => $message,
            'type' => 'alert',
            'priority' => $priority,
            'action_url' => $actionUrl,
        ]);
    }
}
