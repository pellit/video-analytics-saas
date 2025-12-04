<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class SatelliteAnalysis extends Model
{
    use HasFactory;

    protected $table = 'satellite_analyses';

    protected $fillable = [
        'user_id',
        'satellite_zone_id',
        'zone_name',
        'latitude',
        'longitude',
        'change_percent',
        'ssim_score',
        'histogram_correlation',
        'pixel_diff_percent',
        'severity',
        'change_type',
        'vlm_analysis',
        'vlm_model',
        'vlm_prompt',
        'recommendations',
        'change_regions',
        'previous_image_path',
        'current_image_path',
        'heatmap_path',
        'overlay_path',
        'notification_sent',
        'notified_at',
        'notification_priority',
        'metadata',
    ];

    protected $casts = [
        'recommendations' => 'array',
        'change_regions' => 'array',
        'metadata' => 'array',
        'notification_sent' => 'boolean',
        'notified_at' => 'datetime',
        'change_percent' => 'float',
        'ssim_score' => 'float',
        'histogram_correlation' => 'float',
        'pixel_diff_percent' => 'float',
        'latitude' => 'float',
        'longitude' => 'float',
    ];

    protected $appends = ['severity_label', 'change_type_label'];

    // Relationships
    public function user()
    {
        return $this->belongsTo(User::class);
    }

    public function zone()
    {
        return $this->belongsTo(SatelliteZone::class, 'satellite_zone_id');
    }

    public function notifications()
    {
        return $this->morphMany(UserNotification::class, 'source');
    }

    // Accessors
    public function getSeverityLabelAttribute(): string
    {
        return match($this->severity) {
            'minimal' => 'Mínimo',
            'low' => 'Bajo',
            'moderate' => 'Moderado',
            'significant' => 'Significativo',
            'critical' => 'Crítico',
            default => $this->severity,
        };
    }

    public function getChangeTypeLabelAttribute(): string
    {
        return match($this->change_type) {
            'construction' => 'Construcción',
            'vegetation' => 'Vegetación',
            'water' => 'Agua/Inundación',
            'deforestation' => 'Deforestación',
            'urban_expansion' => 'Expansión Urbana',
            'agricultural' => 'Agrícola',
            'unknown' => 'No Determinado',
            default => $this->change_type,
        };
    }

    // Scopes
    public function scopeForUser($query, $userId)
    {
        return $query->where('user_id', $userId);
    }

    public function scopeForZone($query, $zoneId)
    {
        return $query->where('satellite_zone_id', $zoneId);
    }

    public function scopeBySeverity($query, $severity)
    {
        return $query->where('severity', $severity);
    }

    public function scopeSignificantChanges($query)
    {
        return $query->whereIn('severity', ['significant', 'critical']);
    }

    public function scopeRecent($query, $days = 30)
    {
        return $query->where('created_at', '>=', now()->subDays($days));
    }

    // Methods
    public function shouldNotify(): bool
    {
        return in_array($this->severity, ['significant', 'critical']) || 
               $this->change_percent > 20;
    }

    public function getNotificationPriority(): string
    {
        if ($this->severity === 'critical') return 'critical';
        if ($this->severity === 'significant') return 'high';
        if ($this->change_percent > 20) return 'medium';
        return 'low';
    }

    public function markNotified(): void
    {
        $this->update([
            'notification_sent' => true,
            'notified_at' => now(),
            'notification_priority' => $this->getNotificationPriority(),
        ]);
    }
}
