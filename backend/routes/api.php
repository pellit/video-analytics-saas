<?php

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Route;
use App\Http\Controllers\AuthController;
use App\Http\Controllers\CameraController;
use App\Http\Controllers\MagicLinkController;

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

// Rutas Públicas
Route::post('/auth/magic-link', [MagicLinkController::class, 'send']);
Route::get('/auth/verify/{id}', [MagicLinkController::class, 'verify'])->name('verify-login');

// Rutas Protegidas (Admin Dashboard)
Route::middleware(['auth:sanctum'])->group(function () {
    // ... tus rutas de cámaras ...

    // Ruta para el SuperAdmin Dashboard
    Route::get('/admin/stats', function () {
        // Middleware casero para chequear rol
        if (request()->user()->role !== 'superadmin') abort(403);

        return [
            'users' => \App\Models\User::count(),
            'cameras' => \App\Models\Camera::count(),
            'recent_users' => \App\Models\User::latest()->take(5)->get()
        ];
    });
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



    // --- ZONA SUPERADMIN ---
    Route::prefix('admin')->group(function () {
        
        // Middleware casero: Si no es superadmin, error 403 (Prohibido)
        Route::middleware(function ($request, $next) {
            if ($request->user()->role !== 'superadmin') {
                return response()->json(['message' => 'Acceso denegado'], 403);
            }
            return $next($request);
        })->group(function () {
            
            // Aquí van todas las rutas de administración
            Route::get('/stats', [AdminController::class, 'stats']);
            
        });
    });
});