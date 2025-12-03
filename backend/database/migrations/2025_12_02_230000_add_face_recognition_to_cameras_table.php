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
        Schema::table('cameras', function (Blueprint $table) {
            // Añadir columna face_recognition_enabled si no existe
            if (!Schema::hasColumn('cameras', 'face_recognition_enabled')) {
                $table->boolean('face_recognition_enabled')->default(false)->after('detection_classes');
            }
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::table('cameras', function (Blueprint $table) {
            $table->dropColumn('face_recognition_enabled');
        });
    }
};
