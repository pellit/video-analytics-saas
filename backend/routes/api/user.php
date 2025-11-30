<?php

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Route;
use App\Http\Controllers\CameraController;

/*
|--------------------------------------------------------------------------
| Rutas de Usuario (Requieren Token)
|--------------------------------------------------------------------------
| Estas rutas ya están envueltas en el middleware 'auth:sanctum'
| en el archivo principal api.php
*/

// Perfil del usuario
Route::get('/user', function (Request $request) {
    return $request->user();
});

// CRUD de Cámaras
Route::get('/cameras', [CameraController::class, 'index']);      // Listar
Route::post('/cameras', [CameraController::class, 'store']);     // Crear
Route::patch('/cameras/{id}', [CameraController::class, 'update']);  // Actualizar cámara

// Control de Video (Redis)
Route::post('/camera/start', [CameraController::class, 'start']); // Iniciar stream
Route::post('/camera/stop', [CameraController::class, 'stop']);   // Detener stream

// Detecciones
Route::get('/cameras/{id}/detections', [\App\Http\Controllers\DetectionController::class, 'index']);
Route::post('/cameras/{id}/detections', [\App\Http\Controllers\DetectionController::class, 'store']);

// Alert Rules (user-specific)
Route::get('/alerts', [\App\Http\Controllers\AlertController::class, 'index']);
Route::post('/alerts', [\App\Http\Controllers\AlertController::class, 'store']);
Route::put('/alerts/{alert}', [\App\Http\Controllers\AlertController::class, 'update']);
Route::delete('/alerts/{alert}', [\App\Http\Controllers\AlertController::class, 'destroy']);
Route::get('/alerts/recent', [\App\Http\Controllers\AlertController::class, 'recent']);
// SSE stream for real-time detections and alerts
Route::get('/sse/stream', [\App\Http\Controllers\SseController::class, 'stream']);