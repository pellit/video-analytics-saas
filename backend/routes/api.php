<?php

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Route;
use App\Http\Controllers\CameraController;

Route::get('/user', function (Request $request) {
    return $request->user();
})->middleware('auth:sanctum');

// Tus rutas
Route::post('/camera/start', [CameraController::class, 'start']);
Route::post('/camera/stop', [CameraController::class, 'stop']);