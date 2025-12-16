<?php

use Illuminate\Support\Facades\Route;
use Illuminate\Support\Facades\DB;

/*
|--------------------------------------------------------------------------
| API Routes Loader
|--------------------------------------------------------------------------
| Aquí organizamos y cargamos los grupos de rutas.
*/

// Health Check Endpoint (Public - for monitoring)
Route::get('/health', function () {
    $status = 'ok';
    $dbOk = false;
    $redisOk = false;
    
    // Check database
    try {
        DB::connection()->getPdo();
        $dbOk = true;
    } catch (\Exception $e) {
        $status = 'degraded';
    }
    
    // Check Redis (if available)
    try {
        $redis = app('redis');
        $redis->ping();
        $redisOk = true;
    } catch (\Exception $e) {
        // Redis is optional, don't mark as degraded
    }
    
    return response()->json([
        'status' => $status,
        'timestamp' => now()->toIso8601String(),
        'services' => [
            'database' => $dbOk,
            'redis' => $redisOk,
        ],
        'version' => config('app.version', '1.0.0'),
    ]);
});

// 1. Cargar Rutas Públicas (Auth)
require __DIR__ . '/api/auth.php';

// 2. Cargar Rutas de Billing (pagos y suscripciones)
require __DIR__ . '/api/billing.php';

// Worker endpoints (simple API key based)
use App\Http\Controllers\WorkerController;
Route::post('/worker/detections', [WorkerController::class, 'postDetection']);
Route::post('/worker/face-detection', [\App\Http\Controllers\FaceRecognitionController::class, 'recordDetection']);
Route::post('/worker/satellite-result', [\App\Http\Controllers\SatelliteController::class, 'storeWorkerResult']);
Route::post('/worker/satellite-thumbnail', [\App\Http\Controllers\SatelliteController::class, 'storeThumbnail']);

// CAD Worker callback (internal endpoint)
Route::post('/internal/cad/callback', [\App\Http\Controllers\CadController::class, 'workerCallback']);

Route::get('/test/worker-env', function (\Illuminate\Http\Request $r) {
    return response()->json(['env' => env('WORKER_API_KEY'), 'header' => $r->header('X-WORKER-KEY')]);
});

// SSE stream for real-time detections and alerts (Outside auth middleware to support EventSource query param auth)
Route::get('/sse/stream', [\App\Http\Controllers\SseController::class, 'stream']);

// ==========================================================================
// External API v1 (API Key authenticated) - For third-party applications
// ==========================================================================
use App\Http\Controllers\ExternalApiController;

Route::prefix('v1')->middleware('api.key')->group(function () {
    // Single frame analysis
    Route::post('/analyze/frame', [ExternalApiController::class, 'analyzeFrame']);
    
    // Batch frame analysis
    Route::post('/analyze/batch', [ExternalApiController::class, 'analyzeBatch']);
    
    // Stream analysis (async)
    Route::post('/analyze/stream', [ExternalApiController::class, 'analyzeStream']);
    Route::get('/analyze/status/{sessionId}', [ExternalApiController::class, 'getStatus']);
    Route::delete('/analyze/status/{sessionId}', [ExternalApiController::class, 'stopSession']);
});

// 2. Cargar Rutas Protegidas de Usuario
// Aplicamos el middleware de autenticación a todo este grupo
Route::middleware('token.auth')->group(function () {
    require __DIR__ . '/api/user.php';
});


// 3. Cargar Rutas de SuperAdmin
// Aplicamos Auth + el Alias 'superadmin' que creamos en bootstrap/app.php
// CORRECCIÓN IMPORTANTE: Usamos el alias string, no una función anónima.
Route::middleware(['token.auth', 'superadmin'])
    ->prefix('admin')
    ->group(function () {
        require __DIR__ . '/api/admin.php';
    });
