<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class UsageRecord extends Model
{
    protected $fillable = [
        'user_id',
        'camera_id',
        'metric',
        'quantity',
        'recorded_date',
    ];

    protected $casts = [
        'recorded_date' => 'date',
    ];

    public function user()
    {
        return $this->belongsTo(User::class);
    }

    public function camera()
    {
        return $this->belongsTo(Camera::class);
    }

    /**
     * Record usage for a user
     */
    public static function record(int $userId, string $metric, int $quantity, ?int $cameraId = null): self
    {
        return static::create([
            'user_id' => $userId,
            'camera_id' => $cameraId,
            'metric' => $metric,
            'quantity' => $quantity,
            'recorded_date' => now()->toDateString(),
        ]);
    }

    /**
     * Get today's usage for a user and metric
     */
    public static function todayUsage(int $userId, string $metric): int
    {
        return static::where('user_id', $userId)
                     ->where('metric', $metric)
                     ->where('recorded_date', now()->toDateString())
                     ->sum('quantity');
    }

    /**
     * Get usage for a period
     */
    public static function periodUsage(int $userId, string $metric, $from, $to): int
    {
        return static::where('user_id', $userId)
                     ->where('metric', $metric)
                     ->whereBetween('recorded_date', [$from, $to])
                     ->sum('quantity');
    }
}
