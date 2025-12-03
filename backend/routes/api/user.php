<?php

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Route;
use App\Http\Controllers\CameraController;
use App\Http\Controllers\SceneAnalysisController;

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

// Configuración de cámara (Wizard)
Route::post('/cameras/{camera}/setup', [SceneAnalysisController::class, 'completeSetup']);
Route::post('/cameras/{camera}/analyze-scene', [SceneAnalysisController::class, 'analyzeScene']);
Route::post('/cameras/{camera}/apply-recommendations', [SceneAnalysisController::class, 'applyRecommendations']);

// Detecciones
Route::get('/cameras/{id}/detections', [\App\Http\Controllers\DetectionController::class, 'index']);
Route::post('/cameras/{id}/detections', [\App\Http\Controllers\DetectionController::class, 'store']);

// Alert Rules (user-specific)
Route::get('/alerts', [\App\Http\Controllers\AlertController::class, 'index']);
Route::post('/alerts', [\App\Http\Controllers\AlertController::class, 'store']);
Route::put('/alerts/{alert}', [\App\Http\Controllers\AlertController::class, 'update']);
Route::delete('/alerts/{alert}', [\App\Http\Controllers\AlertController::class, 'destroy']);
Route::get('/alerts/recent', [\App\Http\Controllers\AlertController::class, 'recent']);

// API Keys Management (for users to manage their own keys)
Route::get('/api-keys', [\App\Http\Controllers\ApiKeyController::class, 'index']);
Route::post('/api-keys', [\App\Http\Controllers\ApiKeyController::class, 'store']);
Route::get('/api-keys/{id}', [\App\Http\Controllers\ApiKeyController::class, 'show']);
Route::patch('/api-keys/{id}', [\App\Http\Controllers\ApiKeyController::class, 'update']);
Route::delete('/api-keys/{id}', [\App\Http\Controllers\ApiKeyController::class, 'destroy']);
Route::post('/api-keys/{id}/regenerate', [\App\Http\Controllers\ApiKeyController::class, 'regenerate']);

// Face Recognition - Known Faces Management
Route::get('/faces', [\App\Http\Controllers\FaceRecognitionController::class, 'listKnownFaces']);
Route::post('/faces', [\App\Http\Controllers\FaceRecognitionController::class, 'createKnownFace']);
Route::get('/faces/{id}', [\App\Http\Controllers\FaceRecognitionController::class, 'getKnownFace']);
Route::patch('/faces/{id}', [\App\Http\Controllers\FaceRecognitionController::class, 'updateKnownFace']);
Route::delete('/faces/{id}', [\App\Http\Controllers\FaceRecognitionController::class, 'deleteKnownFace']);

// Face Recognition - Detections
Route::get('/face-detections', [\App\Http\Controllers\FaceRecognitionController::class, 'getRecentDetections']);
Route::post('/face-detections/{detectionId}/assign', [\App\Http\Controllers\FaceRecognitionController::class, 'assignDetectionToFace']);
Route::post('/face-detections/{detectionId}/create-face', [\App\Http\Controllers\FaceRecognitionController::class, 'createFaceFromDetection']);
