<?php

use Illuminate\Support\Facades\Route;
use App\Http\Controllers\AdminController;
use App\Http\Controllers\AdminApiController;

/*
|--------------------------------------------------------------------------
| Rutas de SuperAdmin
|--------------------------------------------------------------------------
| Estas rutas requieren 'auth:sanctum' Y el rol 'superadmin'
*/

Route::get('/stats', [AdminController::class, 'stats']);

// API Usage Management (SuperAdmin)
Route::prefix('api-usage')->group(function () {
    Route::get('/overview', [AdminApiController::class, 'overview']);
    Route::get('/keys', [AdminApiController::class, 'listKeys']);
    Route::get('/keys/{id}', [AdminApiController::class, 'keyStats']);
    Route::post('/keys/{id}/toggle', [AdminApiController::class, 'toggleKey']);
    Route::delete('/keys/{id}', [AdminApiController::class, 'deleteKey']);
    Route::get('/activity', [AdminApiController::class, 'activityFeed']);
});

// Aquí podrías agregar más rutas futuras, ejemplo:
// Route::get('/users', [AdminController::class, 'indexUsers']);
// Route::delete('/users/{id}', [AdminController::class, 'deleteUser']);