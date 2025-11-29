<?php

namespace Tests\Feature;

use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;
use App\Models\User;

class CameraTest extends TestCase
{
    use RefreshDatabase;

    /** @test */
    public function un_usuario_autenticado_puede_crear_y_ver_sus_camaras()
    {
        // Crear usuario y token
        $user = User::factory()->create();
        $token = $user->createToken('test')->plainTextToken;

        // Llamar a la API para crear cámara
        $response = $this->withHeaders([
            'Authorization' => 'Bearer ' . $token,
            'Accept' => 'application/json'
        ])->postJson('/api/cameras', [
            'name' => 'Mi Cámara 1',
            'url' => 'rtsp://camera.local/stream'
        ]);

        $response->assertStatus(201)
                 ->assertJsonFragment(['name' => 'Mi Cámara 1']);

        $this->assertDatabaseHas('cameras', ['name' => 'Mi Cámara 1', 'user_id' => $user->id]);

        // Recuperar lista de cámaras
        $res2 = $this->withHeaders(['Authorization' => 'Bearer ' . $token, 'Accept' => 'application/json'])
            ->getJson('/api/cameras');

        $res2->assertStatus(200)
             ->assertJsonCount(1)
             ->assertJsonFragment(['name' => 'Mi Cámara 1']);
    }
}
