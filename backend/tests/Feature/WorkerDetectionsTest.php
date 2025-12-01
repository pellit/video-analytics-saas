<?php

namespace Tests\Feature;

use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;
use App\Models\User;
use App\Models\Camera;
use App\Models\Alert;

class WorkerDetectionsTest extends TestCase
{
    use RefreshDatabase;

    /** @test */
    public function worker_can_post_detection_and_alert_is_triggered()
    {
        $this->withoutExceptionHandling();
        // Seed admin and camera
        $this->seed();
        $admin = User::where('email','admin@video-saas.com')->first();
        $camera = $admin->cameras()->first();

        // Create an alert rule for the admin's camera (event person_detected threshold 0.5)
        $alert = Alert::create(['user_id' => $admin->id, 'camera_id' => $camera->id, 'name' => 'Alerta Test', 'event' => 'person_detected', 'threshold' => 0.5, 'enabled' => true]);

        $payload = ['label' => 'person_detected', 'score' => 0.9, 'bbox' => [10,20,30,40]];

        $res = $this->postJson('/api/worker/detections', [
            'camera_id' => $camera->id,
            'event' => 'person_detected',
            'payload' => $payload
        ], ['X-WORKER-KEY' => env('WORKER_API_KEY')]);

        $res->assertStatus(201);
        $this->assertDatabaseHas('detections', ['camera_id' => $camera->id, 'event' => 'person_detected']);
        $this->assertDatabaseHas('alert_logs', ['alert_id' => $alert->id]);
    }
}
