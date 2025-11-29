<?php

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Route;
use App\Http\Controllers\AuthController;
use App\Http\Controllers\CameraController;

/*
|--------------------------------------------------------------------------
| API Routes
|--------------------------------------------------------------------------
*/

// --- RUTAS PÚBLICAS ---

// Prueba de salud
Route::get('/test', function () {
    return response()->json(['status' => 'API Online 🚀']);
});

// Autenticación
Route::post('/register', [AuthController::class, 'register']);
Route::post('/login', [AuthController::class, 'login']);


// --- RUTAS PROTEGIDAS (Requieren Token) ---
Route::middleware('auth:sanctum')->group(function () {

    // Obtener usuario actual
    Route::get('/user', function (Request $request) {
        return $request->user();
    });

    // Gestión de Cámaras (CRUD)
    Route::get('/cameras', [CameraController::class, 'index']); // Listar mis cámaras
    Route::post('/cameras', [CameraController::class, 'store']); // Crear nueva cámara
    
    // Control de Análisis (Redis)
    Route::post('/camera/start', [CameraController::class, 'start']);
    Route::post('/camera/stop', [CameraController::class, 'stop']);

});