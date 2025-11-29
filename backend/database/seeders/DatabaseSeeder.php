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
        // User::factory(10)->create();

        // Create a Test User if it doesn't exist (idempotent seeding)
        User::firstOrCreate(
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

        // Crear una cámara por defecto para el SuperAdmin si no existe
        $admin = User::where('email', 'admin@video-saas.com')->first();
        if ($admin) {
            $admin->cameras()->firstOrCreate(
                ['name' => 'Cámara por defecto'],
                ['url' => 'rtsp://default/stream', 'status' => 'offline']
            );
        }
    }
}
