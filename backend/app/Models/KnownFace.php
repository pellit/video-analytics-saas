<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class KnownFace extends Model
{
    protected $fillable = [
        'user_id',
        'name',
        'label',
        'embedding',
        'face_image_path',
        'metadata',
        'detection_count',
        'last_seen_at',
    ];

    protected $casts = [
        'embedding' => 'array',
        'metadata' => 'array',
        'last_seen_at' => 'datetime',
    ];

    protected $hidden = [
        'embedding', // Hide large embedding array in API responses by default
    ];

    /**
     * Get the user that owns this known face.
     */
    public function user()
    {
        return $this->belongsTo(User::class);
    }

    /**
     * Get face detection logs for this known face.
     */
    public function detections()
    {
        return $this->hasMany(FaceDetection::class);
    }

    /**
     * Scope to get faces for a specific user.
     */
    public function scopeForUser($query, $userId)
    {
        return $query->where('user_id', $userId);
    }

    /**
     * Calculate cosine similarity with another embedding.
     */
    public function cosineSimilarity(array $otherEmbedding): float
    {
        $embedding = $this->embedding;
        
        if (!$embedding || !$otherEmbedding || count($embedding) !== count($otherEmbedding)) {
            return 0.0;
        }

        $dotProduct = 0;
        $normA = 0;
        $normB = 0;

        for ($i = 0; $i < count($embedding); $i++) {
            $dotProduct += $embedding[$i] * $otherEmbedding[$i];
            $normA += $embedding[$i] * $embedding[$i];
            $normB += $otherEmbedding[$i] * $otherEmbedding[$i];
        }

        $normA = sqrt($normA);
        $normB = sqrt($normB);

        if ($normA == 0 || $normB == 0) {
            return 0.0;
        }

        return $dotProduct / ($normA * $normB);
    }

    /**
     * Find the best match from a list of known faces.
     */
    public static function findBestMatch(array $embedding, $userId, float $threshold = 0.6): ?array
    {
        $knownFaces = self::forUser($userId)->get();
        $bestMatch = null;
        $bestSimilarity = $threshold;

        foreach ($knownFaces as $face) {
            $similarity = $face->cosineSimilarity($embedding);
            if ($similarity > $bestSimilarity) {
                $bestSimilarity = $similarity;
                $bestMatch = [
                    'face' => $face,
                    'similarity' => $similarity,
                ];
            }
        }

        return $bestMatch;
    }
}
