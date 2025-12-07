<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Redis;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Http;

use App\Models\Camera;

class CameraController extends Controller
{
    // URL del worker Go (se puede configurar via env)
    private function getGoWorkerUrl(): string
    {
        return env('GO_WORKER_URL', 'https://worker-go-dev.pellit.com.ar');
    }

    // Verificar si el modelo es para el worker Go
    private function isGoModel(string $model): bool
    {
        return str_starts_with($model, 'go-');
    }

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
            'detection_classes' => 'sometimes|array',
            'face_recognition_enabled' => 'sometimes|boolean',
            'face_analysis_fps' => 'sometimes|integer|min:1|max:30',
            'depth_enabled' => 'sometimes|boolean',
            'bev_enabled' => 'sometimes|boolean',
            'tracking' => 'sometimes|boolean',
            'analysis_fps' => 'sometimes|integer|min:1|max:60',
            'show_analysis_overlay' => 'sometimes|boolean',
            'confidence_threshold' => 'sometimes|numeric|min:0.1|max:1.0',
        ]);
        $camera->update($validated);
        return response()->json($camera);
    }

    // Iniciar Análisis (Tu código anterior, mejorado)
    public function start(Request $request) {
        $request->validate(['id' => 'required|integer']);

        // Verificar que la cámara pertenezca al usuario autenticado
        $camera = Auth::user()->cameras()->findOrFail($request->id);
        
        $model = $camera->detection_model ?? 'yolov8n';
        
        // Si es modelo Go, enviar al worker Go via HTTP
        if ($this->isGoModel($model)) {
            return $this->startGoWorker($camera);
        }

        // Worker Python via Redis
        $message = json_encode([
            'action' => 'START',
            'camera_id' => $camera->id,
            'url' => $camera->url,
            'model' => $model,
            'detection_classes' => $camera->detection_classes,
            'face_recognition_enabled' => $camera->face_recognition_enabled,
            'face_analysis_fps' => $camera->face_analysis_fps ?? 5,
            'depth_enabled' => $camera->depth_enabled,
            'bev_enabled' => $camera->bev_enabled,
            'tracking' => $camera->tracking ?? false,
            'analysis_fps' => $camera->analysis_fps ?? 5,
            'show_analysis_overlay' => $camera->show_analysis_overlay ?? true,
            'confidence_threshold' => $camera->confidence_threshold ?? 0.5,
        ]);
        Redis::publish('video_control', $message);

        return response()->json(['status' => 'success', 'worker' => 'python']);
    }

    // Iniciar procesamiento en Go Worker
    private function startGoWorker(Camera $camera)
    {
        try {
            $response = Http::timeout(10)->post($this->getGoWorkerUrl() . '/camera/' . $camera->id . '/start', [
                'rtsp_url' => $camera->url,
                'model_id' => 'yolov8n',  // Go worker solo soporta yolov8n
                'threshold' => $camera->confidence_threshold ?? 0.5,
            ]);

            if ($response->successful()) {
                return response()->json([
                    'status' => 'success',
                    'worker' => 'go',
                    'worker_response' => $response->json(),
                ]);
            }

            return response()->json([
                'status' => 'error',
                'message' => 'Go worker error: ' . $response->body(),
            ], 500);

        } catch (\Exception $e) {
            return response()->json([
                'status' => 'error',
                'message' => 'Failed to connect to Go worker: ' . $e->getMessage(),
            ], 500);
        }
    }

    public function stop(Request $request)
    {
        $request->validate(['id' => 'required|integer']);
        $camera = Auth::user()->cameras()->findOrFail($request->id);
        
        $model = $camera->detection_model ?? 'yolov8n';

        // Si es modelo Go, detener en worker Go
        if ($this->isGoModel($model)) {
            return $this->stopGoWorker($camera);
        }

        // Worker Python via Redis
        $message = json_encode([
            'action' => 'STOP',
            'camera_id' => $camera->id
        ]);

        Redis::publish('video_control', $message);

        return response()->json([
            'status' => 'success',
            'message' => 'Análisis detenido',
            'worker' => 'python'
        ]);
    }

    // Detener procesamiento en Go Worker
    private function stopGoWorker(Camera $camera)
    {
        try {
            $response = Http::timeout(10)->post($this->getGoWorkerUrl() . '/camera/' . $camera->id . '/stop');

            if ($response->successful()) {
                return response()->json([
                    'status' => 'success',
                    'message' => 'Análisis detenido',
                    'worker' => 'go',
                ]);
            }

            return response()->json([
                'status' => 'error',
                'message' => 'Go worker error: ' . $response->body(),
            ], 500);

        } catch (\Exception $e) {
            return response()->json([
                'status' => 'error',
                'message' => 'Failed to connect to Go worker: ' . $e->getMessage(),
            ], 500);
        }
    }

    // Eliminar cámara
    public function destroy($id)
    {
        $camera = Auth::user()->cameras()->findOrFail($id);
        
        // Primero detener el stream si está corriendo
        $model = $camera->detection_model ?? 'yolov8n';
        
        if ($this->isGoModel($model)) {
            // Intentar detener en Go worker
            try {
                Http::timeout(5)->post($this->getGoWorkerUrl() . '/camera/' . $camera->id . '/stop');
            } catch (\Exception $e) {
                // Ignorar errores al detener
            }
        } else {
            // Enviar STOP a Python worker via Redis
            $message = json_encode([
                'action' => 'STOP',
                'camera_id' => $camera->id
            ]);
            Redis::publish('video_control', $message);
        }
        
        // Eliminar la cámara (esto también eliminará detecciones relacionadas por cascade si está configurado)
        $camera->delete();
        
        return response()->json([
            'status' => 'success',
            'message' => 'Cámara eliminada correctamente'
        ]);
    }
}