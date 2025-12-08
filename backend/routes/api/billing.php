<?php

use App\Http\Controllers\BillingController;
use Illuminate\Support\Facades\Route;

/*
|--------------------------------------------------------------------------
| Billing Routes
|--------------------------------------------------------------------------
*/

// Public routes (plans listing)
Route::get('/billing/plans', [BillingController::class, 'plans']);

// Stripe webhook (no auth)
Route::post('/billing/webhook', [BillingController::class, 'webhook']);

// Protected routes
Route::middleware('auth:sanctum')->prefix('billing')->group(function () {
    // Subscription status
    Route::get('/status', [BillingController::class, 'status']);
    Route::get('/usage', [BillingController::class, 'usage']);
    
    // Checkout & subscription management
    Route::post('/checkout', [BillingController::class, 'checkout']);
    Route::get('/success', [BillingController::class, 'success']);
    Route::post('/cancel', [BillingController::class, 'cancel']);
    Route::post('/resume', [BillingController::class, 'resume']);
    Route::get('/portal', [BillingController::class, 'portal']);
});
