<?php

namespace Database\Seeders;

use App\Models\User;
use Illuminate\Database\Console\Seeds\WithoutModelEvents;
use Illuminate\Database\Seeder;

class DatabaseSeeder extends Seeder
{
    use WithoutModelEvents;

    /**
     * Seed the application's database.
     */
    public function run(): void
    {
        // User::factory(10)->create();

        User::factory()->create([
            'name' => 'Test User',
            'email' => 'test@example.com',
        ]);

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
    }
}
