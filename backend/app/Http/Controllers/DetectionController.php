<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use App\Models\Camera;
use App\Models\Detection;

class DetectionController extends Controller
{
    public function index($cameraId)
    {
        $camera = Auth::user()->cameras()->findOrFail($cameraId);
        return response()->json($camera->detections()->latest()->get());
    }

    public function store(Request $request, $cameraId)
    {
        $request->validate([
            'event' => 'required|string',
            'payload' => 'nullable|array'
        ]);

        $camera = Auth::user()->cameras()->findOrFail($cameraId);

        $detection = $camera->detections()->create([
            'event' => $request->event,
            'payload' => $request->payload ?? []
        ]);

        return response()->json($detection, 201);
    }
}
