<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class ApiUsageDaily extends Model
{
    protected $table = 'api_usage_daily';
    
    protected $fillable = [
        'api_key_id',
        'date',
        'request_count',
        'frames_processed',
        'detections_count',
        'bytes_received',
        'errors_count',
        'avg_response_time_ms',
    ];

    protected $casts = [
        'date' => 'date',
    ];

    public function apiKey()
    {
        return $this->belongsTo(ApiKey::class);
    }

    /**
     * Get or create today's stats record for an API key
     */
    public static function getOrCreateToday(int $apiKeyId): self
    {
        return self::firstOrCreate(
            ['api_key_id' => $apiKeyId, 'date' => today()],
            [
                'request_count' => 0,
                'frames_processed' => 0,
                'detections_count' => 0,
                'bytes_received' => 0,
                'errors_count' => 0,
                'avg_response_time_ms' => 0,
            ]
        );
    }

    /**
     * Increment stats for this record
     */
    public function incrementStats(array $data): void
    {
        $this->increment('request_count');
        
        if (isset($data['frames'])) {
            $this->increment('frames_processed', $data['frames']);
        }
        if (isset($data['detections'])) {
            $this->increment('detections_count', $data['detections']);
        }
        if (isset($data['bytes'])) {
            $this->increment('bytes_received', $data['bytes']);
        }
        if (isset($data['error']) && $data['error']) {
            $this->increment('errors_count');
        }
        if (isset($data['response_time_ms'])) {
            // Rolling average
            $newAvg = (($this->avg_response_time_ms * ($this->request_count - 1)) + $data['response_time_ms']) / $this->request_count;
            $this->update(['avg_response_time_ms' => (int) $newAvg]);
        }
    }
}
