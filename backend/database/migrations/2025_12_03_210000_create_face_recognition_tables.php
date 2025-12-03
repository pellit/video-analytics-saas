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
        // Known faces - faces that have been labeled/named by users
        Schema::create('known_faces', function (Blueprint $table) {
            $table->id();
            $table->foreignId('user_id')->constrained()->onDelete('cascade');
            $table->string('name'); // Name/label for this face
            $table->string('label')->nullable(); // Optional additional label/tag
            $table->json('embedding')->nullable(); // Face embedding vector (128-512 dims)
            $table->string('face_image_path')->nullable(); // Path to stored face image
            $table->json('metadata')->nullable(); // Additional metadata
            $table->unsignedInteger('detection_count')->default(0); // Times this face was detected
            $table->timestamp('last_seen_at')->nullable();
            $table->timestamps();

            $table->index(['user_id', 'name']);
        });

        // Face detections - individual face detection events from cameras
        Schema::create('face_detections', function (Blueprint $table) {
            $table->id();
            $table->foreignId('camera_id')->constrained()->onDelete('cascade');
            $table->foreignId('known_face_id')->nullable()->constrained('known_faces')->onDelete('set null');
            $table->json('embedding')->nullable(); // Face embedding for this detection
            $table->string('face_image_path')->nullable(); // Cropped face image
            $table->float('confidence')->default(0); // Detection confidence
            $table->float('similarity_score')->nullable(); // Similarity to matched known face
            $table->json('bbox')->nullable(); // Bounding box coordinates
            $table->boolean('identified')->default(false); // Whether this face was matched
            $table->json('metadata')->nullable();
            $table->timestamps();

            $table->index(['camera_id', 'created_at']);
            $table->index(['identified', 'created_at']);
            $table->index('known_face_id');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('face_detections');
        Schema::dropIfExists('known_faces');
    }
};
