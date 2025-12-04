<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('satellite_images', function (Blueprint $table) {
            // SQLite no soporta ALTER COLUMN directamente
            // Hacerlo nullable creando una columna temporal
        });
        
        // Para SQLite, necesitamos recrear la tabla
        if (config('database.default') === 'sqlite') {
            // Crear tabla temporal
            Schema::create('satellite_images_temp', function (Blueprint $table) {
                $table->id();
                $table->foreignId('satellite_zone_id')->constrained()->onDelete('cascade');
                $table->string('image_path')->nullable(); // Ahora nullable
                $table->string('thumbnail_path')->nullable();
                $table->timestamp('captured_at')->nullable();
                $table->integer('cloud_cover')->nullable();
                $table->string('satellite_source')->default('sentinel-2');
                $table->json('detections')->nullable();
                $table->text('ai_description')->nullable();
                $table->json('changes_detected')->nullable();
                $table->enum('status', ['pending', 'processing', 'completed', 'failed'])->default('pending');
                $table->text('error_message')->nullable();
                $table->timestamps();
            });
            
            // Copiar datos
            \DB::statement('INSERT INTO satellite_images_temp SELECT * FROM satellite_images');
            
            // Eliminar tabla original
            Schema::dropIfExists('satellite_images');
            
            // Renombrar tabla temporal
            Schema::rename('satellite_images_temp', 'satellite_images');
        }
    }

    public function down(): void
    {
        // No hacer nada en el rollback
    }
};
