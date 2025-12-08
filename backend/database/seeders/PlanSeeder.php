<?php

namespace Database\Seeders;

use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\DB;

class PlanSeeder extends Seeder
{
    /**
     * Seed the plans table with default subscription plans.
     */
    public function run(): void
    {
        $plans = [
            [
                'name' => 'free',
                'display_name' => 'Plan Free',
                'stripe_price_id' => null,
                'price' => 0,
                'currency' => 'USD',
                'camera_limit' => 1,
                'analysis_hours_per_day' => 1,
                'ai_advanced' => false,
                'vlm_access' => false,
                'satellite_access' => false,
                'cad_access' => false,
                'api_access' => false,
                'api_calls_per_day' => 0,
                'email_alerts' => false,
                'telegram_alerts' => false,
                'recording' => false,
                'retention_days' => 0,
                'features' => json_encode([
                    'yolo_basic' => true,
                    'live_view' => true,
                    'basic_detections' => ['person', 'car', 'dog', 'cat'],
                ]),
                'is_active' => true,
                'sort_order' => 1,
            ],
            [
                'name' => 'pro',
                'display_name' => 'Plan Pro',
                'stripe_price_id' => env('STRIPE_PRICE_PRO', 'price_pro_placeholder'),
                'price' => 29.00,
                'currency' => 'USD',
                'camera_limit' => 5,
                'analysis_hours_per_day' => 24,
                'ai_advanced' => true,
                'vlm_access' => false,
                'satellite_access' => false,
                'cad_access' => false,
                'api_access' => true,
                'api_calls_per_day' => 1000,
                'email_alerts' => true,
                'telegram_alerts' => true,
                'recording' => true,
                'retention_days' => 7,
                'features' => json_encode([
                    'yolo_basic' => true,
                    'yolo_advanced' => true,
                    'live_view' => true,
                    'basic_detections' => ['person', 'car', 'dog', 'cat'],
                    'advanced_detections' => ['weapon', 'fire', 'ppe', 'face'],
                    'face_recognition' => true,
                    'zones' => true,
                    'schedules' => true,
                ]),
                'is_active' => true,
                'sort_order' => 2,
            ],
            [
                'name' => 'business',
                'display_name' => 'Plan Business',
                'stripe_price_id' => env('STRIPE_PRICE_BUSINESS', 'price_business_placeholder'),
                'price' => 99.00,
                'currency' => 'USD',
                'camera_limit' => 20,
                'analysis_hours_per_day' => 24,
                'ai_advanced' => true,
                'vlm_access' => true,
                'satellite_access' => true,
                'cad_access' => true,
                'api_access' => true,
                'api_calls_per_day' => 10000,
                'email_alerts' => true,
                'telegram_alerts' => true,
                'recording' => true,
                'retention_days' => 30,
                'features' => json_encode([
                    'yolo_basic' => true,
                    'yolo_advanced' => true,
                    'vlm_analysis' => true,
                    'satellite_analysis' => true,
                    'cad_overlay' => true,
                    'live_view' => true,
                    'all_detections' => true,
                    'face_recognition' => true,
                    'zones' => true,
                    'schedules' => true,
                    'multi_user' => true,
                    'priority_support' => true,
                ]),
                'is_active' => true,
                'sort_order' => 3,
            ],
            [
                'name' => 'enterprise',
                'display_name' => 'Enterprise',
                'stripe_price_id' => env('STRIPE_PRICE_ENTERPRISE', 'price_enterprise_placeholder'),
                'price' => 299.00,
                'currency' => 'USD',
                'camera_limit' => 999, // Prácticamente ilimitado
                'analysis_hours_per_day' => 24,
                'ai_advanced' => true,
                'vlm_access' => true,
                'satellite_access' => true,
                'cad_access' => true,
                'api_access' => true,
                'api_calls_per_day' => 999999, // Ilimitado
                'email_alerts' => true,
                'telegram_alerts' => true,
                'recording' => true,
                'retention_days' => 90,
                'features' => json_encode([
                    'all_features' => true,
                    'custom_models' => true,
                    'dedicated_support' => true,
                    'sla' => true,
                    'on_premise' => true,
                    'white_label' => true,
                ]),
                'is_active' => true,
                'sort_order' => 4,
            ],
        ];

        foreach ($plans as $plan) {
            DB::table('plans')->updateOrInsert(
                ['name' => $plan['name']],
                array_merge($plan, [
                    'created_at' => now(),
                    'updated_at' => now(),
                ])
            );
        }
    }
}
