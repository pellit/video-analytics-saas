<?php

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Laravel\Sanctum\PersonalAccessToken;

class BearerTokenAuthenticate
{
    /**
     * Resolve the authenticated user from a Sanctum personal access token.
     */
    public function handle(Request $request, Closure $next): JsonResponse|\Symfony\Component\HttpFoundation\Response
    {
        $token = $request->bearerToken();

        if (!$token) {
            return $this->unauthorized();
        }

        $accessToken = PersonalAccessToken::findToken($token);

        if (!$accessToken || !$accessToken->tokenable) {
            return $this->unauthorized();
        }

        if ($accessToken->expires_at && now()->greaterThan($accessToken->expires_at)) {
            return $this->unauthorized('Token expired.');
        }

        // Keep Laravel's auth helpers in sync
        $user = $accessToken->tokenable;
        Auth::setUser($user);
        $request->setUserResolver(fn () => $user);

        // Update last usage timestamp for observability
        $accessToken->forceFill(['last_used_at' => now()])->save();

        return $next($request);
    }

    private function unauthorized(string $message = 'Unauthenticated.')
    {
        return response()->json(['message' => $message], 401);
    }
}
