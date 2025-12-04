<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class SatelliteAlert extends Model
{
    use HasFactory;

    protected $fillable = [
        'satellite_zone_id',
        'satellite_image_id',
        'alert_type',
        'severity',
        'message',
        'details',
        'is_read',
        'is_acknowledged',
        'acknowledged_at',
    ];

    protected $casts = [
        'details' => 'array',
        'is_read' => 'boolean',
        'is_acknowledged' => 'boolean',
        'acknowledged_at' => 'datetime',
    ];

    /**
     * Tipos de alerta
     */
    public const ALERT_TYPES = [
        'change_detected' => 'Cambio detectado',
        'object_detected' => 'Objeto detectado',
        'threshold_exceeded' => 'Umbral excedido',
        'new_construction' => 'Nueva construcción',
        'vegetation_change' => 'Cambio vegetación',
        'water_level' => 'Nivel de agua',
    ];

    /**
     * Niveles de severidad
     */
    public const SEVERITIES = [
        'info' => ['label' => 'Info', 'color' => 'blue'],
        'warning' => ['label' => 'Advertencia', 'color' => 'yellow'],
        'critical' => ['label' => 'Crítico', 'color' => 'red'],
    ];

    /**
     * Zona satelital relacionada
     */
    public function zone(): BelongsTo
    {
        return $this->belongsTo(SatelliteZone::class, 'satellite_zone_id');
    }

    /**
     * Imagen que generó la alerta
     */
    public function image(): BelongsTo
    {
        return $this->belongsTo(SatelliteImage::class, 'satellite_image_id');
    }

    /**
     * Marcar como leída
     */
    public function markAsRead(): void
    {
        $this->update(['is_read' => true]);
    }

    /**
     * Marcar como reconocida
     */
    public function acknowledge(): void
    {
        $this->update([
            'is_acknowledged' => true,
            'acknowledged_at' => now(),
        ]);
    }

    /**
     * Scope para alertas no leídas
     */
    public function scopeUnread($query)
    {
        return $query->where('is_read', false);
    }

    /**
     * Scope para alertas críticas
     */
    public function scopeCritical($query)
    {
        return $query->where('severity', 'critical');
    }

    /**
     * Scope para alertas recientes (últimas 24h)
     */
    public function scopeRecent($query)
    {
        return $query->where('created_at', '>=', now()->subDay());
    }
}
