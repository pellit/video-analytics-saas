<?php

use Illuminate\Support\Facades\Route;

/*
|--------------------------------------------------------------------------
| API Routes Loader
|--------------------------------------------------------------------------
| Aquí organizamos y cargamos los grupos de rutas.
*/

// 1. Cargar Rutas Públicas (Auth)
require __DIR__ . '/api/auth.php';


// 2. Cargar Rutas Protegidas de Usuario
// Aplicamos el middleware de autenticación a todo este grupo
Route::middleware('auth:sanctum')->group(function () {
    require __DIR__ . '/api/user.php';
});


// 3. Cargar Rutas de SuperAdmin
// Aplicamos Auth + el Alias 'superadmin' que creamos en bootstrap/app.php
// CORRECCIÓN IMPORTANTE: Usamos el alias string, no una función anónima.
Route::middleware(['auth:sanctum', 'superadmin'])
    ->prefix('admin')
    ->group(function () {
        require __DIR__ . '/api/admin.php';
    });