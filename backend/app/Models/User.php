<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Foundation\Auth\User as Authenticatable;
use Illuminate\Notifications\Notifiable;
use Laravel\Sanctum\HasApiTokens;

class User extends Authenticatable
{
    use HasApiTokens, HasFactory, Notifiable;

    /**
     * The attributes that are mass assignable.
     */
    protected $fillable = [
        'name',
        'email',
        'password',
        'role',
        'last_login_at',
        'stripe_id',
        'pm_type',
        'pm_last_four',
        'trial_ends_at',
        'plan_id',
    ];

    /**
     * The attributes that should be hidden for serialization.
     */
    protected $hidden = [
        'password',
        'remember_token',
        'stripe_id',
    ];

    /**
     * The attributes that should be cast.
     */
    protected $casts = [
        'email_verified_at' => 'datetime',
        'password' => 'hashed',
        'last_login_at' => 'datetime',
        'trial_ends_at' => 'datetime',
    ];

    // =========================================================================
    // RELATIONSHIPS
    // =========================================================================

    public function cameras()
    {
        return $this->hasMany(Camera::class);
    }

    public function alerts()
    {
        return $this->hasManyThrough(Alert::class, Camera::class);
    }

    public function apiKeys()
    {
        return $this->hasMany(ApiKey::class);
    }

    public function subscriptions()
    {
        return $this->hasMany(Subscription::class);
    }

    public function plan()
    {
        return $this->belongsTo(Plan::class);
    }

    public function usageRecords()
    {
        return $this->hasMany(UsageRecord::class);
    }

    // =========================================================================
    // SUBSCRIPTION HELPERS
    // =========================================================================

    /**
     * Check if user is superadmin (bypasses all limits)
     */
    public function isSuperAdmin(): bool
    {
        return $this->role === 'superadmin';
    }

    /**
     * Check if user is admin
     */
    public function isAdmin(): bool
    {
        return in_array($this->role, ['admin', 'superadmin']);
    }

    /**
     * Get user's active subscription
     */
    public function activeSubscription(): ?Subscription
    {
        return $this->subscriptions()
                    ->active()
                    ->with('plan')
                    ->latest()
                    ->first();
    }

    /**
     * Check if user has an active subscription (or is superadmin)
     */
    public function subscribed(string $type = 'default'): bool
    {
        if ($this->isSuperAdmin()) {
            return true;
        }

        $subscription = $this->subscriptions()
                             ->where('type', $type)
                             ->active()
                             ->first();

        return $subscription !== null;
    }

    /**
     * Get user's current plan (or free plan)
     */
    public function currentPlan(): Plan
    {
        if ($this->isSuperAdmin()) {
            // SuperAdmin gets enterprise-level plan
            return Plan::where('name', 'enterprise')->first() ?? Plan::free();
        }

        $subscription = $this->activeSubscription();
        
        if ($subscription && $subscription->plan) {
            return $subscription->plan;
        }

        // Return assigned plan or free plan
        return $this->plan ?? Plan::free();
    }

    /**
     * Check if user is on trial
     */
    public function onTrial(): bool
    {
        if ($this->trial_ends_at && $this->trial_ends_at->isFuture()) {
            return true;
        }

        $subscription = $this->activeSubscription();
        return $subscription ? $subscription->onTrial() : false;
    }

    /**
     * Check if user is on grace period
     */
    public function onGracePeriod(): bool
    {
        $subscription = $this->activeSubscription();
        return $subscription ? $subscription->onGracePeriod() : false;
    }

    // =========================================================================
    // LIMIT CHECKS
    // =========================================================================

    /**
     * Check if user can add more cameras
     */
    public function canAddCamera(): bool
    {
        if ($this->isSuperAdmin()) {
            return true;
        }

        $plan = $this->currentPlan();
        $currentCount = $this->cameras()->count();

        return $currentCount < $plan->camera_limit;
    }

    /**
     * Get remaining camera slots
     */
    public function remainingCameraSlots(): int
    {
        if ($this->isSuperAdmin()) {
            return 999;
        }

        $plan = $this->currentPlan();
        $currentCount = $this->cameras()->count();

        return max(0, $plan->camera_limit - $currentCount);
    }

    /**
     * Check if user can use a feature
     */
    public function canUseFeature(string $feature): bool
    {
        if ($this->isSuperAdmin()) {
            return true;
        }

        $plan = $this->currentPlan();
        
        // Check direct plan attributes
        $directFeatures = [
            'ai_advanced' => 'ai_advanced',
            'vlm' => 'vlm_access',
            'satellite' => 'satellite_access',
            'cad' => 'cad_access',
            'api' => 'api_access',
            'email_alerts' => 'email_alerts',
            'telegram_alerts' => 'telegram_alerts',
            'recording' => 'recording',
        ];

        if (isset($directFeatures[$feature])) {
            return (bool) $plan->{$directFeatures[$feature]};
        }

        // Check features JSON
        return $plan->hasFeature($feature);
    }

    /**
     * Check if user has reached API call limit for today
     */
    public function hasReachedApiLimit(): bool
    {
        if ($this->isSuperAdmin()) {
            return false;
        }

        $plan = $this->currentPlan();
        
        if ($plan->api_calls_per_day <= 0) {
            return true; // No API access
        }

        $todayUsage = UsageRecord::todayUsage($this->id, 'api_calls');

        return $todayUsage >= $plan->api_calls_per_day;
    }

    /**
     * Check analysis hours limit
     */
    public function hasReachedAnalysisLimit(): bool
    {
        if ($this->isSuperAdmin()) {
            return false;
        }

        $plan = $this->currentPlan();
        $todayMinutes = UsageRecord::todayUsage($this->id, 'analysis_minutes');
        $limitMinutes = $plan->analysis_hours_per_day * 60;

        return $todayMinutes >= $limitMinutes;
    }

    /**
     * Get user's limits summary
     */
    public function getLimitsAttribute(): array
    {
        $plan = $this->currentPlan();

        return [
            'plan_name' => $plan->display_name,
            'is_superadmin' => $this->isSuperAdmin(),
            'cameras' => [
                'limit' => $this->isSuperAdmin() ? '∞' : $plan->camera_limit,
                'used' => $this->cameras()->count(),
                'remaining' => $this->remainingCameraSlots(),
            ],
            'analysis_hours' => [
                'limit' => $this->isSuperAdmin() ? '∞' : $plan->analysis_hours_per_day,
                'used_today' => round(UsageRecord::todayUsage($this->id, 'analysis_minutes') / 60, 1),
            ],
            'api_calls' => [
                'limit' => $this->isSuperAdmin() ? '∞' : $plan->api_calls_per_day,
                'used_today' => UsageRecord::todayUsage($this->id, 'api_calls'),
            ],
            'features' => [
                'ai_advanced' => $this->canUseFeature('ai_advanced'),
                'vlm' => $this->canUseFeature('vlm'),
                'satellite' => $this->canUseFeature('satellite'),
                'cad' => $this->canUseFeature('cad'),
                'recording' => $this->canUseFeature('recording'),
                'email_alerts' => $this->canUseFeature('email_alerts'),
                'telegram_alerts' => $this->canUseFeature('telegram_alerts'),
            ],
        ];
    }
}
