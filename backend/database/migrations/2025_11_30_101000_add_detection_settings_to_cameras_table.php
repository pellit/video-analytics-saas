<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('cameras', function (Blueprint $table) {
            $table->boolean('detection_enabled')->default(false)->after('status');
            $table->string('detection_model')->nullable()->after('detection_enabled');
            $table->boolean('tracking')->default(true)->after('detection_model');
        });
    }

    public function down(): void
    {
        Schema::table('cameras', function (Blueprint $table) {
            $table->dropColumn(['detection_enabled','detection_model','tracking']);
        });
    }
};
