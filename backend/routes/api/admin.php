<?php

use Illuminate\Support\Facades\Route;
use App\Http\Controllers\AdminController;

/*
|--------------------------------------------------------------------------
| Rutas de SuperAdmin
|--------------------------------------------------------------------------
| Estas rutas requieren 'auth:sanctum' Y el rol 'superadmin'
*/

Route::get('/stats', [AdminController::class, 'stats']);

// Aquí podrías agregar más rutas futuras, ejemplo:
// Route::get('/users', [AdminController::class, 'indexUsers']);
// Route::delete('/users/{id}', [AdminController::class, 'deleteUser']);