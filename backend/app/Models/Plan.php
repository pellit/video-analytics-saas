<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class Plan extends Model
{
    use HasFactory;

    protected $fillable = [
        'name',
        'display_name',
        'stripe_price_id',
        'price',
        'currency',
        'camera_limit',
        'analysis_hours_per_day',
        'ai_advanced',
        'vlm_access',
        'satellite_access',
        'cad_access',
        'api_access',
        'api_calls_per_day',
        'email_alerts',
        'telegram_alerts',
        'recording',
        'retention_days',
        'features',
        'is_active',
        'sort_order',
    ];

    protected $casts = [
        'price' => 'decimal:2',
        'ai_advanced' => 'boolean',
        'vlm_access' => 'boolean',
        'satellite_access' => 'boolean',
        'cad_access' => 'boolean',
        'api_access' => 'boolean',
        'email_alerts' => 'boolean',
        'telegram_alerts' => 'boolean',
        'recording' => 'boolean',
        'is_active' => 'boolean',
        'features' => 'array',
    ];

    /**
     * Get active plans ordered by sort_order
     */
    public function scopeActive($query)
    {
        return $query->where('is_active', true)->orderBy('sort_order');
    }

    /**
     * Get the free plan (with fallback if not in DB)
     */
    public static function free()
    {
        $plan = static::where('name', 'free')->first();
        
        // If no plan in DB, return a default free plan object
        if (!$plan) {
            $plan = new static([
                'name' => 'free',
                'display_name' => 'Plan Free',
                'price' => 0,
                'currency' => 'USD',
                'camera_limit' => 1,
                'analysis_hours_per_day' => 1,
                'ai_advanced' => false,
                'vlm_access' => false,
                'satellite_access' => false,
                'cad_access' => false,
                'api_access' => false,
                'api_calls_per_day' => 0,
                'email_alerts' => false,
                'telegram_alerts' => false,
                'recording' => false,
                'retention_days' => 0,
                'features' => ['yolo_basic' => true, 'live_view' => true],
                'is_active' => true,
            ]);
        }
        
        return $plan;
    }

    /**
     * Get subscriptions for this plan
     */
    public function subscriptions()
    {
        return $this->hasMany(Subscription::class);
    }

    /**
     * Check if plan has a specific feature
     */
    public function hasFeature(string $feature): bool
    {
        $features = $this->features ?? [];
        
        // Si tiene 'all_features', tiene todo
        if (isset($features['all_features']) && $features['all_features']) {
            return true;
        }
        
        return isset($features[$feature]) && $features[$feature];
    }

    /**
     * Check if plan allows specific detection type
     */
    public function canDetect(string $type): bool
    {
        $features = $this->features ?? [];
        
        if ($this->hasFeature('all_detections')) {
            return true;
        }
        
        $basic = $features['basic_detections'] ?? [];
        $advanced = $features['advanced_detections'] ?? [];
        
        return in_array($type, $basic) || in_array($type, $advanced);
    }

    /**
     * Get formatted price
     */
    public function getFormattedPriceAttribute(): string
    {
        if ($this->price == 0) {
            return 'Gratis';
        }
        
        return '$' . number_format($this->price, 2) . '/' . __('mes');
    }

    /**
     * Get limits as array for frontend
     */
    public function getLimitsAttribute(): array
    {
        return [
            'cameras' => $this->camera_limit,
            'analysis_hours' => $this->analysis_hours_per_day,
            'api_calls' => $this->api_calls_per_day,
            'retention_days' => $this->retention_days,
        ];
    }
}
