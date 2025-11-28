use App\Http\Controllers\CameraController;

// ... (código existente si lo hay)

Route::post('/camera/start', [CameraController::class, 'start']);
Route::post('/camera/stop', [CameraController::class, 'stop']);