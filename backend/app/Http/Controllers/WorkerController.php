<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Redis;
use App\Models\Detection;
use App\Models\Alert;
use App\Models\AlertLog;

class WorkerController extends Controller
{
    public function postDetection(Request $request)
    {
        // Simple worker auth
        $workerKey = $request->header('X-WORKER-KEY');
        $expectedKey = $_SERVER['WORKER_API_KEY'] ?? getenv('WORKER_API_KEY') ?? env('WORKER_API_KEY');
        if (!$workerKey || ($expectedKey && $workerKey !== $expectedKey)) {
            return response()->json(['message' => 'Unauthorized'], 401);
        }

        $data = $request->validate([
            'camera_id' => 'required|integer|exists:cameras,id',
            'event' => 'required|string',
            'payload' => 'nullable|array'
        ]);

        // Save detection
        $d = Detection::create([
            'camera_id' => $data['camera_id'],
            'event' => $data['event'],
            'payload' => $data['payload'] ?? []
        ]);

        // Evaluate alert rules
        $camera = $d->camera;
        // Get relevant rules: user or camera-specific
        $rules = Alert::where(function ($q) use ($camera) {
            $q->where('camera_id', $camera->id)->orWhereNull('camera_id');
        })->where('event', $d->event)->where('enabled', true)->get();

        foreach ($rules as $rule) {
            $match = true;
            // Threshold handling (if present in payload)
            if ($rule->threshold) {
                $score = $d->payload['score'] ?? 0;
                $match = floatval($score) >= floatval($rule->threshold);
            }
            if ($match) {
                $log = AlertLog::create([
                    'alert_id' => $rule->id,
                    'detection_id' => $d->id,
                    'payload' => $d->payload
                ]);

                // Publish notification to Redis alerts channel
                Redis::publish('alerts', json_encode([
                    'user_id' => $rule->user_id,
                    'alert_id' => $rule->id,
                    'camera_id' => $camera->id,
                    'detection_id' => $d->id,
                    'event' => $d->event,
                    'payload' => $d->payload,
                ]));
            }
        }

        return response()->json($d, 201);
    }
}
