<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Support\Str;

class ApiKey extends Model
{
    use HasFactory;

    protected $fillable = [
        'user_id',
        'name',
        'key',
        'key_prefix',
        'description',
        'permissions',
        'rate_limit',
        'daily_limit',
        'is_active',
        'last_used_at',
        'expires_at',
    ];

    protected $casts = [
        'permissions' => 'array',
        'is_active' => 'boolean',
        'last_used_at' => 'datetime',
        'expires_at' => 'datetime',
    ];

    protected $hidden = [
        'key', // Never expose the hashed key
    ];

    /**
     * Generate a new API key
     * Returns the raw key (only shown once) and creates the model
     */
    public static function generate(int $userId, string $name, array $options = []): array
    {
        $rawKey = 'vsa_' . Str::random(40); // vsa = Video SaaS Analytics
        $prefix = substr($rawKey, 0, 8);
        
        $apiKey = self::create([
            'user_id' => $userId,
            'name' => $name,
            'key' => hash('sha256', $rawKey),
            'key_prefix' => $prefix,
            'description' => $options['description'] ?? null,
            'permissions' => $options['permissions'] ?? ['analyze'],
            'rate_limit' => $options['rate_limit'] ?? 100,
            'daily_limit' => $options['daily_limit'] ?? 10000,
            'is_active' => true,
            'expires_at' => $options['expires_at'] ?? null,
        ]);

        return [
            'api_key' => $apiKey,
            'raw_key' => $rawKey, // This is only returned once!
        ];
    }

    /**
     * Find an API key by the raw key value
     */
    public static function findByKey(string $rawKey): ?self
    {
        $hashedKey = hash('sha256', $rawKey);
        return self::where('key', $hashedKey)
            ->where('is_active', true)
            ->where(function ($q) {
                $q->whereNull('expires_at')
                  ->orWhere('expires_at', '>', now());
            })
            ->first();
    }

    /**
     * Check if the key has a specific permission
     */
    public function hasPermission(string $permission): bool
    {
        return in_array($permission, $this->permissions ?? []);
    }

    /**
     * Update last used timestamp
     */
    public function touchLastUsed(): void
    {
        $this->update(['last_used_at' => now()]);
    }

    /**
     * Get today's usage count from cache or DB
     */
    public function getTodayUsageCount(): int
    {
        $cacheKey = "api_key_{$this->id}_daily_" . now()->format('Y-m-d');
        return cache()->remember($cacheKey, 60, function () {
            return ApiUsageLog::where('api_key_id', $this->id)
                ->whereDate('created_at', today())
                ->count();
        });
    }

    /**
     * Check if rate limit is exceeded (per minute)
     */
    public function isRateLimitExceeded(): bool
    {
        $cacheKey = "api_key_{$this->id}_minute_" . now()->format('Y-m-d-H-i');
        $count = cache()->get($cacheKey, 0);
        return $count >= $this->rate_limit;
    }

    /**
     * Increment rate limit counter
     */
    public function incrementRateLimit(): void
    {
        $cacheKey = "api_key_{$this->id}_minute_" . now()->format('Y-m-d-H-i');
        cache()->increment($cacheKey);
        cache()->put($cacheKey, cache()->get($cacheKey, 1), 60);
    }

    // Relationships
    public function user()
    {
        return $this->belongsTo(User::class);
    }

    public function usageLogs()
    {
        return $this->hasMany(ApiUsageLog::class);
    }

    public function dailyStats()
    {
        return $this->hasMany(ApiUsageDaily::class);
    }
}
