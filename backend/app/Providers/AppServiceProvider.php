<?php

namespace App\Providers;

use Illuminate\Support\ServiceProvider;

class AppServiceProvider extends ServiceProvider
{
    /**
     * Register any application services.
     */
    public function register(): void
    {
        // Bind legacy middleware alias 'token.auth' to the actual class
        // Some runtime code may attempt to resolve the alias directly from the container.
        $this->app->bind('token.auth', \App\Http\Middleware\BearerTokenAuthenticate::class);
    }

    /**
     * Bootstrap any application services.
     */
    public function boot(): void
    {
        // Ensure the container recognizes the legacy middleware alias
        $this->app->alias(\App\Http\Middleware\BearerTokenAuthenticate::class, 'token.auth');
    }
}
