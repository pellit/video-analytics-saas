<?php

namespace Tests\Feature;

use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;
use App\Models\User;

class AdminDefaultCamerasTest extends TestCase
{
    use RefreshDatabase;

    /** @test */
    public function superadmin_tiene_tres_camaras_por_defecto_despues_del_seeder()
    {
        // Ejecutamos el seeder principal
        $this->seed();

        $admin = User::where('email', 'admin@video-saas.com')->first();
        $this->assertNotNull($admin, 'SuperAdmin no fue creado por el seeder');

        $this->assertEquals(3, $admin->cameras()->count());

        $this->assertDatabaseHas('cameras', ['user_id' => $admin->id, 'url' => 'https://www.youtube.com/watch?v=aISKK1ex5zU']);
        $this->assertDatabaseHas('cameras', ['user_id' => $admin->id, 'url' => 'https://www.youtube.com/watch?v=fa8iGVeri_I']);
        $this->assertDatabaseHas('cameras', ['user_id' => $admin->id, 'url' => 'https://www.youtube.com/watch?v=qMYlpMsWsBE']);
    }
}
