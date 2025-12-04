<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class SatelliteZone extends Model
{
    use HasFactory;

    protected $fillable = [
        'user_id',
        'name',
        'description',
        'latitude',
        'longitude',
        'radius_km',
        'frequency',
        'preferred_time',
        'max_cloud_cover',
        'is_active',
        'last_checked_at',
        'last_image_at',
        'last_image_path',
        'last_analysis',
        'alert_rules',
    ];

    protected $casts = [
        'latitude' => 'decimal:7',
        'longitude' => 'decimal:7',
        'radius_km' => 'decimal:2',
        'max_cloud_cover' => 'integer',
        'is_active' => 'boolean',
        'last_checked_at' => 'datetime',
        'last_image_at' => 'datetime',
        'last_analysis' => 'array',
        'alert_rules' => 'array',
    ];

    /**
     * Frecuencias de actualización disponibles
     */
    public const FREQUENCIES = [
        'hourly' => 'Cada hora',
        'daily' => 'Diario',
        'weekly' => 'Semanal',
        'manual' => 'Manual',
    ];

    /**
     * Usuario propietario de la zona
     */
    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }

    /**
     * Imágenes satelitales de esta zona
     */
    public function images(): HasMany
    {
        return $this->hasMany(SatelliteImage::class)->orderByDesc('captured_at');
    }

    /**
     * Alertas generadas para esta zona
     */
    public function alerts(): HasMany
    {
        return $this->hasMany(SatelliteAlert::class)->orderByDesc('created_at');
    }

    /**
     * Última imagen de la zona
     */
    public function latestImage()
    {
        return $this->hasOne(SatelliteImage::class)->latestOfMany('captured_at');
    }

    /**
     * Alertas no leídas
     */
    public function unreadAlerts(): HasMany
    {
        return $this->alerts()->where('is_read', false);
    }

    /**
     * Verificar si necesita actualización según frecuencia
     */
    public function needsUpdate(): bool
    {
        if (!$this->is_active || $this->frequency === 'manual') {
            return false;
        }

        if (!$this->last_checked_at) {
            return true;
        }

        $intervals = [
            'hourly' => 60,      // minutos
            'daily' => 1440,    // 24 horas
            'weekly' => 10080,  // 7 días
        ];

        $interval = $intervals[$this->frequency] ?? 1440;
        
        return $this->last_checked_at->addMinutes($interval)->isPast();
    }

    /**
     * Obtener coordenadas formateadas
     */
    public function getCoordinatesAttribute(): string
    {
        $latDir = $this->latitude >= 0 ? 'N' : 'S';
        $lonDir = $this->longitude >= 0 ? 'E' : 'W';
        
        return sprintf(
            "%.4f°%s, %.4f°%s",
            abs($this->latitude),
            $latDir,
            abs($this->longitude),
            $lonDir
        );
    }

    /**
     * Scope para zonas activas
     */
    public function scopeActive($query)
    {
        return $query->where('is_active', true);
    }

    /**
     * Scope para zonas que necesitan actualización
     */
    public function scopeNeedsUpdate($query)
    {
        return $query->active()
            ->where('frequency', '!=', 'manual')
            ->where(function ($q) {
                $q->whereNull('last_checked_at')
                    ->orWhere('last_checked_at', '<', now()->subHour()); // Mínimo 1 hora
            });
    }
}
