<?php

namespace App\Http\Middleware;

use App\Models\UsageRecord;
use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

class CheckApiLimit
{
    /**
     * Verifica límite de llamadas API por día.
     */
    public function handle(Request $request, Closure $next): Response
    {
        $user = $request->user();

        if (!$user) {
            return response()->json(['message' => 'No autenticado.'], 401);
        }

        // SuperAdmin bypasea
        if ($user->isSuperAdmin()) {
            return $next($request);
        }

        // Verificar si puede usar API
        if (!$user->canUseFeature('api')) {
            return response()->json([
                'message' => 'Tu plan no incluye acceso a la API externa.',
                'code' => 'API_NOT_AVAILABLE',
                'upgrade_url' => '/billing/plans'
            ], 402);
        }

        // Verificar límite diario
        if ($user->hasReachedApiLimit()) {
            $plan = $user->currentPlan();
            
            return response()->json([
                'message' => "Has alcanzado el límite de {$plan->api_calls_per_day} llamadas API por día.",
                'code' => 'API_LIMIT_REACHED',
                'limit' => $plan->api_calls_per_day,
                'resets_at' => now()->endOfDay()->toIso8601String(),
                'upgrade_url' => '/billing/plans'
            ], 429);
        }

        // Registrar uso
        $response = $next($request);

        // Solo contar si fue exitoso
        if ($response->getStatusCode() < 400) {
            UsageRecord::record($user->id, 'api_calls', 1);
        }

        return $response;
    }
}
