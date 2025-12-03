<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use App\Models\Camera;
use Illuminate\Support\Facades\Redis;

class SceneAnalysisController extends Controller
{
    /**
     * Inicia el análisis de escena para una cámara
     * Captura frames durante el primer minuto y analiza la escena
     */
    public function analyzeScene(Request $request, Camera $camera)
    {
        // Verificar propiedad
        if ($camera->user_id !== $request->user()->id) {
            return response()->json(['error' => 'No autorizado'], 403);
        }

        // Publicar comando para analizar escena
        $message = json_encode([
            'action' => 'analyze_scene',
            'camera_id' => $camera->id,
            'url' => $camera->url,
            'duration_seconds' => 30, // Analizar 30 segundos
        ]);

        Redis::publish('camera_control', $message);

        return response()->json([
            'message' => 'Análisis de escena iniciado',
            'camera_id' => $camera->id,
            'estimated_time' => 30
        ]);
    }

    /**
     * Guarda el resultado del análisis de escena
     * (Llamado por el worker de Python)
     */
    public function saveSceneAnalysis(Request $request, Camera $camera)
    {
        $request->validate([
            'scene_analysis' => 'required|array',
        ]);

        $analysis = $request->input('scene_analysis');
        
        // Generar configuración recomendada basada en el análisis
        $recommended = $this->generateRecommendationsFromAnalysis($camera, $analysis);

        $camera->update([
            'scene_analysis' => $analysis,
            'scene_analyzed_at' => now(),
            'recommended_settings' => $recommended,
        ]);

        return response()->json([
            'message' => 'Análisis guardado',
            'scene_analysis' => $analysis,
            'recommended_settings' => $recommended,
        ]);
    }

    /**
     * Genera recomendaciones basadas en el análisis de escena
     */
    private function generateRecommendationsFromAnalysis(Camera $camera, array $analysis): array
    {
        $recommendations = $camera->generateRecommendedSettings();

        // Ajustar según objetos detectados en la escena
        $detectedObjects = $analysis['detected_objects'] ?? [];
        if (!empty($detectedObjects)) {
            // Agregar clases que ya están en la escena
            $recommendations['detection_classes'] = array_unique(array_merge(
                $recommendations['detection_classes'] ?? [],
                array_keys($detectedObjects)
            ));
        }

        // Ajustar según luminosidad
        $brightness = $analysis['brightness'] ?? 'normal';
        if ($brightness === 'low') {
            $recommendations['confidence_threshold'] = 0.4; // Más sensible en baja luz
            $recommendations['notes'][] = 'Escena con baja iluminación - umbral de confianza reducido';
        }

        // Ajustar según nivel de movimiento
        $motionLevel = $analysis['motion_level'] ?? 'medium';
        if ($motionLevel === 'high') {
            $recommendations['detection_interval_ms'] = 300; // Más frecuente
            $recommendations['tracking'] = true;
            $recommendations['notes'][] = 'Alto nivel de movimiento detectado';
        } elseif ($motionLevel === 'low') {
            $recommendations['detection_interval_ms'] = 1000; // Menos frecuente
            $recommendations['notes'][] = 'Escena estática - intervalo de detección reducido';
        }

        // Detectar si es entrada/salida
        if (isset($analysis['scene_type'])) {
            switch ($analysis['scene_type']) {
                case 'entrance':
                    $recommendations['count_objects'] = true;
                    $recommendations['face_recognition_enabled'] = true;
                    $recommendations['notes'][] = 'Entrada detectada - conteo y reconocimiento habilitados';
                    break;
                case 'parking':
                    $recommendations['detection_classes'] = array_unique(array_merge(
                        $recommendations['detection_classes'] ?? [],
                        ['car', 'truck', 'motorcycle', 'person']
                    ));
                    $recommendations['notes'][] = 'Estacionamiento detectado';
                    break;
                case 'corridor':
                    $recommendations['detect_loitering'] = true;
                    $recommendations['notes'][] = 'Pasillo/corredor - detección de merodeo habilitada';
                    break;
                case 'open_space':
                    $recommendations['depth_enabled'] = true;
                    $recommendations['bev_enabled'] = true;
                    $recommendations['notes'][] = 'Espacio abierto - vista aérea habilitada';
                    break;
            }
        }

        // Detectar densidad de personas
        $personDensity = $analysis['person_density'] ?? 'low';
        if ($personDensity === 'high') {
            $recommendations['tracking'] = true;
            $recommendations['count_objects'] = true;
            $recommendations['notes'][] = 'Alta densidad de personas detectada';
        }

        return $recommendations;
    }

    /**
     * Aplica las recomendaciones a la cámara
     */
    public function applyRecommendations(Request $request, Camera $camera)
    {
        if ($camera->user_id !== $request->user()->id) {
            return response()->json(['error' => 'No autorizado'], 403);
        }

        $recommendations = $camera->recommended_settings;
        
        if (empty($recommendations)) {
            return response()->json(['error' => 'No hay recomendaciones disponibles'], 400);
        }

        // Aplicar solo campos válidos
        $validFields = [
            'detection_classes',
            'confidence_threshold',
            'detection_interval_ms',
            'tracking',
            'face_recognition_enabled',
            'alert_on_unknown_face',
            'count_objects',
            'detect_loitering',
            'depth_enabled',
            'bev_enabled',
        ];

        $toUpdate = [];
        foreach ($validFields as $field) {
            if (isset($recommendations[$field])) {
                $toUpdate[$field] = $recommendations[$field];
            }
        }

        $camera->update($toUpdate);

        return response()->json([
            'message' => 'Recomendaciones aplicadas',
            'applied_settings' => $toUpdate,
        ]);
    }

    /**
     * Completa la configuración del wizard
     */
    public function completeSetup(Request $request, Camera $camera)
    {
        if ($camera->user_id !== $request->user()->id) {
            return response()->json(['error' => 'No autorizado'], 403);
        }

        $request->validate([
            'camera_type' => 'required|in:security,monitoring,traffic,retail,industrial,custom',
            'camera_behavior' => 'required|in:fixed,ptz,patrol,motion_triggered',
            'location_type' => 'required|in:indoor,outdoor,entrance,parking,corridor,warehouse,office,other',
            'primary_goal' => 'required|in:intrusion,counting,behavior,recognition,traffic,safety,general',
        ]);

        $camera->update([
            'camera_type' => $request->camera_type,
            'camera_behavior' => $request->camera_behavior,
            'location_type' => $request->location_type,
            'primary_goal' => $request->primary_goal,
            'setup_completed' => true,
        ]);

        // Generar y guardar configuración recomendada
        $recommended = $camera->generateRecommendedSettings();
        $camera->update(['recommended_settings' => $recommended]);

        return response()->json([
            'message' => 'Configuración completada',
            'camera' => $camera->fresh(),
            'recommended_settings' => $recommended,
        ]);
    }
}
