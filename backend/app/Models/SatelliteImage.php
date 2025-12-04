<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class SatelliteImage extends Model
{
    use HasFactory;

    protected $fillable = [
        'satellite_zone_id',
        'image_path',
        'thumbnail_path',
        'captured_at',
        'cloud_cover',
        'satellite_source',
        'detections',
        'ai_description',
        'changes_detected',
        'status',
        'error_message',
    ];

    protected $casts = [
        'captured_at' => 'datetime',
        'cloud_cover' => 'integer',
        'detections' => 'array',
        'changes_detected' => 'array',
    ];

    /**
     * Estados posibles de la imagen
     */
    public const STATUSES = [
        'pending' => 'Pendiente',
        'processing' => 'Procesando',
        'completed' => 'Completado',
        'failed' => 'Fallido',
    ];

    /**
     * Zona satelital a la que pertenece
     */
    public function zone(): BelongsTo
    {
        return $this->belongsTo(SatelliteZone::class, 'satellite_zone_id');
    }

    /**
     * Alertas generadas por esta imagen
     */
    public function alerts(): HasMany
    {
        return $this->hasMany(SatelliteAlert::class);
    }

    /**
     * URL pública de la imagen
     */
    public function getImageUrlAttribute(): ?string
    {
        if (!$this->image_path) {
            return null;
        }
        
        // Si es una URL completa (S3, etc)
        if (str_starts_with($this->image_path, 'http')) {
            return $this->image_path;
        }
        
        // Ruta local
        return asset('storage/' . $this->image_path);
    }

    /**
     * URL del thumbnail
     */
    public function getThumbnailUrlAttribute(): ?string
    {
        if (!$this->thumbnail_path) {
            return $this->image_url; // Usar imagen original si no hay thumbnail
        }
        
        if (str_starts_with($this->thumbnail_path, 'http')) {
            return $this->thumbnail_path;
        }
        
        return asset('storage/' . $this->thumbnail_path);
    }

    /**
     * Resumen de detecciones
     */
    public function getDetectionsSummaryAttribute(): array
    {
        if (!$this->detections) {
            return [];
        }

        $summary = [];
        foreach ($this->detections as $detection) {
            $class = $detection['class'] ?? 'unknown';
            $summary[$class] = ($summary[$class] ?? 0) + 1;
        }
        
        return $summary;
    }

    /**
     * Scope para imágenes completadas
     */
    public function scopeCompleted($query)
    {
        return $query->where('status', 'completed');
    }

    /**
     * Scope para imágenes pendientes de procesamiento
     */
    public function scopePending($query)
    {
        return $query->where('status', 'pending');
    }
}
