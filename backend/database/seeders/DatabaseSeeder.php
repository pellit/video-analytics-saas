<?php

namespace Database\Seeders;

use App\Models\User;
use Illuminate\Database\Console\Seeds\WithoutModelEvents;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\Hash;

class DatabaseSeeder extends Seeder
{
    use WithoutModelEvents;

    /**
     * Seed the application's database.
     */
    public function run(): void
    {
        // Seed plans first (needed for subscriptions)
        $this->call(PlanSeeder::class);

        // Create a Test User if it doesn't exist (idempotent seeding)
        $testUser = User::firstOrCreate(
            ['email' => 'test@example.com'],
            [
                'name' => 'Test User',
                'password' => Hash::make('password'),
                'email_verified_at' => now(),
            ]
        );

        // Crear SuperAdmin si no existe
        User::firstOrCreate(
            ['email' => 'admin@video-saas.com'],
            [
                'name' => 'Super Admin',
                'password' => Hash::make('admin123'), // Contraseña de respaldo
                'role' => 'superadmin',
                'email_verified_at' => now(),
            ]
        );

        // Crear cámaras demo para el Test User
        if ($testUser) {
            $testUser->cameras()->updateOrCreate(
                ['name' => 'Demo - Times Square NYC'],
                ['url' => 'https://www.youtube.com/watch?v=aISKK1ex5zU', 'status' => 'offline', 'detection_enabled' => true, 'detection_model' => 'yolov8n']
            );
            $testUser->cameras()->updateOrCreate(
                ['name' => 'Demo - Tokyo Street'],
                ['url' => 'https://www.youtube.com/watch?v=gFRtAAmiFbE', 'status' => 'offline', 'detection_enabled' => true, 'detection_model' => 'yolov8n']
            );
                        $admin->cameras()->updateOrCreate(
                ['name' => 'Inside Living ROOM'],
                ['url' => 'https://www.youtube.com/watch?v=BJ7fql5fKsU', 'status' => 'offline', 'detection_enabled' => true, 'detection_model' => 'yolov8n']
            );
            $admin->cameras()->updateOrCreate(
                ['name' => 'Traffic Cam Fresno'],
                ['url' => 'https://www.youtube.com/watch?v=HiOvVp-wMj0', 'status' => 'offline', 'detection_enabled' => true, 'detection_model' => 'yolov8n']
            );
        }

        // Crear una cámara por defecto para el SuperAdmin si no existe
        $admin = User::where('email', 'admin@video-saas.com')->first();
        if ($admin) {
            // Usamos updateOrCreate para garantizar que las cámaras por defecto
            // estén presentes y mantengan la URL solicitada.
            $admin->cameras()->updateOrCreate(
                ['name' => 'Cámara YouTube 1'],
                ['url' => 'https://www.youtube.com/watch?v=aISKK1ex5zU', 'status' => 'offline', 'detection_enabled' => true, 'detection_model' => 'yolov8n']
            );
            $admin->cameras()->updateOrCreate(
                ['name' => 'Cámara YouTube 2'],
                ['url' => 'https://www.youtube.com/watch?v=fa8iGVeri_I', 'status' => 'offline', 'detection_enabled' => true, 'detection_model' => 'yolov8n']
            );
            $admin->cameras()->updateOrCreate(
                ['name' => 'Cámara YouTube 3'],
                ['url' => 'https://www.youtube.com/watch?v=qMYlpMsWsBE', 'status' => 'offline', 'detection_enabled' => true, 'detection_model' => 'yolov8n']
            );
            $admin->cameras()->updateOrCreate(
                ['name' => 'Inside Living ROOM'],
                ['url' => 'https://www.youtube.com/watch?v=BJ7fql5fKsU', 'status' => 'offline', 'detection_enabled' => true, 'detection_model' => 'yolov8n']
            );
            $admin->cameras()->updateOrCreate(
                ['name' => 'Traffic Cam Fresno'],
                ['url' => 'https://www.youtube.com/watch?v=HiOvVp-wMj0', 'status' => 'offline', 'detection_enabled' => true, 'detection_model' => 'yolov8n']
            );
        }
    }
}

