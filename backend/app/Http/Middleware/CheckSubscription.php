<?php

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

class CheckSubscription
{
    /**
     * Handle an incoming request.
     * 
     * Verifica que el usuario tenga una suscripción válida para acceder
     * a recursos protegidos. SuperAdmin bypasea todas las restricciones.
     *
     * @param  \Closure(\Illuminate\Http\Request): (\Symfony\Component\HttpFoundation\Response)  $next
     * @param  string|null  $feature  Feature específica requerida (opcional)
     */
    public function handle(Request $request, Closure $next, ?string $feature = null): Response
    {
        $user = $request->user();

        if (!$user) {
            return response()->json([
                'message' => 'No autenticado.',
                'code' => 'UNAUTHENTICATED'
            ], 401);
        }

        // SuperAdmin bypasea TODAS las restricciones
        if ($user->isSuperAdmin()) {
            return $next($request);
        }

        // Verificar si tiene suscripción activa o está en free tier válido
        if (!$user->subscribed() && !$user->onTrial()) {
            // Verificar si puede usar el free tier
            $plan = $user->currentPlan();
            
            if ($plan->name !== 'free') {
                return response()->json([
                    'message' => 'Tu suscripción ha expirado. Por favor, renueva tu plan.',
                    'code' => 'SUBSCRIPTION_EXPIRED',
                    'upgrade_url' => '/billing/plans'
                ], 402);
            }
        }

        // Si se especifica una feature, verificar acceso
        if ($feature && !$user->canUseFeature($feature)) {
            return response()->json([
                'message' => "Tu plan no incluye acceso a: {$feature}. Actualiza a un plan superior.",
                'code' => 'FEATURE_NOT_AVAILABLE',
                'feature' => $feature,
                'current_plan' => $user->currentPlan()->display_name,
                'upgrade_url' => '/billing/plans'
            ], 402);
        }

        return $next($request);
    }
}
