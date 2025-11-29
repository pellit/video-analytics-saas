<?php

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

class CheckSuperAdmin
{
    /**
     * Handle an incoming request.
     */
    public function handle(Request $request, Closure $next): Response
    {
        // Verificamos si el usuario tiene el rol correcto
        if (!$request->user() || $request->user()->role !== 'superadmin') {
            return response()->json(['message' => 'Acceso denegado. Se requieren permisos de SuperAdmin.'], 403);
        }

        return $next($request);
    }
}