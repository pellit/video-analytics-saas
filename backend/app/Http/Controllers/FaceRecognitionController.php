<?php

namespace App\Http\Controllers;

use App\Models\KnownFace;
use App\Models\FaceDetection;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Storage;

class FaceRecognitionController extends Controller
{
    /**
     * Get all known faces for the authenticated user.
     */
    public function listKnownFaces(Request $request)
    {
        $faces = KnownFace::forUser($request->user()->id)
            ->orderBy('name')
            ->get()
            ->map(function ($face) {
                return [
                    'id' => $face->id,
                    'name' => $face->name,
                    'label' => $face->label,
                    'face_image_url' => $face->face_image_path 
                        ? Storage::url($face->face_image_path) 
                        : null,
                    'detection_count' => $face->detection_count,
                    'last_seen_at' => $face->last_seen_at,
                    'created_at' => $face->created_at,
                ];
            });

        return response()->json($faces);
    }

    /**
     * Get a specific known face with embedding.
     */
    public function getKnownFace(Request $request, $id)
    {
        $face = KnownFace::forUser($request->user()->id)->findOrFail($id);
        
        return response()->json([
            'id' => $face->id,
            'name' => $face->name,
            'label' => $face->label,
            'face_image_url' => $face->face_image_path 
                ? Storage::url($face->face_image_path) 
                : null,
            'detection_count' => $face->detection_count,
            'last_seen_at' => $face->last_seen_at,
            'metadata' => $face->metadata,
            'created_at' => $face->created_at,
        ]);
    }

    /**
     * Create a new known face (from manual upload or from detection).
     */
    public function createKnownFace(Request $request)
    {
        $validated = $request->validate([
            'name' => 'required|string|max:255',
            'label' => 'nullable|string|max:255',
            'face_image' => 'nullable|image|max:2048', // 2MB max
            'detection_id' => 'nullable|exists:face_detections,id',
            'embedding' => 'nullable|array',
        ]);

        $face = new KnownFace();
        $face->user_id = $request->user()->id;
        $face->name = $validated['name'];
        $face->label = $validated['label'] ?? null;

        // If creating from a detection, copy embedding and image
        if (!empty($validated['detection_id'])) {
            $detection = FaceDetection::findOrFail($validated['detection_id']);
            $face->embedding = $detection->embedding;
            $face->face_image_path = $detection->face_image_path;
            
            // Mark the detection as identified
            $detection->update([
                'identified' => true,
                'known_face_id' => null, // Will be updated after save
            ]);
        }

        // If embedding provided directly
        if (!empty($validated['embedding'])) {
            $face->embedding = $validated['embedding'];
        }

        // Handle uploaded image
        if ($request->hasFile('face_image')) {
            $path = $request->file('face_image')->store('faces', 'public');
            $face->face_image_path = $path;
        }

        $face->save();

        // Update detection with known_face_id if applicable
        if (!empty($validated['detection_id'])) {
            FaceDetection::where('id', $validated['detection_id'])
                ->update(['known_face_id' => $face->id]);
        }

        return response()->json([
            'message' => 'Cara registrada correctamente',
            'face' => [
                'id' => $face->id,
                'name' => $face->name,
                'label' => $face->label,
                'face_image_url' => $face->face_image_path 
                    ? Storage::url($face->face_image_path) 
                    : null,
            ]
        ], 201);
    }

    /**
     * Update a known face (name, label).
     */
    public function updateKnownFace(Request $request, $id)
    {
        $face = KnownFace::forUser($request->user()->id)->findOrFail($id);

        $validated = $request->validate([
            'name' => 'sometimes|string|max:255',
            'label' => 'nullable|string|max:255',
            'face_image' => 'nullable|image|max:2048',
        ]);

        if (isset($validated['name'])) {
            $face->name = $validated['name'];
        }
        if (array_key_exists('label', $validated)) {
            $face->label = $validated['label'];
        }

        if ($request->hasFile('face_image')) {
            // Delete old image if exists
            if ($face->face_image_path) {
                Storage::disk('public')->delete($face->face_image_path);
            }
            $path = $request->file('face_image')->store('faces', 'public');
            $face->face_image_path = $path;
        }

        $face->save();

        return response()->json([
            'message' => 'Cara actualizada correctamente',
            'face' => [
                'id' => $face->id,
                'name' => $face->name,
                'label' => $face->label,
                'face_image_url' => $face->face_image_path 
                    ? Storage::url($face->face_image_path) 
                    : null,
            ]
        ]);
    }

    /**
     * Delete a known face.
     */
    public function deleteKnownFace(Request $request, $id)
    {
        $face = KnownFace::forUser($request->user()->id)->findOrFail($id);
        
        // Delete associated image
        if ($face->face_image_path) {
            Storage::disk('public')->delete($face->face_image_path);
        }

        // Unlink detections (set known_face_id to null)
        FaceDetection::where('known_face_id', $face->id)
            ->update(['known_face_id' => null, 'identified' => false]);

        $face->delete();

        return response()->json(['message' => 'Cara eliminada correctamente']);
    }

    /**
     * Get face detections for a specific camera.
     */
    public function getDetectionsByCamera(Request $request, $cameraId)
    {
        $limit = min($request->query('limit', 20), 100);
        $identified = $request->query('identified'); // 'true', 'false', or null for all

        $query = FaceDetection::with('knownFace:id,name')
            ->where('camera_id', $cameraId)
            ->orderBy('created_at', 'desc');

        if ($identified === 'true') {
            $query->identified();
        } elseif ($identified === 'false') {
            $query->unidentified();
        }

        $detections = $query->limit($limit)->get()->map(function ($det) {
            return [
                'id' => $det->id,
                'camera_id' => $det->camera_id,
                'confidence' => $det->confidence,
                'similarity_score' => $det->similarity_score,
                'face_image_url' => $det->face_image_path 
                    ? Storage::url($det->face_image_path) 
                    : null,
                'face_image_base64' => null, // Not stored, only realtime
                'bbox' => $det->bbox,
                'identified' => $det->identified,
                'matched_name' => $det->knownFace ? $det->knownFace->name : null,
                'known_face' => $det->knownFace ? [
                    'id' => $det->knownFace->id,
                    'name' => $det->knownFace->name,
                ] : null,
                'created_at' => $det->created_at,
            ];
        });

        return response()->json(['detections' => $detections]);
    }

    /**
     * Get recent face detections for a camera (unidentified faces for labeling).
     */
    public function getRecentDetections(Request $request)
    {
        $cameraId = $request->query('camera_id');
        $identified = $request->query('identified'); // 'true', 'false', or null for all
        $limit = min($request->query('limit', 20), 100);

        $query = FaceDetection::with('knownFace:id,name')
            ->orderBy('created_at', 'desc');

        if ($cameraId) {
            $query->forCamera($cameraId);
        }

        if ($identified === 'true') {
            $query->identified();
        } elseif ($identified === 'false') {
            $query->unidentified();
        }

        $detections = $query->limit($limit)->get()->map(function ($det) {
            return [
                'id' => $det->id,
                'camera_id' => $det->camera_id,
                'confidence' => $det->confidence,
                'similarity_score' => $det->similarity_score,
                'face_image_url' => $det->face_image_path 
                    ? Storage::url($det->face_image_path) 
                    : null,
                'bbox' => $det->bbox,
                'identified' => $det->identified,
                'known_face' => $det->knownFace ? [
                    'id' => $det->knownFace->id,
                    'name' => $det->knownFace->name,
                ] : null,
                'created_at' => $det->created_at,
            ];
        });

        return response()->json($detections);
    }

    /**
     * Assign a detection to a known face (labeling).
     */
    public function assignDetectionToFace(Request $request, $detectionId)
    {
        $validated = $request->validate([
            'known_face_id' => 'required|exists:known_faces,id',
        ]);

        $detection = FaceDetection::findOrFail($detectionId);
        $knownFace = KnownFace::forUser($request->user()->id)
            ->findOrFail($validated['known_face_id']);

        $detection->update([
            'known_face_id' => $knownFace->id,
            'identified' => true,
        ]);

        // Update known face stats
        $knownFace->increment('detection_count');
        $knownFace->update(['last_seen_at' => now()]);

        // Optionally update embedding with average (improves recognition over time)
        // This is a simple approach - more sophisticated methods exist
        if ($detection->embedding && $knownFace->embedding) {
            // For now, we keep the original embedding
            // In production, you might want to implement embedding averaging or clustering
        }

        return response()->json([
            'message' => 'Detección asignada correctamente',
            'detection' => [
                'id' => $detection->id,
                'known_face' => [
                    'id' => $knownFace->id,
                    'name' => $knownFace->name,
                ]
            ]
        ]);
    }

    /**
     * Create a new known face from an unidentified detection.
     */
    public function createFaceFromDetection(Request $request, $detectionId)
    {
        $validated = $request->validate([
            'name' => 'required|string|max:255',
            'label' => 'nullable|string|max:255',
        ]);

        $detection = FaceDetection::findOrFail($detectionId);

        // Create new known face
        $face = KnownFace::create([
            'user_id' => $request->user()->id,
            'name' => $validated['name'],
            'label' => $validated['label'] ?? null,
            'embedding' => $detection->embedding,
            'face_image_path' => $detection->face_image_path,
            'detection_count' => 1,
            'last_seen_at' => now(),
        ]);

        // Link detection to the new face
        $detection->update([
            'known_face_id' => $face->id,
            'identified' => true,
        ]);

        return response()->json([
            'message' => 'Nueva cara registrada desde detección',
            'face' => [
                'id' => $face->id,
                'name' => $face->name,
                'label' => $face->label,
                'face_image_url' => $face->face_image_path 
                    ? Storage::url($face->face_image_path) 
                    : null,
            ]
        ], 201);
    }

    /**
     * Worker endpoint: Record a face detection from AI engine.
     * This should be called by the AI worker, not authenticated users.
     */
    public function recordDetection(Request $request)
    {
        // Verify worker API key
        $workerKey = $request->header('X-WORKER-KEY');
        if ($workerKey !== config('services.worker.api_key')) {
            return response()->json(['error' => 'Unauthorized'], 401);
        }

        $validated = $request->validate([
            'camera_id' => 'required|exists:cameras,id',
            'embedding' => 'nullable|array',
            'face_image_base64' => 'nullable|string',
            'confidence' => 'required|numeric|min:0|max:1',
            'bbox' => 'nullable|array',
        ]);

        // Save face image if provided
        $imagePath = null;
        if (!empty($validated['face_image_base64'])) {
            $imageData = base64_decode($validated['face_image_base64']);
            $filename = 'detections/' . uniqid() . '_' . time() . '.jpg';
            Storage::disk('public')->put($filename, $imageData);
            $imagePath = $filename;
        }

        // Try to match with known faces
        $camera = \App\Models\Camera::findOrFail($validated['camera_id']);
        $userId = $camera->user_id;
        
        $knownFaceId = null;
        $identified = false;
        $similarityScore = null;

        if (!empty($validated['embedding'])) {
            $match = KnownFace::findBestMatch($validated['embedding'], $userId, 0.6);
            if ($match) {
                $knownFaceId = $match['face']->id;
                $similarityScore = $match['similarity'];
                $identified = true;

                // Update known face stats
                $match['face']->increment('detection_count');
                $match['face']->update(['last_seen_at' => now()]);
            }
        }

        // Create detection record
        $detection = FaceDetection::create([
            'camera_id' => $validated['camera_id'],
            'known_face_id' => $knownFaceId,
            'embedding' => $validated['embedding'] ?? null,
            'face_image_path' => $imagePath,
            'confidence' => $validated['confidence'],
            'similarity_score' => $similarityScore,
            'bbox' => $validated['bbox'] ?? null,
            'identified' => $identified,
        ]);

        return response()->json([
            'detection_id' => $detection->id,
            'identified' => $identified,
            'known_face_id' => $knownFaceId,
            'similarity_score' => $similarityScore,
        ], 201);
    }
}
