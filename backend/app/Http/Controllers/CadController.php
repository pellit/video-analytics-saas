<?php

namespace App\Http\Controllers;

use App\Models\CadProject;
use Illuminate\Http\Request;
use Illuminate\Http\JsonResponse;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Redis;
use Illuminate\Support\Facades\Storage;
use Illuminate\Support\Facades\Log;
use Illuminate\Validation\Rule;

class CadController extends Controller
{
    /**
     * List all CAD projects for the authenticated user.
     */
    public function index(Request $request): JsonResponse
    {
        $query = CadProject::forUser(Auth::id())
            ->orderBy('created_at', 'desc');

        // Filtros opcionales
        if ($request->has('status')) {
            $query->where('status', $request->status);
        }
        if ($request->has('project_type')) {
            $query->ofType($request->project_type);
        }

        $projects = $query->paginate($request->get('per_page', 20));

        return response()->json([
            'success' => true,
            'projects' => $projects->items(),
            'pagination' => [
                'total' => $projects->total(),
                'per_page' => $projects->perPage(),
                'current_page' => $projects->currentPage(),
                'last_page' => $projects->lastPage(),
            ]
        ]);
    }

    /**
     * Get a specific CAD project.
     */
    public function show(int $id): JsonResponse
    {
        $project = CadProject::forUser(Auth::id())->findOrFail($id);

        return response()->json([
            'success' => true,
            'project' => $project,
            'full_analysis' => $project->full_analysis,
        ]);
    }

    /**
     * Upload a new CAD file for analysis.
     */
    public function upload(Request $request): JsonResponse
    {
        $request->validate([
            'file' => 'required|file|max:102400', // Max 100MB
            'name' => 'required|string|max:255',
            'description' => 'nullable|string|max:1000',
            'project_type' => ['nullable', Rule::in(array_keys(CadProject::PROJECT_TYPES))],
        ]);

        $file = $request->file('file');
        $extension = strtolower($file->getClientOriginalExtension());

        // Validar tipo de archivo
        if (!in_array($extension, CadProject::FILE_TYPES)) {
            return response()->json([
                'success' => false,
                'message' => 'Tipo de archivo no soportado. Use: ' . implode(', ', CadProject::FILE_TYPES)
            ], 422);
        }

        // Guardar archivo
        $path = $file->store('cad_files/' . Auth::id(), 'public');

        // Crear proyecto
        $project = CadProject::create([
            'user_id' => Auth::id(),
            'name' => $request->name,
            'description' => $request->description,
            'project_type' => $request->project_type ?? 'architecture',
            'original_filename' => $file->getClientOriginalName(),
            'file_path' => $path,
            'file_type' => $extension,
            'file_size' => $file->getSize(),
            'status' => 'pending',
            'progress' => 0,
            'current_step' => 'En cola de procesamiento...',
        ]);

        // Enviar tarea al worker Python vía Redis
        $this->dispatchToWorker($project);

        return response()->json([
            'success' => true,
            'message' => 'Archivo subido correctamente. El análisis comenzará en breve.',
            'project' => $project,
        ], 201);
    }

    /**
     * Update project metadata (name, description, tags).
     */
    public function update(Request $request, int $id): JsonResponse
    {
        $project = CadProject::forUser(Auth::id())->findOrFail($id);

        $request->validate([
            'name' => 'sometimes|string|max:255',
            'description' => 'nullable|string|max:1000',
            'project_type' => ['nullable', Rule::in(array_keys(CadProject::PROJECT_TYPES))],
            'tags' => 'nullable|array',
        ]);

        $project->update($request->only(['name', 'description', 'project_type', 'tags']));

        return response()->json([
            'success' => true,
            'project' => $project->fresh(),
        ]);
    }

    /**
     * Delete a CAD project.
     */
    public function destroy(int $id): JsonResponse
    {
        $project = CadProject::forUser(Auth::id())->findOrFail($id);

        // Eliminar archivos
        if ($project->file_path && Storage::disk('public')->exists($project->file_path)) {
            Storage::disk('public')->delete($project->file_path);
        }
        if ($project->render_image_path && Storage::disk('public')->exists($project->render_image_path)) {
            Storage::disk('public')->delete($project->render_image_path);
        }
        if ($project->render_thumbnail_path && Storage::disk('public')->exists($project->render_thumbnail_path)) {
            Storage::disk('public')->delete($project->render_thumbnail_path);
        }

        $project->delete();

        return response()->json([
            'success' => true,
            'message' => 'Proyecto eliminado correctamente.',
        ]);
    }

    /**
     * Re-analyze a project (retry or update analysis).
     */
    public function reanalyze(int $id): JsonResponse
    {
        $project = CadProject::forUser(Auth::id())->findOrFail($id);

        // Reset status
        $project->update([
            'status' => 'pending',
            'progress' => 0,
            'current_step' => 'Re-analizando...',
            'error_message' => null,
        ]);

        // Dispatch to worker
        $this->dispatchToWorker($project);

        return response()->json([
            'success' => true,
            'message' => 'Re-análisis iniciado.',
            'project' => $project->fresh(),
        ]);
    }

    /**
     * Get project status (for polling).
     */
    public function status(int $id): JsonResponse
    {
        $project = CadProject::forUser(Auth::id())->findOrFail($id);

        return response()->json([
            'success' => true,
            'status' => $project->status,
            'progress' => $project->progress,
            'current_step' => $project->current_step,
            'error_message' => $project->error_message,
            'is_processing' => $project->isProcessing(),
            'is_completed' => $project->isCompleted(),
        ]);
    }

    /**
     * Get available project types.
     */
    public function projectTypes(): JsonResponse
    {
        return response()->json([
            'success' => true,
            'types' => CadProject::PROJECT_TYPES,
        ]);
    }

    /**
     * Get analytics summary for user's projects.
     * (Placeholder for future analytics feature)
     */
    public function analytics(Request $request): JsonResponse
    {
        $userId = Auth::id();

        $stats = [
            'total_projects' => CadProject::forUser($userId)->count(),
            'completed' => CadProject::forUser($userId)->completed()->count(),
            'processing' => CadProject::forUser($userId)->processing()->count(),
            'by_type' => CadProject::forUser($userId)
                ->selectRaw('project_type, COUNT(*) as count')
                ->groupBy('project_type')
                ->pluck('count', 'project_type'),
            'recent_projects' => CadProject::forUser($userId)
                ->orderBy('created_at', 'desc')
                ->limit(5)
                ->get(['id', 'name', 'status', 'created_at']),
        ];

        return response()->json([
            'success' => true,
            'analytics' => $stats,
        ]);
    }

    /**
     * Callback endpoint for worker to update project status.
     * (Called by Python worker via internal API)
     */
    public function workerCallback(Request $request): JsonResponse
    {
        // Validar key del worker
        $workerKey = $request->header('X-WORKER-KEY');
        if ($workerKey !== config('services.worker.key', 'worker-secret-key')) {
            return response()->json(['error' => 'Unauthorized'], 401);
        }

        $request->validate([
            'project_id' => 'required|integer',
            'status' => 'sometimes|string',
            'progress' => 'sometimes|integer|min:0|max:100',
            'current_step' => 'sometimes|string',
            'error_message' => 'sometimes|nullable|string',
            'render_image_path' => 'sometimes|nullable|string',
            'render_thumbnail_path' => 'sometimes|nullable|string',
            'analysis_general' => 'sometimes|nullable|array',
            'analysis_rooms' => 'sometimes|nullable|array',
            'analysis_safety' => 'sometimes|nullable|array',
            'analysis_structural' => 'sometimes|nullable|array',
            'analysis_dimensions' => 'sometimes|nullable|array',
            'analysis_materials' => 'sometimes|nullable|array',
            'metadata' => 'sometimes|nullable|array',
        ]);

        $project = CadProject::findOrFail($request->project_id);

        $updateData = $request->only([
            'status', 'progress', 'current_step', 'error_message',
            'render_image_path', 'render_thumbnail_path',
            'analysis_general', 'analysis_rooms', 'analysis_safety',
            'analysis_structural', 'analysis_dimensions', 'analysis_materials',
            'metadata'
        ]);

        // Handle processing times
        if ($request->status === 'rendering' && !$project->processing_started_at) {
            $updateData['processing_started_at'] = now();
        }
        if ($request->status === 'completed') {
            $updateData['processing_completed_at'] = now();
            if ($project->processing_started_at) {
                $updateData['processing_duration_seconds'] = now()->diffInSeconds($project->processing_started_at);
            }
        }

        $project->update($updateData);

        Log::info("CAD Worker callback for project {$project->id}: status={$project->status}, progress={$project->progress}%");

        return response()->json([
            'success' => true,
            'project_id' => $project->id,
        ]);
    }

    /**
     * Dispatch project to Python worker via Redis.
     */
    private function dispatchToWorker(CadProject $project): void
    {
        try {
            // Con volumen compartido:
            // Laravel storage: /var/www/html/storage  -> app_storage volume
            // Python storage:  /app/storage           -> app_storage volume
            // El file_path ya es relativo (ej: "cad_files/1/archivo.dxf")
            // Python lo accede como /app/storage/app/public/{file_path}
            $message = json_encode([
                'action' => 'PROCESS_CAD',
                'project_id' => $project->id,
                'file_path' => '/app/storage/app/public/' . $project->file_path,
                'file_type' => $project->file_type,
                'project_type' => $project->project_type,
                'user_id' => $project->user_id,
                'callback_url' => config('app.url') . '/api/internal/cad/callback',
            ]);

            Redis::publish('cad_control', $message);
            Log::info("Dispatched CAD project {$project->id} to worker");
        } catch (\Exception $e) {
            Log::error("Failed to dispatch CAD project {$project->id}: " . $e->getMessage());
            $project->update([
                'status' => 'error',
                'error_message' => 'Error al enviar tarea al worker: ' . $e->getMessage(),
            ]);
        }
    }
}
