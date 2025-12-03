<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class FaceDetection extends Model
{
    protected $fillable = [
        'camera_id',
        'known_face_id',
        'embedding',
        'face_image_path',
        'confidence',
        'similarity_score',
        'bbox',
        'identified',
        'metadata',
    ];

    protected $casts = [
        'embedding' => 'array',
        'bbox' => 'array',
        'metadata' => 'array',
        'identified' => 'boolean',
        'confidence' => 'float',
        'similarity_score' => 'float',
    ];

    protected $hidden = [
        'embedding',
    ];

    /**
     * Get the camera where this face was detected.
     */
    public function camera()
    {
        return $this->belongsTo(Camera::class);
    }

    /**
     * Get the known face if identified.
     */
    public function knownFace()
    {
        return $this->belongsTo(KnownFace::class);
    }

    /**
     * Scope for unidentified faces.
     */
    public function scopeUnidentified($query)
    {
        return $query->where('identified', false);
    }

    /**
     * Scope for identified faces.
     */
    public function scopeIdentified($query)
    {
        return $query->where('identified', true);
    }

    /**
     * Get recent detections for a camera.
     */
    public function scopeForCamera($query, $cameraId)
    {
        return $query->where('camera_id', $cameraId);
    }

    /**
     * Get recent unidentified faces (for labeling UI).
     */
    public function scopeRecentUnidentified($query, $limit = 20)
    {
        return $query->unidentified()
            ->orderBy('created_at', 'desc')
            ->limit($limit);
    }
}
