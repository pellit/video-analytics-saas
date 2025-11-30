<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class AlertLog extends Model
{
    use HasFactory;

    protected $fillable = ['alert_id','detection_id','payload'];

    protected $casts = ['payload' => 'array'];

    public function alert()
    {
        return $this->belongsTo(Alert::class);
    }

    public function detection()
    {
        return $this->belongsTo(Detection::class);
    }
}
