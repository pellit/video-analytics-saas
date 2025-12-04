<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class Camera extends Model
{
    use HasFactory;

    // Campos que permitimos guardar masivamente
    protected $fillable = [
        'user_id',
        'name',
        'url',
        'status',
        // Perfil de cámara
        'camera_type',
        'camera_behavior',
        'location_type',
        'primary_goal',
        // Configuración de detección
        'detection_enabled',
        'detection_model',
        'detection_classes',
        'confidence_threshold',
        'detection_interval_ms',
        'analysis_fps',
        'show_analysis_overlay',
        // Funcionalidades
        'face_recognition_enabled',
        'alert_on_unknown_face',
        'depth_enabled',
        'bev_enabled',
        'tracking',
        'count_objects',
        'detect_loitering',
        'loitering_threshold_seconds',
        // ROI y zonas
        'roi_settings',
        'roi_points',
        // Análisis de escena
        'scene_analysis',
        'scene_analyzed_at',
        'recommended_settings',
        'setup_completed'
    ];

    protected $casts = [
        'detection_enabled' => 'boolean',
        'detection_classes' => 'array',
        'face_recognition_enabled' => 'boolean',
        'alert_on_unknown_face' => 'boolean',
        'depth_enabled' => 'boolean',
        'bev_enabled' => 'boolean',
        'tracking' => 'boolean',
        'count_objects' => 'boolean',
        'detect_loitering' => 'boolean',
        'setup_completed' => 'boolean',
        'show_analysis_overlay' => 'boolean',
        'confidence_threshold' => 'float',
        'detection_interval_ms' => 'integer',
        'analysis_fps' => 'integer',
        'loitering_threshold_seconds' => 'integer',
        'roi_settings' => 'array',
        'scene_analysis' => 'array',
        'recommended_settings' => 'array',
        'scene_analyzed_at' => 'datetime',
    ];

    /**
     * Relación: Una cámara pertenece a un Usuario.
     */
    public function user()
    {
        return $this->belongsTo(User::class);
    }

    public function detections()
    {
        return $this->hasMany(Detection::class);
    }

    public function alerts()
    {
        return $this->hasMany(Alert::class);
    }

    /**
     * Genera configuración recomendada basada en el perfil
     */
    public function generateRecommendedSettings(): array
    {
        $settings = [
            'detection_classes' => ['person'],
            'confidence_threshold' => 0.5,
            'detection_interval_ms' => 500,
            'tracking' => true,
        ];

        // Ajustar según tipo de cámara
        switch ($this->camera_type) {
            case 'security':
                $settings['detection_classes'] = ['person', 'car', 'truck', 'motorcycle'];
                $settings['face_recognition_enabled'] = true;
                $settings['detect_loitering'] = true;
                $settings['alert_on_unknown_face'] = true;
                break;
            case 'traffic':
                $settings['detection_classes'] = ['car', 'truck', 'bus', 'motorcycle', 'bicycle', 'person'];
                $settings['count_objects'] = true;
                $settings['tracking'] = true;
                break;
            case 'retail':
                $settings['detection_classes'] = ['person', 'handbag', 'backpack', 'suitcase'];
                $settings['count_objects'] = true;
                $settings['detect_loitering'] = true;
                break;
            case 'industrial':
                $settings['detection_classes'] = ['person', 'truck', 'forklift'];
                $settings['confidence_threshold'] = 0.6;
                break;
        }

        // Ajustar según objetivo
        switch ($this->primary_goal) {
            case 'intrusion':
                $settings['alert_on_unknown_face'] = true;
                $settings['confidence_threshold'] = 0.4; // Más sensible
                break;
            case 'counting':
                $settings['count_objects'] = true;
                $settings['tracking'] = true;
                break;
            case 'recognition':
                $settings['face_recognition_enabled'] = true;
                break;
            case 'behavior':
                $settings['detect_loitering'] = true;
                $settings['tracking'] = true;
                break;
        }

        // Ajustar según ubicación
        if (in_array($this->location_type, ['entrance', 'parking'])) {
            $settings['detection_classes'] = array_unique(array_merge(
                $settings['detection_classes'] ?? [],
                ['person', 'car', 'truck']
            ));
        }

        // Ajustar según comportamiento de cámara
        if ($this->camera_behavior === 'ptz' || $this->camera_behavior === 'patrol') {
            $settings['detection_interval_ms'] = 1000; // Menos frecuente porque la imagen cambia
        }

        return $settings;
    }
}
