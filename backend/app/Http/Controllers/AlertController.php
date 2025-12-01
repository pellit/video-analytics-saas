<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use App\Models\Alert;

class AlertController extends Controller
{
    public function index()
    {
        return response()->json(Auth::user()->alerts()->with('camera')->get());
    }

    public function store(Request $request)
    {
        $data = $request->validate([
            'camera_id' => 'nullable|integer|exists:cameras,id',
            'name' => 'required|string',
            'event' => 'required|string',
            'threshold' => 'nullable|numeric',
            'enabled' => 'boolean'
        ]);

        $data['user_id'] = Auth::id();
        $alert = Alert::create($data);
        return response()->json($alert, 201);
    }

    public function update(Request $request, Alert $alert)
    {
        if ($alert->user_id !== Auth::id()) {
            return response()->json(['message' => 'Forbidden'], 403);
        }
        $data = $request->validate([
            'name' => 'sometimes|string',
            'event' => 'sometimes|string',
            'threshold' => 'sometimes|numeric',
            'enabled' => 'sometimes|boolean'
        ]);
        $alert->update($data);
        return response()->json($alert);
    }

    public function destroy(Alert $alert)
    {
        if ($alert->user_id !== Auth::id()) {
            return response()->json(['message' => 'Forbidden'], 403);
        }
        $alert->delete();
        return response()->json(['status' => 'deleted']);
    }

    public function recent()
    {
        $user = Auth::user();
        // Specify table name to avoid ambiguity in HasManyThrough join
        $alertIds = $user->alerts()->pluck('alerts.id');
        $logs = \App\Models\AlertLog::whereIn('alert_id', $alertIds)->latest()->take(50)->get();
        return response()->json($logs);
    }
}
