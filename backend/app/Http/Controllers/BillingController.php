<?php

namespace App\Http\Controllers;

use App\Models\Plan;
use App\Models\Subscription;
use App\Models\UsageRecord;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;

class BillingController extends Controller
{
    /**
     * Get available plans
     */
    public function plans()
    {
        $plans = Plan::active()->get()->map(function ($plan) {
            return [
                'id' => $plan->id,
                'name' => $plan->name,
                'display_name' => $plan->display_name,
                'price' => $plan->price,
                'formatted_price' => $plan->formatted_price,
                'currency' => $plan->currency,
                'limits' => $plan->limits,
                'features' => [
                    'cameras' => $plan->camera_limit,
                    'analysis_hours' => $plan->analysis_hours_per_day,
                    'ai_advanced' => $plan->ai_advanced,
                    'vlm_access' => $plan->vlm_access,
                    'satellite_access' => $plan->satellite_access,
                    'cad_access' => $plan->cad_access,
                    'api_access' => $plan->api_access,
                    'api_calls_per_day' => $plan->api_calls_per_day,
                    'email_alerts' => $plan->email_alerts,
                    'telegram_alerts' => $plan->telegram_alerts,
                    'recording' => $plan->recording,
                    'retention_days' => $plan->retention_days,
                ],
                'stripe_price_id' => $plan->stripe_price_id,
            ];
        });

        return response()->json($plans);
    }

    /**
     * Get current user's subscription status
     */
    public function status(Request $request)
    {
        $user = $request->user();
        $plan = $user->currentPlan();
        $subscription = $user->activeSubscription();

        return response()->json([
            'is_superadmin' => $user->isSuperAdmin(),
            'subscribed' => $user->subscribed(),
            'on_trial' => $user->onTrial(),
            'on_grace_period' => $user->onGracePeriod(),
            'plan' => [
                'id' => $plan->id,
                'name' => $plan->name,
                'display_name' => $plan->display_name,
                'price' => $plan->price,
            ],
            'subscription' => $subscription ? [
                'id' => $subscription->id,
                'status' => $subscription->stripe_status ?? 'active',
                'trial_ends_at' => $subscription->trial_ends_at?->toIso8601String(),
                'ends_at' => $subscription->ends_at?->toIso8601String(),
                'current_period_end' => $subscription->current_period_end?->toIso8601String(),
                'cancel_at_period_end' => $subscription->cancel_at_period_end,
            ] : null,
            'limits' => $user->limits,
        ]);
    }

    /**
     * Get usage statistics for current billing period
     */
    public function usage(Request $request)
    {
        $user = $request->user();
        $plan = $user->currentPlan();

        // Today's usage
        $todayAnalysis = UsageRecord::todayUsage($user->id, 'analysis_minutes');
        $todayApiCalls = UsageRecord::todayUsage($user->id, 'api_calls');

        // This month's usage
        $monthStart = now()->startOfMonth();
        $monthEnd = now()->endOfMonth();
        $monthAnalysis = UsageRecord::periodUsage($user->id, 'analysis_minutes', $monthStart, $monthEnd);
        $monthApiCalls = UsageRecord::periodUsage($user->id, 'api_calls', $monthStart, $monthEnd);

        return response()->json([
            'plan' => $plan->display_name,
            'is_superadmin' => $user->isSuperAdmin(),
            'today' => [
                'analysis_minutes' => $todayAnalysis,
                'analysis_hours' => round($todayAnalysis / 60, 2),
                'analysis_limit_hours' => $user->isSuperAdmin() ? '∞' : $plan->analysis_hours_per_day,
                'analysis_percentage' => $user->isSuperAdmin() ? 0 : 
                    min(100, round(($todayAnalysis / ($plan->analysis_hours_per_day * 60)) * 100)),
                'api_calls' => $todayApiCalls,
                'api_limit' => $user->isSuperAdmin() ? '∞' : $plan->api_calls_per_day,
                'api_percentage' => $user->isSuperAdmin() || $plan->api_calls_per_day == 0 ? 0 :
                    min(100, round(($todayApiCalls / $plan->api_calls_per_day) * 100)),
            ],
            'month' => [
                'analysis_hours' => round($monthAnalysis / 60, 2),
                'api_calls' => $monthApiCalls,
            ],
            'cameras' => [
                'active' => $user->cameras()->where('status', 'active')->count(),
                'total' => $user->cameras()->count(),
                'limit' => $user->isSuperAdmin() ? '∞' : $plan->camera_limit,
            ],
        ]);
    }

    /**
     * Create checkout session for Stripe (placeholder - needs Cashier)
     * 
     * When Laravel Cashier is installed, this will redirect to Stripe Checkout
     */
    public function checkout(Request $request)
    {
        $request->validate([
            'plan' => 'required|string|exists:plans,name',
        ]);

        $user = $request->user();
        $plan = Plan::where('name', $request->plan)->firstOrFail();

        // Si el plan es gratuito, asignar directamente
        if ($plan->price == 0) {
            $this->assignFreePlan($user, $plan);
            
            return response()->json([
                'success' => true,
                'message' => 'Plan gratuito asignado correctamente.',
                'redirect' => '/dashboard',
            ]);
        }

        // TODO: Cuando se instale Laravel Cashier, usar:
        // return $user->newSubscription('default', $plan->stripe_price_id)
        //     ->checkout([
        //         'success_url' => config('app.url') . '/billing/success?session_id={CHECKOUT_SESSION_ID}',
        //         'cancel_url' => config('app.url') . '/billing/cancel',
        //     ]);

        // Por ahora, devolver placeholder
        return response()->json([
            'success' => false,
            'message' => 'El sistema de pagos aún no está configurado. Contacta al administrador.',
            'plan' => $plan->display_name,
            'price' => $plan->formatted_price,
            // Esta URL sería la de Stripe Checkout
            'checkout_url' => null,
            'requires_setup' => true,
        ], 501);
    }

    /**
     * Handle successful checkout (webhook endpoint)
     */
    public function success(Request $request)
    {
        // TODO: Verificar session_id con Stripe
        // $sessionId = $request->get('session_id');
        
        return response()->json([
            'success' => true,
            'message' => 'Pago procesado correctamente. Tu suscripción está activa.',
            'redirect' => '/dashboard',
        ]);
    }

    /**
     * Handle Stripe webhooks
     */
    public function webhook(Request $request)
    {
        $payload = $request->getContent();
        $sigHeader = $request->header('Stripe-Signature');
        
        // TODO: Verificar firma con Stripe
        // $event = \Stripe\Webhook::constructEvent($payload, $sigHeader, config('services.stripe.webhook_secret'));

        $event = json_decode($payload);
        
        Log::info('Stripe webhook received', ['type' => $event->type ?? 'unknown']);

        // Handle different event types
        switch ($event->type ?? '') {
            case 'checkout.session.completed':
                $this->handleCheckoutCompleted($event->data->object);
                break;
                
            case 'invoice.payment_succeeded':
                $this->handlePaymentSucceeded($event->data->object);
                break;
                
            case 'invoice.payment_failed':
                $this->handlePaymentFailed($event->data->object);
                break;
                
            case 'customer.subscription.updated':
                $this->handleSubscriptionUpdated($event->data->object);
                break;
                
            case 'customer.subscription.deleted':
                $this->handleSubscriptionDeleted($event->data->object);
                break;
        }

        return response()->json(['received' => true]);
    }

    /**
     * Cancel subscription
     */
    public function cancel(Request $request)
    {
        $user = $request->user();
        $subscription = $user->activeSubscription();

        if (!$subscription) {
            return response()->json([
                'message' => 'No tienes una suscripción activa.',
            ], 400);
        }

        // TODO: Cancelar en Stripe
        // $user->subscription('default')->cancel();

        // Por ahora, marcar como cancelada al final del período
        $subscription->update([
            'cancel_at_period_end' => true,
        ]);

        return response()->json([
            'success' => true,
            'message' => 'Tu suscripción se cancelará al final del período actual.',
            'ends_at' => $subscription->current_period_end?->toIso8601String(),
        ]);
    }

    /**
     * Resume canceled subscription
     */
    public function resume(Request $request)
    {
        $user = $request->user();
        $subscription = $user->activeSubscription();

        if (!$subscription || !$subscription->cancel_at_period_end) {
            return response()->json([
                'message' => 'No hay suscripción cancelada para reanudar.',
            ], 400);
        }

        // TODO: Reanudar en Stripe
        // $user->subscription('default')->resume();

        $subscription->update([
            'cancel_at_period_end' => false,
        ]);

        return response()->json([
            'success' => true,
            'message' => 'Tu suscripción ha sido reanudada.',
        ]);
    }

    /**
     * Get billing portal URL (Stripe Customer Portal)
     */
    public function portal(Request $request)
    {
        $user = $request->user();

        if (!$user->stripe_id) {
            return response()->json([
                'message' => 'No tienes un perfil de facturación configurado.',
            ], 400);
        }

        // TODO: Generar URL del portal de Stripe
        // return $user->billingPortalUrl(route('dashboard'));

        return response()->json([
            'url' => null,
            'message' => 'El portal de facturación aún no está configurado.',
        ], 501);
    }

    // =========================================================================
    // PRIVATE HELPERS
    // =========================================================================

    private function assignFreePlan($user, $plan)
    {
        // Cancelar suscripción existente si hay
        $user->subscriptions()->update(['ends_at' => now()]);

        // Crear nueva suscripción gratuita
        Subscription::create([
            'user_id' => $user->id,
            'plan_id' => $plan->id,
            'type' => 'default',
            'stripe_status' => 'active',
        ]);

        $user->update(['plan_id' => $plan->id]);
    }

    private function handleCheckoutCompleted($session)
    {
        // TODO: Implementar cuando Stripe esté configurado
        Log::info('Checkout completed', ['session' => $session->id ?? null]);
    }

    private function handlePaymentSucceeded($invoice)
    {
        Log::info('Payment succeeded', ['invoice' => $invoice->id ?? null]);
    }

    private function handlePaymentFailed($invoice)
    {
        Log::warning('Payment failed', ['invoice' => $invoice->id ?? null]);
        
        // TODO: Suspender cámaras del usuario
        // $user = User::where('stripe_id', $invoice->customer)->first();
        // if ($user) {
        //     $user->cameras()->update(['status' => 'suspended']);
        //     // Notificar via Redis para detener workers
        //     Redis::publish('video_control', json_encode([
        //         'action' => 'STOP_ALL',
        //         'user_id' => $user->id
        //     ]));
        // }
    }

    private function handleSubscriptionUpdated($subscription)
    {
        Log::info('Subscription updated', ['subscription' => $subscription->id ?? null]);
    }

    private function handleSubscriptionDeleted($subscription)
    {
        Log::info('Subscription deleted', ['subscription' => $subscription->id ?? null]);
    }
}
