<?php

namespace App\Http\Controllers;

use App\Models\SatelliteZone;
use App\Models\SatelliteImage;
use App\Models\SatelliteAlert;
use Illuminate\Http\Request;
use Illuminate\Http\JsonResponse;
use Illuminate\Support\Facades\Redis;
use Illuminate\Support\Facades\Storage;
use Illuminate\Validation\Rule;

class SatelliteController extends Controller
{
    /**
     * Listar todas las zonas satelitales del usuario
     */
    public function index(Request $request): JsonResponse
    {
        $zones = SatelliteZone::where('user_id', $request->user()->id)
            ->with(['latestImage'])
            ->withCount(['images', 'unreadAlerts'])
            ->orderByDesc('updated_at')
            ->get();

        return response()->json($zones);
    }

    /**
     * Crear nueva zona satelital
     */
    public function store(Request $request): JsonResponse
    {
        $validated = $request->validate([
            'name' => 'required|string|max:255',
            'description' => 'nullable|string|max:1000',
            'latitude' => 'required|numeric|between:-90,90',
            'longitude' => 'required|numeric|between:-180,180',
            'radius_km' => 'nullable|numeric|between:0.1,50',
            'frequency' => ['nullable', Rule::in(['hourly', 'daily', 'weekly', 'manual'])],
            'preferred_time' => 'nullable|date_format:H:i',
            'max_cloud_cover' => 'nullable|integer|between:0,100',
            'alert_rules' => 'nullable|array',
        ]);

        $zone = SatelliteZone::create([
            'user_id' => $request->user()->id,
            ...$validated,
            'radius_km' => $validated['radius_km'] ?? 1.0,
            'frequency' => $validated['frequency'] ?? 'daily',
            'max_cloud_cover' => $validated['max_cloud_cover'] ?? 20,
        ]);

        // Solicitar thumbnail inicial de la zona
        try {
            $command = [
                'action' => 'GET_ZONE_THUMBNAIL',
                'zone_id' => $zone->id,
                'lat' => (float) $zone->latitude,
                'lon' => (float) $zone->longitude,
                'radius_km' => (float) $zone->radius_km,
            ];
            Redis::publish('satellite_control', json_encode($command));
        } catch (\Exception $e) {
            // No fallar si no se puede obtener el thumbnail
            \Log::warning('Could not request zone thumbnail: ' . $e->getMessage());
        }

        return response()->json($zone, 201);
    }

    /**
     * Obtener detalle de una zona
     */
    public function show(Request $request, SatelliteZone $zone): JsonResponse
    {
        // Verificar propiedad
        if ($zone->user_id !== $request->user()->id) {
            return response()->json(['error' => 'No autorizado'], 403);
        }

        $zone->load(['images' => fn($q) => $q->latest()->limit(10), 'alerts' => fn($q) => $q->latest()->limit(20)]);
        $zone->loadCount(['images', 'unreadAlerts']);

        return response()->json($zone);
    }

    /**
     * Actualizar zona
     */
    public function update(Request $request, SatelliteZone $zone): JsonResponse
    {
        if ($zone->user_id !== $request->user()->id) {
            return response()->json(['error' => 'No autorizado'], 403);
        }

        $validated = $request->validate([
            'name' => 'sometimes|string|max:255',
            'description' => 'nullable|string|max:1000',
            'latitude' => 'sometimes|numeric|between:-90,90',
            'longitude' => 'sometimes|numeric|between:-180,180',
            'radius_km' => 'sometimes|numeric|between:0.1,50',
            'frequency' => ['sometimes', Rule::in(['hourly', 'daily', 'weekly', 'manual'])],
            'preferred_time' => 'nullable|date_format:H:i',
            'max_cloud_cover' => 'sometimes|integer|between:0,100',
            'is_active' => 'sometimes|boolean',
            'alert_rules' => 'nullable|array',
        ]);

        $zone->update($validated);

        return response()->json($zone);
    }

    /**
     * Eliminar zona
     */
    public function destroy(Request $request, SatelliteZone $zone): JsonResponse
    {
        if ($zone->user_id !== $request->user()->id) {
            return response()->json(['error' => 'No autorizado'], 403);
        }

        // Eliminar imágenes del storage
        foreach ($zone->images as $image) {
            if ($image->image_path && !str_starts_with($image->image_path, 'http')) {
                Storage::disk('public')->delete($image->image_path);
            }
            if ($image->thumbnail_path && !str_starts_with($image->thumbnail_path, 'http')) {
                Storage::disk('public')->delete($image->thumbnail_path);
            }
        }

        $zone->delete();

        return response()->json(['message' => 'Zona eliminada']);
    }

    /**
     * Solicitar análisis manual de una zona
     * Envía comando al worker de Python vía Redis
     */
    public function analyze(Request $request, SatelliteZone $zone): JsonResponse
    {
        if ($zone->user_id !== $request->user()->id) {
            return response()->json(['error' => 'No autorizado'], 403);
        }

        // Verificar que no esté ya procesando
        $pendingImages = $zone->images()->where('status', 'processing')->exists();
        if ($pendingImages) {
            return response()->json([
                'error' => 'Ya hay un análisis en progreso',
                'status' => 'processing'
            ], 409);
        }

        // Crear registro de imagen pendiente
        $image = SatelliteImage::create([
            'satellite_zone_id' => $zone->id,
            'image_path' => null, // Se llenará cuando el worker descargue
            'status' => 'pending',
            'satellite_source' => 'sentinel-2',
        ]);

        // Enviar comando al worker Python
        $command = [
            'action' => 'ANALYZE_SATELLITE',
            'zone_id' => $zone->id,
            'image_id' => $image->id,
            'lat' => (float) $zone->latitude,
            'lon' => (float) $zone->longitude,
            'radius_km' => (float) $zone->radius_km,
            'max_cloud_cover' => $zone->max_cloud_cover / 100,
            'prompt' => 'Describe this satellite image. Identify any buildings, vehicles, water bodies, or notable features.',
        ];

        try {
            Redis::publish('satellite_control', json_encode($command));
            
            $zone->update(['last_checked_at' => now()]);

            return response()->json([
                'message' => 'Análisis iniciado',
                'image_id' => $image->id,
                'status' => 'pending'
            ]);
        } catch (\Exception $e) {
            $image->update([
                'status' => 'failed',
                'error_message' => 'Error enviando comando: ' . $e->getMessage()
            ]);

            return response()->json([
                'error' => 'Error iniciando análisis',
                'details' => $e->getMessage()
            ], 500);
        }
    }

    /**
     * Obtener historial de imágenes de una zona
     */
    public function images(Request $request, SatelliteZone $zone): JsonResponse
    {
        if ($zone->user_id !== $request->user()->id) {
            return response()->json(['error' => 'No autorizado'], 403);
        }

        $images = $zone->images()
            ->orderByDesc('captured_at')
            ->paginate(20);

        return response()->json($images);
    }

    /**
     * Obtener la imagen más reciente de una zona
     */
    public function latestImage(Request $request, SatelliteZone $zone): JsonResponse
    {
        if ($zone->user_id !== $request->user()->id) {
            return response()->json(['error' => 'No autorizado'], 403);
        }

        $image = $zone->images()->latest('captured_at')->first();
        
        if (!$image) {
            return response()->json(['error' => 'No hay imágenes disponibles'], 404);
        }

        return response()->json($image);
    }

    /**
     * Obtener alertas de una zona
     */
    public function alerts(Request $request, SatelliteZone $zone): JsonResponse
    {
        if ($zone->user_id !== $request->user()->id) {
            return response()->json(['error' => 'No autorizado'], 403);
        }

        $alerts = $zone->alerts()
            ->with('image')
            ->orderByDesc('created_at')
            ->paginate(50);

        return response()->json($alerts);
    }

    /**
     * Marcar alertas como leídas
     */
    public function markAlertsRead(Request $request, SatelliteZone $zone): JsonResponse
    {
        if ($zone->user_id !== $request->user()->id) {
            return response()->json(['error' => 'No autorizado'], 403);
        }

        $zone->alerts()->where('is_read', false)->update(['is_read' => true]);

        return response()->json(['message' => 'Alertas marcadas como leídas']);
    }

    /**
     * Obtener estadísticas globales de satélite para el usuario
     */
    public function stats(Request $request): JsonResponse
    {
        $userId = $request->user()->id;

        $stats = [
            'total_zones' => SatelliteZone::where('user_id', $userId)->count(),
            'active_zones' => SatelliteZone::where('user_id', $userId)->active()->count(),
            'total_images' => SatelliteImage::whereHas('zone', fn($q) => $q->where('user_id', $userId))->count(),
            'unread_alerts' => SatelliteAlert::whereHas('zone', fn($q) => $q->where('user_id', $userId))->unread()->count(),
            'recent_alerts' => SatelliteAlert::whereHas('zone', fn($q) => $q->where('user_id', $userId))->recent()->count(),
        ];

        return response()->json($stats);
    }

    /**
     * Webhook para recibir resultados del worker Python
     * (Llamado internamente por el worker)
     */
    public function workerCallback(Request $request): JsonResponse
    {
        // Validar que viene del worker (API Key interna)
        $workerKey = $request->header('X-WORKER-KEY');
        if ($workerKey !== config('services.worker.key')) {
            return response()->json(['error' => 'No autorizado'], 401);
        }

        $validated = $request->validate([
            'image_id' => 'required|integer|exists:satellite_images,id',
            'status' => 'required|in:completed,failed',
            'image_path' => 'nullable|string',
            'captured_at' => 'nullable|date',
            'cloud_cover' => 'nullable|integer',
            'detections' => 'nullable|array',
            'ai_description' => 'nullable|string',
            'changes_detected' => 'nullable|array',
            'error_message' => 'nullable|string',
        ]);

        $image = SatelliteImage::findOrFail($validated['image_id']);
        
        $image->update([
            'status' => $validated['status'],
            'image_path' => $validated['image_path'] ?? $image->image_path,
            'captured_at' => $validated['captured_at'] ?? now(),
            'cloud_cover' => $validated['cloud_cover'],
            'detections' => $validated['detections'],
            'ai_description' => $validated['ai_description'],
            'changes_detected' => $validated['changes_detected'],
            'error_message' => $validated['error_message'],
        ]);

        // Actualizar zona
        if ($validated['status'] === 'completed') {
            $image->zone->update([
                'last_image_at' => now(),
                'last_image_path' => $validated['image_path'],
                'last_analysis' => [
                    'detections' => $validated['detections'],
                    'description' => $validated['ai_description'],
                    'timestamp' => now()->toIso8601String(),
                ],
            ]);

            // Generar alertas si se detectaron cambios
            if (!empty($validated['changes_detected'])) {
                foreach ($validated['changes_detected'] as $change) {
                    SatelliteAlert::create([
                        'satellite_zone_id' => $image->satellite_zone_id,
                        'satellite_image_id' => $image->id,
                        'alert_type' => $change['type'] ?? 'change_detected',
                        'severity' => $change['severity'] ?? 'info',
                        'message' => $change['message'] ?? 'Cambio detectado en la zona',
                        'details' => $change,
                    ]);
                }
            }
        }

        return response()->json(['message' => 'Callback procesado', 'image_id' => $image->id]);
    }

    /**
     * Recibir resultado de análisis satelital del worker Python
     * Endpoint: POST /api/worker/satellite-result
     */
    public function storeWorkerResult(Request $request): JsonResponse
    {
        // Validar API Key del worker
        $workerKey = $request->header('X-WORKER-KEY');
        $expectedKey = config('services.worker.key', env('WORKER_API_KEY'));
        
        if (!$workerKey || $workerKey !== $expectedKey) {
            return response()->json(['error' => 'No autorizado'], 401);
        }

        $validated = $request->validate([
            'zone_id' => 'required|integer|exists:satellite_zones,id',
            'image_id' => 'nullable|integer|exists:satellite_images,id',
            'user_id' => 'required|integer',
            'detections' => 'nullable|array',
            'image_base64' => 'nullable|string',
            'vlm_analysis' => 'nullable|string',
            'cloud_cover' => 'nullable|numeric',
            'captured_at' => 'nullable|string',
        ]);

        $zone = SatelliteZone::find($validated['zone_id']);
        if (!$zone) {
            return response()->json(['error' => 'Zona no encontrada'], 404);
        }

        // Guardar imagen en storage
        $imagePath = null;
        $thumbnailPath = null;
        
        if (!empty($validated['image_base64'])) {
            $imageData = base64_decode($validated['image_base64']);
            $filename = "satellite_{$zone->id}_" . time() . '.jpg';
            $imagePath = "satellite/{$filename}";
            
            Storage::disk('public')->put($imagePath, $imageData);
            
            // Crear thumbnail
            try {
                $image = imagecreatefromstring($imageData);
                if ($image) {
                    $thumbWidth = 256;
                    $thumbHeight = 256;
                    $thumb = imagecreatetruecolor($thumbWidth, $thumbHeight);
                    imagecopyresampled($thumb, $image, 0, 0, 0, 0, $thumbWidth, $thumbHeight, imagesx($image), imagesy($image));
                    
                    ob_start();
                    imagejpeg($thumb, null, 80);
                    $thumbData = ob_get_clean();
                    
                    $thumbnailPath = "satellite/thumbs/{$filename}";
                    Storage::disk('public')->put($thumbnailPath, $thumbData);
                    
                    imagedestroy($image);
                    imagedestroy($thumb);
                }
            } catch (\Exception $e) {
                // Ignorar error de thumbnail
            }
        }

        // Si tenemos image_id, actualizar el registro existente; si no, crear nuevo
        if (!empty($validated['image_id'])) {
            $satelliteImage = SatelliteImage::find($validated['image_id']);
            if ($satelliteImage) {
                $satelliteImage->update([
                    'image_path' => $imagePath ?? $satelliteImage->image_path,
                    'thumbnail_path' => $thumbnailPath ?? $satelliteImage->thumbnail_path,
                    'cloud_cover' => $validated['cloud_cover'] ?? 0,
                    'captured_at' => $validated['captured_at'] ? \Carbon\Carbon::parse($validated['captured_at']) : now(),
                    'status' => 'completed',
                    'analysis_result' => $validated['detections'] ?? [],
                    'ai_description' => $validated['vlm_analysis'] ?? null,
                ]);
            }
        } else {
            // Crear nuevo registro de imagen
            $satelliteImage = SatelliteImage::create([
                'satellite_zone_id' => $zone->id,
                'satellite_source' => 'sentinel-2',
                'image_path' => $imagePath,
                'thumbnail_path' => $thumbnailPath,
                'cloud_cover' => $validated['cloud_cover'] ?? 0,
                'captured_at' => $validated['captured_at'] ? \Carbon\Carbon::parse($validated['captured_at']) : now(),
                'status' => 'completed',
                'analysis_result' => $validated['detections'] ?? [],
                'ai_description' => $validated['vlm_analysis'] ?? null,
            ]);
        }

        // Actualizar zona con última imagen
        $zone->update([
            'last_image_at' => now(),
            'last_image_path' => $imagePath,
            'last_analysis' => [
                'detections' => $validated['detections'] ?? [],
                'timestamp' => now()->toIso8601String(),
            ],
        ]);

        // Generar alertas si hay detecciones importantes
        $detections = $validated['detections'] ?? [];
        if (count($detections) > 0) {
            // Verificar contra reglas de alerta de la zona
            $alertRules = $zone->alert_rules ?? [];
            
            foreach ($detections as $detection) {
                $className = $detection['class_name'] ?? 'unknown';
                $confidence = $detection['confidence'] ?? 0;
                
                // Crear alerta si la clase está en las reglas o es importante
                $importantClasses = ['person', 'car', 'truck', 'boat', 'airplane'];
                if (in_array(strtolower($className), $importantClasses) && $confidence > 0.5) {
                    SatelliteAlert::create([
                        'satellite_zone_id' => $zone->id,
                        'satellite_image_id' => $satelliteImage->id,
                        'alert_type' => 'object_detected',
                        'severity' => $confidence > 0.8 ? 'high' : 'medium',
                        'message' => "Se detectó {$className} con {$confidence}% de confianza",
                        'details' => $detection,
                    ]);
                }
            }
        }

        return response()->json([
            'message' => 'Resultado satelital guardado',
            'image_id' => $satelliteImage->id,
            'detections_count' => count($detections),
        ], 201);
    }

    /**
     * Recibir thumbnail de zona del worker Python
     * Endpoint: POST /api/worker/satellite-thumbnail
     */
    public function storeThumbnail(Request $request): JsonResponse
    {
        // Validar API Key del worker
        $workerKey = $request->header('X-WORKER-KEY');
        $expectedKey = config('services.worker.key', env('WORKER_API_KEY'));
        
        if (!$workerKey || $workerKey !== $expectedKey) {
            return response()->json(['error' => 'No autorizado'], 401);
        }

        $validated = $request->validate([
            'zone_id' => 'required|integer|exists:satellite_zones,id',
            'thumbnail_base64' => 'required|string',
        ]);

        $zone = SatelliteZone::find($validated['zone_id']);
        if (!$zone) {
            return response()->json(['error' => 'Zona no encontrada'], 404);
        }

        // Guardar thumbnail en storage
        $imageData = base64_decode($validated['thumbnail_base64']);
        $filename = "zone_thumb_{$zone->id}_" . time() . '.jpg';
        $thumbnailPath = "satellite/zone_thumbs/{$filename}";
        
        Storage::disk('public')->put($thumbnailPath, $imageData);

        // Actualizar zona con el thumbnail (usar last_image_path si no hay imagen real)
        if (empty($zone->last_image_path)) {
            $zone->update([
                'last_image_path' => $thumbnailPath,
            ]);
        }

        return response()->json([
            'message' => 'Thumbnail guardado',
            'zone_id' => $zone->id,
            'thumbnail_path' => $thumbnailPath,
        ], 201);
    }

    /**
     * Regenerar thumbnails para todas las zonas del usuario
     */
    public function regenerateThumbnails(Request $request): JsonResponse
    {
        $zones = SatelliteZone::where('user_id', $request->user()->id)->get();
        $count = 0;

        foreach ($zones as $zone) {
            try {
                $command = [
                    'action' => 'GET_ZONE_THUMBNAIL',
                    'zone_id' => $zone->id,
                    'lat' => (float) $zone->latitude,
                    'lon' => (float) $zone->longitude,
                    'radius_km' => (float) $zone->radius_km,
                ];
                Redis::publish('satellite_control', json_encode($command));
                $count++;
            } catch (\Exception $e) {
                \Log::warning("Could not request thumbnail for zone {$zone->id}: " . $e->getMessage());
            }
        }

        return response()->json([
            'message' => "Solicitados $count thumbnails",
            'count' => $count,
        ]);
    }
}
