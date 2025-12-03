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
        // API Keys for third-party applications
        Schema::create('api_keys', function (Blueprint $table) {
            $table->id();
            $table->foreignId('user_id')->constrained()->onDelete('cascade');
            $table->string('name'); // Descriptive name for the API key
            $table->string('key', 64)->unique(); // The actual API key (hashed)
            $table->string('key_prefix', 8); // First 8 chars for identification (unhashed)
            $table->text('description')->nullable();
            $table->json('permissions')->nullable(); // What this key can do: ['analyze', 'stream', 'detect']
            $table->integer('rate_limit')->default(100); // Requests per minute
            $table->integer('daily_limit')->default(10000); // Requests per day
            $table->boolean('is_active')->default(true);
            $table->timestamp('last_used_at')->nullable();
            $table->timestamp('expires_at')->nullable();
            $table->timestamps();
            
            $table->index(['key_prefix', 'is_active']);
        });

        // API Usage logs for tracking and analytics
        Schema::create('api_usage_logs', function (Blueprint $table) {
            $table->id();
            $table->foreignId('api_key_id')->constrained()->onDelete('cascade');
            $table->string('endpoint'); // Which endpoint was called
            $table->string('method', 10); // GET, POST, etc
            $table->string('ip_address', 45)->nullable();
            $table->string('user_agent')->nullable();
            $table->integer('response_code')->nullable();
            $table->integer('response_time_ms')->nullable(); // Response time in milliseconds
            $table->integer('payload_size')->nullable(); // Size of request payload in bytes
            $table->json('metadata')->nullable(); // Additional info like camera_id, frame_count, etc
            $table->timestamp('created_at')->useCurrent();
            
            $table->index(['api_key_id', 'created_at']);
            $table->index('created_at');
        });

        // Daily aggregated stats for quick dashboard queries
        Schema::create('api_usage_daily', function (Blueprint $table) {
            $table->id();
            $table->foreignId('api_key_id')->constrained()->onDelete('cascade');
            $table->date('date');
            $table->integer('request_count')->default(0);
            $table->integer('frames_processed')->default(0);
            $table->integer('detections_count')->default(0);
            $table->bigInteger('bytes_received')->default(0);
            $table->integer('errors_count')->default(0);
            $table->integer('avg_response_time_ms')->default(0);
            $table->timestamps();
            
            $table->unique(['api_key_id', 'date']);
            $table->index('date');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('api_usage_daily');
        Schema::dropIfExists('api_usage_logs');
        Schema::dropIfExists('api_keys');
    }
};
