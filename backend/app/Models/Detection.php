<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class Detection extends Model
{
    use HasFactory;

    protected $fillable = ['camera_id', 'event', 'payload'];

    protected $casts = [
        'payload' => 'array'
    ];

    public function camera()
    {
        return $this->belongsTo(Camera::class);
    }
}
