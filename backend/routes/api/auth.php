<?php

use Illuminate\Support\Facades\Route;
use App\Http\Controllers\AuthController;
use App\Http\Controllers\MagicLinkController;

// Prueba de salud (Pública)
Route::get('/test', function () {
    return response()->json(['status' => 'API Online 🚀']);
});

// Login Tradicional
Route::post('/register', [AuthController::class, 'register']);
Route::post('/login', [AuthController::class, 'login']);

// Magic Links (Sin contraseña)
Route::post('/auth/magic-link', [MagicLinkController::class, 'send']);
Route::get('/auth/verify/{id}', [MagicLinkController::class, 'verify'])->name('verify-login');