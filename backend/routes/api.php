<?php

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Route;
use App\Http\Controllers\CameraController;

// Ruta de prueba para ver si la API responde
Route::get('/test', function () {
    return response()->json(['status' => 'API Working']);
});

// --- TUS RUTAS DE CÁMARA ---
Route::post('/camera/start', [CameraController::class, 'start']);
Route::post('/camera/stop', [CameraController::class, 'stop']);