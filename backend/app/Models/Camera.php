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
        'roi_points', // Opcional, por si lo usamos en el futuro
        'depth_enabled',
        'bev_enabled'
    ];

    protected $casts = [
        'depth_enabled' => 'boolean',
        'bev_enabled' => 'boolean',
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

