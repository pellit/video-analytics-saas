<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('cameras', function (Blueprint $table) {
            // FPS de análisis (frames a analizar por segundo)
            // Por defecto 5 FPS para balance entre rendimiento y detección
            $table->integer('analysis_fps')->default(5)->after('detection_interval_ms');
            
            // Overlay settings (para mostrar info en el video)
            $table->boolean('show_analysis_overlay')->default(true)->after('analysis_fps');
        });
    }

    public function down(): void
    {
        Schema::table('cameras', function (Blueprint $table) {
            $table->dropColumn(['analysis_fps', 'show_analysis_overlay']);
        });
    }
};
