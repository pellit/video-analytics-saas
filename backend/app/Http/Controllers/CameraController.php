<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Redis;
use Illuminate\Support\Facades\Auth;

use App\Models\Camera;

class CameraController extends Controller
{

// Listar cámaras del usuario
    public function index() {
        $cameras = Auth::user()->cameras()->get();
        return response()->json($cameras);
    }

    // Guardar nueva cámara
    public function store(Request $request) {
        $validated = $request->validate(['name' => 'required', 'url' => 'required']);

        // Crear la cámara asociada al usuario autenticado
        $camera = Auth::user()->cameras()->create([
            'name' => $validated['name'],
            'url' => $validated['url']
        ]);

        return response()->json($camera, 201);
    }

    // Update camera settings (name/url/detection options)
    public function update(Request $request, $id) {
        $camera = Auth::user()->cameras()->findOrFail($id);
        $validated = $request->validate([
            'name' => 'sometimes|string',
            'url' => 'sometimes|string',
            'detection_enabled' => 'sometimes|boolean',
            'detection_model' => 'sometimes|string|nullable',
            'tracking' => 'sometimes|boolean',
        ]);
        $camera->update($validated);
        return response()->json($camera);
    }

    // Iniciar Análisis (Tu código anterior, mejorado)
    public function start(Request $request) {
        $request->validate(['id' => 'required|integer']);

        // Verificar que la cámara pertenezca al usuario autenticado
        $camera = Auth::user()->cameras()->findOrFail($request->id);

        // Publicar en Redis
        $message = json_encode([
            'action' => 'START',
            'camera_id' => $camera->id,
            'url' => $camera->url
        ]);
        Redis::publish('video_control', $message);

        return response()->json(['status' => 'success']);
    }

    public function stop(Request $request)
    {
        $request->validate(['id' => 'required|integer']);
        $camera = Auth::user()->cameras()->findOrFail($request->id);

        $message = json_encode([
            'action' => 'STOP',
            'camera_id' => $camera->id
        ]);

        Redis::publish('video_control', $message);

        return response()->json([
            'status' => 'success',
            'message' => 'Análisis detenido'
        ]);
    }
}