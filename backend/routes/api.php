<?php

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Route;
use App\Http\Controllers\CameraController;

// Rutas de API v1
Route::middleware('auth:sanctum')->get('/user', function (Request $request) {
    return $request->user();
});

// --- RUTAS DE CÁMARA ---
Route::post('/camera/start', [CameraController::class, 'start']);
Route::post('/camera/stop', [CameraController::class, 'stop']);