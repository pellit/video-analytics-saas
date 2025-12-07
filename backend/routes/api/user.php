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
Route::delete('/cameras/{id}', [CameraController::class, 'destroy']); // Eliminar cámara

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

// Detecciones de rostros por cámara
Route::get('/cameras/{id}/face-detections', [\App\Http\Controllers\FaceRecognitionController::class, 'getDetectionsByCamera']);

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

// Satellite Zones Management
Route::get('/satellite/zones', [\App\Http\Controllers\SatelliteController::class, 'index']);
Route::post('/satellite/zones', [\App\Http\Controllers\SatelliteController::class, 'store']);
Route::get('/satellite/zones/{zone}', [\App\Http\Controllers\SatelliteController::class, 'show']);
Route::put('/satellite/zones/{zone}', [\App\Http\Controllers\SatelliteController::class, 'update']);
Route::delete('/satellite/zones/{zone}', [\App\Http\Controllers\SatelliteController::class, 'destroy']);
Route::post('/satellite/zones/{zone}/analyze', [\App\Http\Controllers\SatelliteController::class, 'analyze']);
Route::get('/satellite/zones/{zone}/latest-image', [\App\Http\Controllers\SatelliteController::class, 'latestImage']);
Route::get('/satellite/zones/{zone}/alerts', [\App\Http\Controllers\SatelliteController::class, 'alerts']);
Route::get('/satellite/zones/{zone}/analysis-history', [\App\Http\Controllers\SatelliteAnalysisController::class, 'historyByZone']);

// Satellite Analysis (VLM History)
Route::get('/satellite/analysis', [\App\Http\Controllers\SatelliteAnalysisController::class, 'index']);
Route::post('/satellite/analysis', [\App\Http\Controllers\SatelliteAnalysisController::class, 'store']);
Route::get('/satellite/analysis/statistics', [\App\Http\Controllers\SatelliteAnalysisController::class, 'statistics']);
Route::get('/satellite/analysis/{analysis}', [\App\Http\Controllers\SatelliteAnalysisController::class, 'show']);
Route::delete('/satellite/analysis/{analysis}', [\App\Http\Controllers\SatelliteAnalysisController::class, 'destroy']);

// User Notifications
Route::get('/notifications', [\App\Http\Controllers\NotificationController::class, 'index']);
Route::get('/notifications/unread-count', [\App\Http\Controllers\NotificationController::class, 'unreadCount']);
Route::get('/notifications/recent', [\App\Http\Controllers\NotificationController::class, 'recent']);
Route::post('/notifications/send', [\App\Http\Controllers\NotificationController::class, 'send']);
Route::post('/notifications/mark-all-read', [\App\Http\Controllers\NotificationController::class, 'markAllRead']);
Route::post('/notifications/{notification}/read', [\App\Http\Controllers\NotificationController::class, 'markRead']);
Route::delete('/notifications/{notification}', [\App\Http\Controllers\NotificationController::class, 'destroy']);

// ==========================================================================
// CAD Projects - "Architect's Eye" Feature
// Análisis inteligente de planos arquitectónicos/ingeniería
// ==========================================================================
Route::prefix('cad')->group(function () {
    // Project Types (meta)
    Route::get('/project-types', [\App\Http\Controllers\CadController::class, 'projectTypes']);
    
    // Analytics (dashboard)
    Route::get('/analytics', [\App\Http\Controllers\CadController::class, 'analytics']);
    
    // CRUD de proyectos CAD
    Route::get('/projects', [\App\Http\Controllers\CadController::class, 'index']);
    Route::post('/projects', [\App\Http\Controllers\CadController::class, 'upload']);
    Route::get('/projects/{id}', [\App\Http\Controllers\CadController::class, 'show']);
    Route::patch('/projects/{id}', [\App\Http\Controllers\CadController::class, 'update']);
    Route::delete('/projects/{id}', [\App\Http\Controllers\CadController::class, 'destroy']);
    
    // Status & Actions
    Route::get('/projects/{id}/status', [\App\Http\Controllers\CadController::class, 'status']);
    Route::post('/projects/{id}/reanalyze', [\App\Http\Controllers\CadController::class, 'reanalyze']);
});
