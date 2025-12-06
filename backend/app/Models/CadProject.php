<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class CadProject extends Model
{
    use HasFactory;

    protected $fillable = [
        'user_id',
        'name',
        'description',
        'project_type',
        'original_filename',
        'file_path',
        'file_type',
        'file_size',
        'status',
        'progress',
        'current_step',
        'error_message',
        'render_image_path',
        'render_thumbnail_path',
        'analysis_general',
        'analysis_rooms',
        'analysis_safety',
        'analysis_structural',
        'analysis_dimensions',
        'analysis_materials',
        'analysis_compliance',
        'metadata',
        'tags',
        'processing_started_at',
        'processing_completed_at',
        'processing_duration_seconds',
    ];

    protected $casts = [
        'analysis_general' => 'array',
        'analysis_rooms' => 'array',
        'analysis_safety' => 'array',
        'analysis_structural' => 'array',
        'analysis_dimensions' => 'array',
        'analysis_materials' => 'array',
        'analysis_compliance' => 'array',
        'metadata' => 'array',
        'tags' => 'array',
        'processing_started_at' => 'datetime',
        'processing_completed_at' => 'datetime',
        'file_size' => 'integer',
        'progress' => 'integer',
        'processing_duration_seconds' => 'integer',
    ];

    /**
     * Project types available
     */
    const PROJECT_TYPES = [
        'architecture' => 'Arquitectura',
        'engineering' => 'Ingeniería Civil',
        'electrical' => 'Instalaciones Eléctricas',
        'plumbing' => 'Instalaciones Sanitarias',
        'structural' => 'Estructural',
        'hvac' => 'Climatización (HVAC)',
        'landscape' => 'Paisajismo',
        'interior' => 'Diseño Interior',
        'urban' => 'Urbanismo',
        'other' => 'Otro',
    ];

    /**
     * Supported file types
     */
    const FILE_TYPES = ['dxf', 'dwg', 'pdf'];

    /**
     * Status labels
     */
    const STATUS_LABELS = [
        'pending' => 'Pendiente',
        'rendering' => 'Renderizando',
        'analyzing' => 'Analizando',
        'completed' => 'Completado',
        'error' => 'Error',
    ];

    /**
     * Get the user that owns the project.
     */
    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }

    /**
     * Get all analysis results combined
     */
    public function getFullAnalysisAttribute(): array
    {
        return [
            'general' => $this->analysis_general,
            'rooms' => $this->analysis_rooms,
            'safety' => $this->analysis_safety,
            'structural' => $this->analysis_structural,
            'dimensions' => $this->analysis_dimensions,
            'materials' => $this->analysis_materials,
            'compliance' => $this->analysis_compliance,
        ];
    }

    /**
     * Check if project is still processing
     */
    public function isProcessing(): bool
    {
        return in_array($this->status, ['pending', 'rendering', 'analyzing']);
    }

    /**
     * Check if project completed successfully
     */
    public function isCompleted(): bool
    {
        return $this->status === 'completed';
    }

    /**
     * Check if project has errors
     */
    public function hasError(): bool
    {
        return $this->status === 'error';
    }

    /**
     * Get project type label
     */
    public function getProjectTypeLabelAttribute(): string
    {
        return self::PROJECT_TYPES[$this->project_type] ?? $this->project_type;
    }

    /**
     * Get status label
     */
    public function getStatusLabelAttribute(): string
    {
        return self::STATUS_LABELS[$this->status] ?? $this->status;
    }

    /**
     * Get render image URL
     */
    public function getRenderImageUrlAttribute(): ?string
    {
        if (!$this->render_image_path) {
            return null;
        }
        return asset('storage/' . $this->render_image_path);
    }

    /**
     * Get thumbnail URL
     */
    public function getThumbnailUrlAttribute(): ?string
    {
        if (!$this->render_thumbnail_path) {
            return $this->render_image_url; // Fallback to full image
        }
        return asset('storage/' . $this->render_thumbnail_path);
    }

    /**
     * Scope for user's projects
     */
    public function scopeForUser($query, $userId)
    {
        return $query->where('user_id', $userId);
    }

    /**
     * Scope for completed projects
     */
    public function scopeCompleted($query)
    {
        return $query->where('status', 'completed');
    }

    /**
     * Scope for processing projects
     */
    public function scopeProcessing($query)
    {
        return $query->whereIn('status', ['pending', 'rendering', 'analyzing']);
    }

    /**
     * Scope by project type
     */
    public function scopeOfType($query, $type)
    {
        return $query->where('project_type', $type);
    }
}
