<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use App\Models\User;
use Illuminate\Support\Facades\URL;
use Illuminate\Support\Facades\Mail;
use App\Mail\MagicLinkMail;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Hash;
use Illuminate\Support\Str;

class MagicLinkController extends Controller
{
    // 1. Enviar el Link
    public function send(Request $request)
    {
        $request->validate(['email' => 'required|email']);

        // Buscamos o creamos el usuario (Registro implícito o Login)
        $user = User::firstOrCreate(
            ['email' => $request->email],
            [
                'name' => explode('@', $request->email)[0],
                'role' => 'admin',
                // Garantizar que la columna `password` no sea NULL
                'password' => Hash::make(Str::random(12)),
            ]
        );

        // Generar URL firmada temporal (válida por 15 min)
        // Esta URL apuntará al FRONTEND, con un token como parámetro
        $url = URL::temporarySignedRoute(
            'verify-login', now()->addMinutes(15), ['id' => $user->id]
        );

        // Convertimos la URL de API a URL de Frontend para el email
        // De: http://api:8000/api/auth/verify/123?signature=...
        // A:  http://frontend:5173/verify?url=...
        $frontendUrl = str_replace(env('APP_URL').'/api', 'http://192.168.0.38:5173/auth/callback', $url);

        // Enviar Email (ahora con Mailable para facilitar las pruebas)
        Mail::to($user->email)->send(new MagicLinkMail($frontendUrl));

        return response()->json(['message' => 'Enlace mágico enviado a tu correo.']);
    }

    // 2. Verificar el Link (Laravel valida la firma)
    public function verify(Request $request, $id)
    {
        if (!$request->hasValidSignature()) {
            return response()->json(['message' => 'Enlace inválido o expirado'], 401);
        }

        $user = User::findOrFail($id);

        // Login exitoso
        $token = $user->createToken('auth_token')->plainTextToken;

        return response()->json([
            'token' => $token,
            'user' => $user
        ]);
    }
}