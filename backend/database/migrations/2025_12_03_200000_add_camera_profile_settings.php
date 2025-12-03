<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Campos de configuración de perfil de cámara
     * Basados en las preguntas del asistente de configuración
     */
    public function up(): void
    {
        Schema::table('cameras', function (Blueprint $table) {
            // Tipo de cámara
            $table->enum('camera_type', ['security', 'monitoring', 'traffic', 'retail', 'industrial', 'custom'])
                ->default('security')
                ->after('url');
            
            // Comportamiento de la cámara
            $table->enum('camera_behavior', ['fixed', 'ptz', 'patrol', 'motion_triggered'])
                ->default('fixed')
                ->after('camera_type');
            
            // Ubicación
            $table->enum('location_type', ['indoor', 'outdoor', 'entrance', 'parking', 'corridor', 'warehouse', 'office', 'other'])
                ->default('indoor')
                ->after('camera_behavior');
            
            // Objetivo principal de detección
            $table->enum('primary_goal', ['intrusion', 'counting', 'behavior', 'recognition', 'traffic', 'safety', 'general'])
                ->default('general')
                ->after('location_type');
            
            // Configuración de análisis
            $table->float('confidence_threshold')->default(0.5)->after('primary_goal');
            $table->integer('detection_interval_ms')->default(500)->after('confidence_threshold'); // Cada cuántos ms analizar
            $table->boolean('alert_on_unknown_face')->default(false)->after('detection_interval_ms');
            $table->boolean('count_objects')->default(false)->after('alert_on_unknown_face');
            $table->boolean('detect_loitering')->default(false)->after('count_objects');
            $table->integer('loitering_threshold_seconds')->default(60)->after('detect_loitering');
            
            // Análisis de escena (resultado del análisis automático inicial)
            $table->json('scene_analysis')->nullable()->after('loitering_threshold_seconds');
            $table->timestamp('scene_analyzed_at')->nullable()->after('scene_analysis');
            
            // Configuración recomendada por el sistema
            $table->json('recommended_settings')->nullable()->after('scene_analyzed_at');
            
            // Estado del wizard de configuración
            $table->boolean('setup_completed')->default(false)->after('recommended_settings');
        });
    }

    public function down(): void
    {
        Schema::table('cameras', function (Blueprint $table) {
            $table->dropColumn([
                'camera_type',
                'camera_behavior', 
                'location_type',
                'primary_goal',
                'confidence_threshold',
                'detection_interval_ms',
                'alert_on_unknown_face',
                'count_objects',
                'detect_loitering',
                'loitering_threshold_seconds',
                'scene_analysis',
                'scene_analyzed_at',
                'recommended_settings',
                'setup_completed'
            ]);
        });
    }
};
