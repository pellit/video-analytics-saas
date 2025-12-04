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
        Schema::create('satellite_analyses', function (Blueprint $table) {
            $table->id();
            $table->foreignId('user_id')->constrained()->onDelete('cascade');
            $table->foreignId('satellite_zone_id')->nullable()->constrained()->onDelete('set null');
            
            // Zone reference (in case zone is deleted)
            $table->string('zone_name')->nullable();
            $table->decimal('latitude', 10, 7)->nullable();
            $table->decimal('longitude', 10, 7)->nullable();
            
            // Comparison metrics
            $table->decimal('change_percent', 5, 2);
            $table->decimal('ssim_score', 5, 4)->nullable();
            $table->decimal('histogram_correlation', 5, 4)->nullable();
            $table->decimal('pixel_diff_percent', 5, 2)->nullable();
            
            // Classification
            $table->enum('severity', ['minimal', 'low', 'moderate', 'significant', 'critical'])->default('minimal');
            $table->enum('change_type', [
                'construction', 'vegetation', 'water', 'deforestation', 
                'urban_expansion', 'agricultural', 'unknown'
            ])->default('unknown');
            
            // AI Analysis
            $table->text('vlm_analysis')->nullable();
            $table->string('vlm_model')->nullable();
            $table->text('vlm_prompt')->nullable();
            
            // Recommendations (JSON array)
            $table->json('recommendations')->nullable();
            
            // Change regions (JSON array of detected regions)
            $table->json('change_regions')->nullable();
            
            // Images (stored as paths to avoid bloating DB)
            $table->string('previous_image_path')->nullable();
            $table->string('current_image_path')->nullable();
            $table->string('heatmap_path')->nullable();
            $table->string('overlay_path')->nullable();
            
            // Notification status
            $table->boolean('notification_sent')->default(false);
            $table->timestamp('notified_at')->nullable();
            $table->enum('notification_priority', ['low', 'medium', 'high'])->nullable();
            
            // Metadata
            $table->json('metadata')->nullable();
            
            $table->timestamps();
            
            // Indexes
            $table->index(['user_id', 'created_at']);
            $table->index(['satellite_zone_id', 'created_at']);
            $table->index('severity');
            $table->index('change_type');
        });
        
        // Create notifications table for push notifications
        Schema::create('user_notifications', function (Blueprint $table) {
            $table->id();
            $table->foreignId('user_id')->constrained()->onDelete('cascade');
            
            // Notification content
            $table->string('title');
            $table->text('message');
            $table->enum('type', ['info', 'success', 'warning', 'error', 'alert'])->default('info');
            $table->enum('priority', ['low', 'medium', 'high', 'critical'])->default('medium');
            
            // Source reference (polymorphic)
            $table->string('source_type')->nullable(); // 'satellite_analysis', 'alert', etc.
            $table->unsignedBigInteger('source_id')->nullable();
            
            // Delivery status
            $table->boolean('read')->default(false);
            $table->timestamp('read_at')->nullable();
            $table->boolean('push_sent')->default(false);
            $table->timestamp('push_sent_at')->nullable();
            $table->boolean('email_sent')->default(false);
            $table->timestamp('email_sent_at')->nullable();
            
            // Action URL
            $table->string('action_url')->nullable();
            $table->string('action_text')->nullable();
            
            // Metadata
            $table->json('data')->nullable();
            
            $table->timestamps();
            
            // Indexes
            $table->index(['user_id', 'read', 'created_at']);
            $table->index(['user_id', 'type']);
            $table->index(['source_type', 'source_id']);
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('user_notifications');
        Schema::dropIfExists('satellite_analyses');
    }
};
