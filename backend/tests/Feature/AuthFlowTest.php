<?php

namespace Tests\Feature;

use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Mail;
use Illuminate\Support\Facades\URL;
use Tests\TestCase;
use App\Models\User;

class AuthFlowTest extends TestCase
{
    use RefreshDatabase; // Borra la BD en memoria después de cada test

    /** @test */
    public function un_usuario_puede_registrarse()
    {
        $response = $this->postJson('/api/register', [
            'name' => 'Test User',
            'email' => 'test@video.com',
            'password' => 'secret123'
        ]);

        $response->assertStatus(200)
                 ->assertJsonStructure(['token']);

        $this->assertDatabaseHas('users', ['email' => 'test@video.com']);
    }

    /** @test */
    public function un_usuario_puede_hacer_login_tradicional()
    {
        // 1. Crear usuario
        $user = User::factory()->create([
            'email' => 'login@video.com',
            'password' => bcrypt('password')
        ]);

        // 2. Intentar login
        $response = $this->postJson('/api/login', [
            'email' => 'login@video.com',
            'password' => 'password'
        ]);

        $response->assertStatus(200)
                 ->assertJsonStructure(['token', 'user']);
    }

    /** @test */
    public function el_magic_link_envia_un_correo()
    {
        Mail::fake(); // Intercepta los emails

        // 1. Solicitar Magic Link
        $response = $this->postJson('/api/auth/magic-link', [
            'email' => 'magic@video.com'
        ]);

        $response->assertStatus(200);

        // 2. Verificar que se creó el usuario implícitamente
        $this->assertDatabaseHas('users', ['email' => 'magic@video.com']);

        // 3. Verificar que se "envió" el email
        // Como usamos Mail::raw, verificamos que se haya enviado algo
        Mail::assertSent(function ($mail) {
            return $mail->hasTo('magic@video.com');
        });
    }

    /** @test */
    public function verificar_magic_link_loguea_al_usuario()
    {
        $user = User::factory()->create(['email' => 'verify@video.com']);

        // 1. Generar una URL firmada válida manualmente (simulando lo que hace el controlador)
        $url = URL::temporarySignedRoute(
            'verify-login', now()->addMinutes(15), ['id' => $user->id]
        );

        // 2. Visitar la URL
        $response = $this->getJson($url);

        // 3. Esperar token de vuelta
        $response->assertStatus(200)
                 ->assertJsonStructure(['token', 'user']);
                 
        $this->assertEquals('verify@video.com', $response->json('user.email'));
    }
}