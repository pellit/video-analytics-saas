<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     * 
     * Tables for subscription system (compatible with Laravel Cashier when installed)
     */
    public function up(): void
    {
        // Tabla de planes
        Schema::create('plans', function (Blueprint $table) {
            $table->id();
            $table->string('name');              // free, pro, enterprise
            $table->string('display_name');      // Plan Free, Plan Pro, Enterprise
            $table->string('stripe_price_id')->nullable(); // price_xxx de Stripe
            $table->decimal('price', 10, 2)->default(0);   // Precio mensual
            $table->string('currency', 3)->default('USD');
            $table->integer('camera_limit')->default(1);    // Límite de cámaras
            $table->integer('analysis_hours_per_day')->default(1); // Horas de análisis/día
            $table->boolean('ai_advanced')->default(false); // IA avanzada (armas, EPP)
            $table->boolean('vlm_access')->default(false);  // Acceso a VLM (Moondream)
            $table->boolean('satellite_access')->default(false); // Acceso satelital
            $table->boolean('cad_access')->default(false);  // Acceso CAD
            $table->boolean('api_access')->default(false);  // Acceso API externa
            $table->integer('api_calls_per_day')->default(0); // Llamadas API/día
            $table->boolean('email_alerts')->default(false);
            $table->boolean('telegram_alerts')->default(false);
            $table->boolean('recording')->default(false);    // Grabación de video
            $table->integer('retention_days')->default(0);   // Días de retención
            $table->json('features')->nullable();            // Features extra en JSON
            $table->boolean('is_active')->default(true);
            $table->integer('sort_order')->default(0);
            $table->timestamps();
        });

        // Tabla de suscripciones (simplificada, compatible con Cashier)
        Schema::create('subscriptions', function (Blueprint $table) {
            $table->id();
            $table->foreignId('user_id')->constrained()->onDelete('cascade');
            $table->foreignId('plan_id')->constrained()->onDelete('restrict');
            $table->string('stripe_id')->nullable()->unique(); // sub_xxx de Stripe
            $table->string('stripe_status')->nullable();       // active, canceled, past_due
            $table->string('type')->default('default');        // Para Cashier
            $table->timestamp('trial_ends_at')->nullable();
            $table->timestamp('ends_at')->nullable();          // Fecha de cancelación
            $table->timestamp('current_period_start')->nullable();
            $table->timestamp('current_period_end')->nullable();
            $table->boolean('cancel_at_period_end')->default(false);
            $table->timestamps();

            $table->index(['user_id', 'stripe_status']);
        });

        // Tabla de items de suscripción (para planes con múltiples items)
        Schema::create('subscription_items', function (Blueprint $table) {
            $table->id();
            $table->foreignId('subscription_id')->constrained()->onDelete('cascade');
            $table->string('stripe_id')->nullable()->unique(); // si_xxx de Stripe
            $table->string('stripe_product')->nullable();
            $table->string('stripe_price')->nullable();
            $table->integer('quantity')->default(1);
            $table->timestamps();
        });

        // Historial de uso (para facturación por uso)
        Schema::create('usage_records', function (Blueprint $table) {
            $table->id();
            $table->foreignId('user_id')->constrained()->onDelete('cascade');
            $table->foreignId('camera_id')->nullable()->constrained()->onDelete('set null');
            $table->string('metric');          // 'analysis_minutes', 'api_calls', 'storage_mb'
            $table->integer('quantity');
            $table->date('recorded_date');
            $table->timestamps();

            $table->index(['user_id', 'metric', 'recorded_date']);
        });

        // Agregar campos al usuario para billing
        Schema::table('users', function (Blueprint $table) {
            $table->string('stripe_id')->nullable()->unique()->after('role');
            $table->string('pm_type')->nullable()->after('stripe_id');      // visa, mastercard
            $table->string('pm_last_four', 4)->nullable()->after('pm_type');
            $table->timestamp('trial_ends_at')->nullable()->after('pm_last_four');
            $table->foreignId('plan_id')->nullable()->after('trial_ends_at');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::table('users', function (Blueprint $table) {
            $table->dropColumn(['stripe_id', 'pm_type', 'pm_last_four', 'trial_ends_at', 'plan_id']);
        });
        
        Schema::dropIfExists('usage_records');
        Schema::dropIfExists('subscription_items');
        Schema::dropIfExists('subscriptions');
        Schema::dropIfExists('plans');
    }
};
