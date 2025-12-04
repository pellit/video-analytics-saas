<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Migración para zonas satelitales.
     * Las zonas satelitales son como "cámaras lentas" que obtienen imágenes
     * de Sentinel Hub cada cierto tiempo en lugar de streaming continuo.
     */
    public function up(): void
    {
        Schema::create('satellite_zones', function (Blueprint $table) {
            $table->id();
            $table->foreignId('user_id')->constrained()->onDelete('cascade');
            
            // Información básica
            $table->string('name');
            $table->text('description')->nullable();
            
            // Coordenadas del centro de la zona
            $table->decimal('latitude', 10, 7);  // -90 a 90
            $table->decimal('longitude', 11, 7); // -180 a 180
            $table->decimal('radius_km', 5, 2)->default(1.0); // Radio en km
            
            // Configuración de monitoreo
            $table->enum('frequency', ['hourly', 'daily', 'weekly', 'manual'])->default('daily');
            $table->time('preferred_time')->nullable(); // Hora preferida para actualización
            $table->integer('max_cloud_cover')->default(20); // % máximo de nubes
            
            // Estado
            $table->boolean('is_active')->default(true);
            $table->timestamp('last_checked_at')->nullable();
            $table->timestamp('last_image_at')->nullable();
            
            // Última imagen obtenida
            $table->string('last_image_path')->nullable();
            $table->json('last_analysis')->nullable(); // Resultado del análisis IA
            
            // Alertas configuradas
            $table->json('alert_rules')->nullable();
            
            $table->timestamps();
            
            // Índices
            $table->index(['user_id', 'is_active']);
            $table->index('last_checked_at');
        });
        
        // Historial de imágenes satelitales
        Schema::create('satellite_images', function (Blueprint $table) {
            $table->id();
            $table->foreignId('satellite_zone_id')->constrained()->onDelete('cascade');
            
            // Imagen
            $table->string('image_path');
            $table->string('thumbnail_path')->nullable();
            
            // Metadatos de la imagen
            $table->timestamp('captured_at')->nullable(); // Fecha de captura del satélite
            $table->integer('cloud_cover')->nullable(); // % de nubes
            $table->string('satellite_source')->default('sentinel-2');
            
            // Análisis IA
            $table->json('detections')->nullable(); // Detecciones YOLO
            $table->text('ai_description')->nullable(); // Descripción de Moondream
            $table->json('changes_detected')->nullable(); // Comparación con imagen anterior
            
            // Estado del análisis
            $table->enum('status', ['pending', 'processing', 'completed', 'failed'])->default('pending');
            $table->text('error_message')->nullable();
            
            $table->timestamps();
            
            // Índices
            $table->index(['satellite_zone_id', 'captured_at']);
            $table->index('status');
        });
        
        // Alertas generadas por zonas satelitales
        Schema::create('satellite_alerts', function (Blueprint $table) {
            $table->id();
            $table->foreignId('satellite_zone_id')->constrained()->onDelete('cascade');
            $table->foreignId('satellite_image_id')->nullable()->constrained()->onDelete('set null');
            
            $table->string('alert_type'); // 'change_detected', 'object_detected', 'threshold_exceeded'
            $table->string('severity')->default('info'); // 'info', 'warning', 'critical'
            $table->text('message');
            $table->json('details')->nullable();
            
            $table->boolean('is_read')->default(false);
            $table->boolean('is_acknowledged')->default(false);
            $table->timestamp('acknowledged_at')->nullable();
            
            $table->timestamps();
            
            // Índices
            $table->index(['satellite_zone_id', 'is_read']);
            $table->index('created_at');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('satellite_alerts');
        Schema::dropIfExists('satellite_images');
        Schema::dropIfExists('satellite_zones');
    }
};
