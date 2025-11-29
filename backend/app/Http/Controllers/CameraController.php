<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Redis;

class CameraController extends Controller
{

// Listar cámaras del usuario
    public function index() {
        return Auth::user()->cameras;
    }

    // Guardar nueva cámara
    public function store(Request $request) {
        $request->validate(['name' => 'required', 'url' => 'required']);

        $camera = Auth::user()->cameras()->create([
            'name' => $request->name,
            'url' => $request->url
        ]);

        return $camera;
    }

    // Iniciar Análisis (Tu código anterior, mejorado)
    public function start(Request $request) {
        // ... validaciones ...

        // Publicar en Redis (Igual que antes)
        $message = json_encode([
            'action' => 'START',
            'camera_id' => $request->id,
            'url' => $request->url
        ]);
        Redis::publish('video_control', $message);

        return response()->json(['status' => 'success']);
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