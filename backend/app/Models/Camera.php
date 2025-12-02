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
        'detection_enabled',
        'detection_model',
        'detection_classes',
        'face_recognition_enabled',
        'depth_enabled',
        'bev_enabled',
        'roi_settings',
        'roi_points'
    ];

    protected $casts = [
        'detection_enabled' => 'boolean',
        'detection_classes' => 'array',
        'face_recognition_enabled' => 'boolean',
        'depth_enabled' => 'boolean',
        'bev_enabled' => 'boolean',
        'roi_settings' => 'array',
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
}
