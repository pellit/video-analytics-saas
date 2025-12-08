<?php

namespace App\Http\Middleware;

use App\Models\UsageRecord;
use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

class CheckAnalysisLimit
{
    /**
     * Verifica límite de horas de análisis por día.
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

        // Verificar límite de análisis
        if ($user->hasReachedAnalysisLimit()) {
            $plan = $user->currentPlan();
            
            return response()->json([
                'message' => "Has alcanzado el límite de {$plan->analysis_hours_per_day} horas de análisis por día.",
                'code' => 'ANALYSIS_LIMIT_REACHED',
                'limit_hours' => $plan->analysis_hours_per_day,
                'resets_at' => now()->endOfDay()->toIso8601String(),
                'upgrade_url' => '/billing/plans'
            ], 402);
        }

        return $next($request);
    }
}
