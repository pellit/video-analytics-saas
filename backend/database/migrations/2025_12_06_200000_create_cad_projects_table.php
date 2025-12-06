<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     * 
     * CAD Projects - "Architect's Eye" Feature
     * Almacena proyectos de planos arquitectónicos/ingeniería para análisis con IA
     */
    public function up(): void
    {
        Schema::create('cad_projects', function (Blueprint $table) {
            $table->id();
            $table->foreignId('user_id')->constrained()->onDelete('cascade');
            
            // Project Info
            $table->string('name');
            $table->text('description')->nullable();
            $table->string('project_type')->default('architecture'); // architecture, engineering, electrical, plumbing, structural
            
            // File Info
            $table->string('original_filename');
            $table->string('file_path'); // Ruta del archivo subido
            $table->string('file_type'); // dxf, dwg, pdf
            $table->bigInteger('file_size')->default(0); // bytes
            
            // Processing Status
            $table->enum('status', [
                'pending',      // Esperando procesamiento
                'rendering',    // Convirtiendo CAD a imagen
                'analyzing',    // Moondream analizando
                'completed',    // Análisis completo
                'error'         // Error en procesamiento
            ])->default('pending');
            $table->unsignedTinyInteger('progress')->default(0); // 0-100
            $table->string('current_step')->nullable(); // "Renderizando plano...", "Analizando habitaciones..."
            $table->text('error_message')->nullable();
            
            // Rendered Output
            $table->string('render_image_path')->nullable(); // PNG renderizado
            $table->string('render_thumbnail_path')->nullable(); // Thumbnail para lista
            
            // AI Analysis Results (JSON)
            $table->json('analysis_general')->nullable();     // Descripción general del plano
            $table->json('analysis_rooms')->nullable();       // Habitaciones detectadas
            $table->json('analysis_safety')->nullable();      // Elementos de seguridad
            $table->json('analysis_structural')->nullable();  // Elementos estructurales
            $table->json('analysis_dimensions')->nullable();  // Dimensiones estimadas
            $table->json('analysis_materials')->nullable();   // Materiales sugeridos
            $table->json('analysis_compliance')->nullable();  // Cumplimiento normativo (futuro)
            
            // Metadata
            $table->json('metadata')->nullable(); // Info extraída del CAD (layers, blocks, etc)
            $table->json('tags')->nullable(); // Tags para búsqueda
            
            // Processing Times
            $table->timestamp('processing_started_at')->nullable();
            $table->timestamp('processing_completed_at')->nullable();
            $table->unsignedInteger('processing_duration_seconds')->nullable();
            
            $table->timestamps();
            
            // Indexes
            $table->index(['user_id', 'status']);
            $table->index(['user_id', 'project_type']);
            $table->index('created_at');
        });

        // Tabla para análisis por lotes (futuro)
        Schema::create('cad_batch_jobs', function (Blueprint $table) {
            $table->id();
            $table->foreignId('user_id')->constrained()->onDelete('cascade');
            $table->string('name');
            $table->enum('status', ['pending', 'processing', 'completed', 'error'])->default('pending');
            $table->unsignedInteger('total_files')->default(0);
            $table->unsignedInteger('processed_files')->default(0);
            $table->unsignedInteger('failed_files')->default(0);
            $table->json('summary')->nullable(); // Resumen del análisis por lotes
            $table->timestamps();
        });

        // Tabla pivote para lotes
        Schema::create('cad_batch_project', function (Blueprint $table) {
            $table->id();
            $table->foreignId('batch_id')->constrained('cad_batch_jobs')->onDelete('cascade');
            $table->foreignId('project_id')->constrained('cad_projects')->onDelete('cascade');
            $table->unsignedSmallInteger('order')->default(0);
            $table->timestamps();
        });

        // Tabla para análisis comparativos (futuro - tracking de cambios entre versiones)
        Schema::create('cad_comparisons', function (Blueprint $table) {
            $table->id();
            $table->foreignId('user_id')->constrained()->onDelete('cascade');
            $table->foreignId('project_a_id')->constrained('cad_projects')->onDelete('cascade');
            $table->foreignId('project_b_id')->constrained('cad_projects')->onDelete('cascade');
            $table->string('comparison_type')->default('diff'); // diff, overlay, timeline
            $table->json('changes_detected')->nullable();
            $table->string('diff_image_path')->nullable();
            $table->timestamps();
        });

        // Tabla para analytics agregadas (futuro)
        Schema::create('cad_analytics', function (Blueprint $table) {
            $table->id();
            $table->foreignId('user_id')->constrained()->onDelete('cascade');
            $table->string('metric_type'); // total_sqm, avg_rooms, common_issues, etc
            $table->string('project_type')->nullable();
            $table->json('data');
            $table->date('period_start');
            $table->date('period_end');
            $table->timestamps();
            
            $table->index(['user_id', 'metric_type', 'period_start']);
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('cad_analytics');
        Schema::dropIfExists('cad_comparisons');
        Schema::dropIfExists('cad_batch_project');
        Schema::dropIfExists('cad_batch_jobs');
        Schema::dropIfExists('cad_projects');
    }
};
