<?php

namespace Tests\Feature;

use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;
use App\Models\User;
use App\Models\Camera;

class DetectionTest extends TestCase
{
    use RefreshDatabase;

    /** @test */
    public function usuario_logueado_puede_crear_una_camara_y_guardar_detecciones()
    {
        // 1. Crear usuario y token
        $user = User::factory()->create();
        $token = $user->createToken('test')->plainTextToken;

        // 2. Crear cámara via API
        $res = $this->withHeaders([
            'Authorization' => 'Bearer ' . $token,
            'Accept' => 'application/json'
        ])->postJson('/api/cameras', [
            'name' => 'Cámara Test Detección',
            'url' => 'rtsp://test/stream'
        ]);

        $res->assertStatus(201)->assertJsonFragment(['name' => 'Cámara Test Detección']);
        $cameraId = $res->json('id');

        // 3. Enviar detecciones (simulando el AI worker)
        $payload1 = ['score' => 0.98, 'bbox' => [10,20,100,200]];
        $res2 = $this->withHeaders(['Authorization' => 'Bearer ' . $token, 'Accept' => 'application/json'])
            ->postJson("/api/cameras/{$cameraId}/detections", [
                'event' => 'person_detected',
                'payload' => $payload1
            ]);
        $res2->assertStatus(201)->assertJsonFragment(['event' => 'person_detected']);

        $this->assertDatabaseHas('detections', ['camera_id' => $cameraId, 'event' => 'person_detected']);

        // 4. Recuperar detecciones y comprobar payload
        $res3 = $this->withHeaders(['Authorization' => 'Bearer ' . $token, 'Accept' => 'application/json'])
            ->getJson("/api/cameras/{$cameraId}/detections");

        $res3->assertStatus(200);
        $this->assertEquals('person_detected', $res3->json()[0]['event']);
        $this->assertEquals(0.98, $res3->json()[0]['payload']['score']);
    }
}
