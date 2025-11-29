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

// Control de Video (Redis)
Route::post('/camera/start', [CameraController::class, 'start']); // Iniciar stream
Route::post('/camera/stop', [CameraController::class, 'stop']);   // Detener stream