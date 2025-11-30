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
            // Usamos updateOrCreate para garantizar que las cámaras por defecto
            // estén presentes y mantengan la URL solicitada.
            $admin->cameras()->updateOrCreate(
                ['name' => 'Cámara YouTube 1'],
                ['url' => 'https://www.youtube.com/watch?v=aISKK1ex5zU', 'status' => 'offline']
            );
            $admin->cameras()->updateOrCreate(
                ['name' => 'Cámara YouTube 2'],
                ['url' => 'https://www.youtube.com/watch?v=fa8iGVeri_I', 'status' => 'offline']
            );
            $admin->cameras()->updateOrCreate(
                ['name' => 'Cámara YouTube 3'],
                ['url' => 'https://www.youtube.com/watch?v=qMYlpMsWsBE', 'status' => 'offline']
            );
        }
    }
}

// agrega a la app opcines de ver con modelo de profundidad y seguimiento agregando rutinas de ultralitics simpre que podamos elegir y ademas un sistema de alertas en tiempo real configurable, luego de todo eso haz un push 
