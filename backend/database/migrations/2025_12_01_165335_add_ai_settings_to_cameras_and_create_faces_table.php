<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        // 1. Agregar configuración de clases a la tabla cameras
        Schema::table('cameras', function (Blueprint $table) {
            // JSON para guardar las clases seleccionadas (ej: ['person', 'car'])
            $table->json('detection_classes')->nullable()->after('detection_model');
            // JSON para guardar configuración de zonas o líneas (futuro)
            $table->json('roi_settings')->nullable()->after('detection_classes');
        });

        // 2. Crear tabla de rostros (Faces)
        Schema::create('faces', function (Blueprint $table) {
            $table->id();
            $table->string('name')->nullable()->default('Unknown');
            // Guardamos el embedding como binario (BLOB) o JSON. 
            // Para SQLite/MySQL simple usaremos TEXT/JSON por ahora.
            // En producción con pgvector sería 'vector'.
            $table->text('embedding')->nullable(); 
            $table->string('preview_url')->nullable(); // URL de la imagen del rostro recortado
            $table->timestamp('first_seen_at')->useCurrent();
            $table->timestamp('last_seen_at')->useCurrent();
            $table->timestamps();
        });

        // 3. Relacionar detecciones con rostros
        Schema::table('detections', function (Blueprint $table) {
            $table->foreignId('face_id')->nullable()->constrained('faces')->nullOnDelete();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::table('detections', function (Blueprint $table) {
            $table->dropForeign(['face_id']);
            $table->dropColumn('face_id');
        });

        Schema::dropIfExists('faces');

        Schema::table('cameras', function (Blueprint $table) {
            $table->dropColumn(['detection_classes', 'roi_settings']);
        });
    }
};
