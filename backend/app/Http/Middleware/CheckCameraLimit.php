<?php

namespace App\Http\Middleware;

use App\Models\UsageRecord;
use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

class CheckCameraLimit
{
    /**
     * Verifica límite de cámaras antes de crear una nueva.
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

        // Solo verificar en POST (creación)
        if ($request->isMethod('POST') && !$user->canAddCamera()) {
            $plan = $user->currentPlan();
            
            return response()->json([
                'message' => "Has alcanzado el límite de {$plan->camera_limit} cámaras de tu plan {$plan->display_name}.",
                'code' => 'CAMERA_LIMIT_REACHED',
                'limit' => $plan->camera_limit,
                'current' => $user->cameras()->count(),
                'upgrade_url' => '/billing/plans'
            ], 402);
        }

        return $next($request);
    }
}
