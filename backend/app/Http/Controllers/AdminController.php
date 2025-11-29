<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use App\Models\User;
use App\Models\Camera;

class AdminController extends Controller
{
    public function stats()
    {
        // 1. Métricas Generales
        $totalUsers = User::count();
        $totalCameras = Camera::count();
        
        // 2. Cámaras Online (Simulado basándonos en el status de DB)
        // En una v2 podríamos consultar a Redis directamente
        $activeCameras = Camera::where('status', 'online')->count();

        // 3. Usuarios recientes (Últimos 5)
        $recentUsers = User::latest()
            ->take(5)
            ->get(['id', 'name', 'email', 'created_at', 'role']);

        return response()->json([
            'metrics' => [
                'users' => $totalUsers,
                'cameras' => $totalCameras,
                'active' => $activeCameras
            ],
            'recent_users' => $recentUsers
        ]);
    }
}