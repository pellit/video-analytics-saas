<?php
namespace App\Http;

use Illuminate\Foundation\Http\Kernel as HttpKernel;
use Illuminate\Cookie\Middleware\AddQueuedCookiesToResponse;
use Illuminate\Cookie\Middleware\EncryptCookies;
use Illuminate\Session\Middleware\StartSession;
use Illuminate\View\Middleware\ShareErrorsFromSession;
use Illuminate\Routing\Middleware\SubstituteBindings;
use Illuminate\Routing\Middleware\ThrottleRequests;
use Illuminate\Http\Middleware\HandleCors;
use App\Http\Middleware\CheckSuperAdmin;
use App\Http\Middleware\CheckCameraLimit;
use App\Http\Middleware\CheckAnalysisLimit;
use App\Http\Middleware\CheckApiLimit;
use App\Http\Middleware\BearerTokenAuthenticate;

class Kernel extends HttpKernel
{
    /**
     * The application's global HTTP middleware stack.
     *
     * @var array<int, class-string|string>
     */
    protected $middleware = [
        // Only enable CORS handling in the minimal kernel for this project
        HandleCors::class,
    ];

    /**
     * The application's route middleware groups.
     *
     * @var array<string, array<int, class-string|string>>
     */
    protected $middlewareGroups = [
        'web' => [],
        'api' => [
            SubstituteBindings::class,
        ],
    ];

    /**
     * The application's route middleware aliases.
     *
     * @var array<string, class-string|string>
     */
    protected $routeMiddleware = [
        // Expose a few route middleware aliases used in the project
        'superadmin' => CheckSuperAdmin::class,
        'throttle' => \Illuminate\Routing\Middleware\ThrottleRequests::class,
        'signed' => \Illuminate\Routing\Middleware\ValidateSignature::class,
        'substituteBindings' => SubstituteBindings::class,
        // Subscription/Billing middleware
        'camera.limit' => CheckCameraLimit::class,
        'analysis.limit' => CheckAnalysisLimit::class,
        'api.limit' => CheckApiLimit::class,
        'token.auth' => BearerTokenAuthenticate::class,
    ];
}

    /**
     * Override terminateMiddleware to resolve middleware aliases before container make.
     */
    protected function terminateMiddleware($middleware, $request, $response)
    {
        if (is_string($middleware) && isset($this->routeMiddleware[$middleware])) {
            $middleware = $this->routeMiddleware[$middleware];
        }

        return parent::terminateMiddleware($middleware, $request, $response);
    }
