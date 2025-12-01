<?php

namespace Tests\Feature;

// use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class ExampleTest extends TestCase
{
    use \Illuminate\Foundation\Testing\RefreshDatabase;

    /**
     * A basic test example.
     */
    public function test_the_application_returns_a_successful_response(): void
    {
        dump('Config app.key: ' . config('app.key'));
        dump('Env APP_KEY: ' . env('APP_KEY'));
        $response = $this->get('/');

        $response->assertStatus(200);
    }
}
