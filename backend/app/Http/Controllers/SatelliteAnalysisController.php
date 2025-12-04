<?php

namespace App\Http\Controllers;

use App\Models\SatelliteAnalysis;
use App\Models\SatelliteZone;
use App\Models\UserNotification;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Storage;

class SatelliteAnalysisController extends Controller
{
    /**
     * Store a new satellite analysis.
     */
    public function store(Request $request)
    {
        $validated = $request->validate([
            'zone_id' => 'nullable|exists:satellite_zones,id',
            'zone_name' => 'nullable|string|max:255',
            'change_percent' => 'required|numeric|min:0|max:100',
            'ssim_score' => 'nullable|numeric|min:-1|max:1',
            'histogram_correlation' => 'nullable|numeric|min:-1|max:1',
            'pixel_diff_percent' => 'nullable|numeric|min:0|max:100',
            'severity' => 'required|in:minimal,low,moderate,significant,critical',
            'change_type' => 'nullable|in:construction,vegetation,water,deforestation,urban_expansion,agricultural,unknown',
            'vlm_analysis' => 'nullable|string',
            'vlm_model' => 'nullable|string',
            'recommendations' => 'nullable|array',
            'change_regions' => 'nullable|array',
            'heatmap_base64' => 'nullable|string',
            'overlay_base64' => 'nullable|string',
            'metadata' => 'nullable|array',
        ]);
        
        $zone = null;
        if ($validated['zone_id']) {
            $zone = SatelliteZone::find($validated['zone_id']);
        }
        
        // Save images if provided
        $heatmapPath = null;
        $overlayPath = null;
        
        if (!empty($validated['heatmap_base64'])) {
            $heatmapPath = $this->saveBase64Image(
                $validated['heatmap_base64'],
                'satellite/heatmaps',
                Auth::id()
            );
        }
        
        if (!empty($validated['overlay_base64'])) {
            $overlayPath = $this->saveBase64Image(
                $validated['overlay_base64'],
                'satellite/overlays',
                Auth::id()
            );
        }
        
        $analysis = SatelliteAnalysis::create([
            'user_id' => Auth::id(),
            'satellite_zone_id' => $validated['zone_id'] ?? null,
            'zone_name' => $validated['zone_name'] ?? $zone?->name,
            'latitude' => $zone?->latitude,
            'longitude' => $zone?->longitude,
            'change_percent' => $validated['change_percent'],
            'ssim_score' => $validated['ssim_score'] ?? null,
            'histogram_correlation' => $validated['histogram_correlation'] ?? null,
            'pixel_diff_percent' => $validated['pixel_diff_percent'] ?? null,
            'severity' => $validated['severity'],
            'change_type' => $validated['change_type'] ?? 'unknown',
            'vlm_analysis' => $validated['vlm_analysis'] ?? null,
            'vlm_model' => $validated['vlm_model'] ?? null,
            'recommendations' => $validated['recommendations'] ?? [],
            'change_regions' => $validated['change_regions'] ?? [],
            'heatmap_path' => $heatmapPath,
            'overlay_path' => $overlayPath,
            'metadata' => $validated['metadata'] ?? [],
        ]);
        
        // Send notification if significant change
        if ($analysis->shouldNotify()) {
            $notification = UserNotification::createForSatelliteAnalysis(
                $analysis,
                '🛰️ Cambio Detectado',
                "Se detectó un cambio del {$analysis->change_percent}% en {$analysis->zone_name}. Severidad: {$analysis->severity_label}"
            );
            
            $analysis->markNotified();
        }
        
        return response()->json([
            'success' => true,
            'analysis' => $analysis->load('zone'),
        ], 201);
    }

    /**
     * Get analysis history for a zone.
     */
    public function historyByZone(SatelliteZone $zone)
    {
        // Verify ownership
        if ($zone->user_id !== Auth::id()) {
            return response()->json(['error' => 'Unauthorized'], 403);
        }
        
        $history = SatelliteAnalysis::forZone($zone->id)
            ->orderBy('created_at', 'desc')
            ->limit(50)
            ->get();
        
        return response()->json($history);
    }

    /**
     * Get all analyses for the authenticated user.
     */
    public function index(Request $request)
    {
        $query = SatelliteAnalysis::forUser(Auth::id())
            ->with('zone')
            ->orderBy('created_at', 'desc');
        
        // Filter by severity
        if ($request->has('severity')) {
            $query->bySeverity($request->severity);
        }
        
        // Filter by zone
        if ($request->has('zone_id')) {
            $query->forZone($request->zone_id);
        }
        
        // Filter by date range
        if ($request->has('days')) {
            $query->recent((int)$request->days);
        }
        
        // Only significant changes
        if ($request->has('significant_only') && $request->significant_only) {
            $query->significantChanges();
        }
        
        $analyses = $query->paginate($request->per_page ?? 20);
        
        return response()->json($analyses);
    }

    /**
     * Get a single analysis.
     */
    public function show(SatelliteAnalysis $analysis)
    {
        // Verify ownership
        if ($analysis->user_id !== Auth::id()) {
            return response()->json(['error' => 'Unauthorized'], 403);
        }
        
        return response()->json($analysis->load('zone', 'notifications'));
    }

    /**
     * Delete an analysis.
     */
    public function destroy(SatelliteAnalysis $analysis)
    {
        // Verify ownership
        if ($analysis->user_id !== Auth::id()) {
            return response()->json(['error' => 'Unauthorized'], 403);
        }
        
        // Delete associated images
        if ($analysis->heatmap_path) {
            Storage::disk('public')->delete($analysis->heatmap_path);
        }
        if ($analysis->overlay_path) {
            Storage::disk('public')->delete($analysis->overlay_path);
        }
        
        $analysis->delete();
        
        return response()->json(['success' => true]);
    }

    /**
     * Get analysis statistics.
     */
    public function statistics(Request $request)
    {
        $days = $request->days ?? 30;
        
        $stats = [
            'total_analyses' => SatelliteAnalysis::forUser(Auth::id())
                ->recent($days)
                ->count(),
            
            'significant_changes' => SatelliteAnalysis::forUser(Auth::id())
                ->recent($days)
                ->significantChanges()
                ->count(),
            
            'by_severity' => SatelliteAnalysis::forUser(Auth::id())
                ->recent($days)
                ->selectRaw('severity, COUNT(*) as count')
                ->groupBy('severity')
                ->pluck('count', 'severity'),
            
            'by_change_type' => SatelliteAnalysis::forUser(Auth::id())
                ->recent($days)
                ->selectRaw('change_type, COUNT(*) as count')
                ->groupBy('change_type')
                ->pluck('count', 'change_type'),
            
            'average_change' => round(SatelliteAnalysis::forUser(Auth::id())
                ->recent($days)
                ->avg('change_percent') ?? 0, 2),
            
            'zones_monitored' => SatelliteAnalysis::forUser(Auth::id())
                ->recent($days)
                ->distinct('satellite_zone_id')
                ->count('satellite_zone_id'),
        ];
        
        return response()->json($stats);
    }

    /**
     * Save a base64 image to storage.
     */
    private function saveBase64Image(string $base64, string $folder, int $userId): string
    {
        $imageData = base64_decode($base64);
        $filename = $userId . '_' . time() . '_' . uniqid() . '.jpg';
        $path = $folder . '/' . $filename;
        
        Storage::disk('public')->put($path, $imageData);
        
        return $path;
    }
}
