<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Redis;

class CameraController extends Controller
{
    public function start(Request $request)
    {
        // Validamos que nos envíen ID y URL
        $request->validate([
            'id' => 'required',
            'url' => 'required|url',
            'name' => 'nullable|string'
        ]);

        // Construimos el mensaje para el Worker de Python
        $message = json_encode([
            'action' => 'START',
            'camera_id' => $request->id,
            'url' => $request->url
        ]);

        // Publicamos en el canal 'video_control' de Redis
        Redis::publish('video_control', $message);

        return response()->json([
            'status' => 'success',
            'message' => "Análisis iniciado en cámara {$request->id}"
        ]);
    }

    public function stop(Request $request)
    {
        $message = json_encode([
            'action' => 'STOP',
            'camera_id' => $request->id ?? 1
        ]);

        Redis::publish('video_control', $message);

        return response()->json([
            'status' => 'success',
            'message' => 'Análisis detenido'
        ]);
    }
}