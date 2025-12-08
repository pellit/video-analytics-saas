<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class Subscription extends Model
{
    use HasFactory;

    protected $fillable = [
        'user_id',
        'plan_id',
        'stripe_id',
        'stripe_status',
        'type',
        'trial_ends_at',
        'ends_at',
        'current_period_start',
        'current_period_end',
        'cancel_at_period_end',
    ];

    protected $casts = [
        'trial_ends_at' => 'datetime',
        'ends_at' => 'datetime',
        'current_period_start' => 'datetime',
        'current_period_end' => 'datetime',
        'cancel_at_period_end' => 'boolean',
    ];

    /**
     * Get the user that owns the subscription
     */
    public function user()
    {
        return $this->belongsTo(User::class);
    }

    /**
     * Get the plan for this subscription
     */
    public function plan()
    {
        return $this->belongsTo(Plan::class);
    }

    /**
     * Get subscription items
     */
    public function items()
    {
        return $this->hasMany(SubscriptionItem::class);
    }

    /**
     * Check if subscription is active
     */
    public function isActive(): bool
    {
        // Stripe statuses that mean "active"
        $activeStatuses = ['active', 'trialing'];
        
        if (in_array($this->stripe_status, $activeStatuses)) {
            return true;
        }

        // Si no tiene stripe_status, verificar ends_at
        if (is_null($this->stripe_status)) {
            return is_null($this->ends_at) || $this->ends_at->isFuture();
        }

        return false;
    }

    /**
     * Check if subscription is on trial
     */
    public function onTrial(): bool
    {
        return $this->stripe_status === 'trialing' || 
               ($this->trial_ends_at && $this->trial_ends_at->isFuture());
    }

    /**
     * Check if subscription is canceled
     */
    public function canceled(): bool
    {
        return $this->stripe_status === 'canceled' || 
               ($this->ends_at && $this->ends_at->isPast());
    }

    /**
     * Check if subscription is on grace period
     */
    public function onGracePeriod(): bool
    {
        return $this->cancel_at_period_end && 
               $this->current_period_end && 
               $this->current_period_end->isFuture();
    }

    /**
     * Scope for active subscriptions
     */
    public function scopeActive($query)
    {
        return $query->whereIn('stripe_status', ['active', 'trialing'])
                     ->orWhere(function ($q) {
                         $q->whereNull('stripe_status')
                           ->where(function ($q2) {
                               $q2->whereNull('ends_at')
                                  ->orWhere('ends_at', '>', now());
                           });
                     });
    }
}
