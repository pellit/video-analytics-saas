<template>
  <div class="pricing-container">
    <div class="pricing-header">
      <h2>Elige tu Plan</h2>
      <p>Escala tu vigilancia inteligente según tus necesidades</p>
      
      <!-- Billing Toggle -->
      <div class="billing-toggle">
        <span :class="{ active: !isAnnual }">Mensual</span>
        <button class="toggle-btn" @click="isAnnual = !isAnnual">
          <span class="toggle-slider" :class="{ annual: isAnnual }"></span>
        </button>
        <span :class="{ active: isAnnual }">
          Anual
          <span class="save-badge">-20%</span>
        </span>
      </div>
    </div>

    <div class="pricing-grid">
      <!-- Free Plan -->
      <div 
        class="plan-card" 
        :class="{ current: currentPlan === 'free' }"
      >
        <div class="plan-icon">🆓</div>
        <h3 class="plan-name">Free</h3>
        <div class="plan-price">
          <span class="price-amount">$0</span>
          <span class="price-period">/mes</span>
        </div>
        <p class="plan-description">Perfecto para empezar a explorar</p>
        
        <ul class="plan-features">
          <li><span class="check">✓</span> 1 cámara</li>
          <li><span class="check">✓</span> 10 llamadas API/día</li>
          <li><span class="check">✓</span> Detección básica</li>
          <li><span class="check">✓</span> Dashboard estándar</li>
          <li class="disabled"><span class="x">✕</span> IA avanzada</li>
          <li class="disabled"><span class="x">✕</span> Reconocimiento facial</li>
          <li class="disabled"><span class="x">✕</span> Soporte prioritario</li>
        </ul>

        <button 
          class="plan-btn" 
          :class="{ current: currentPlan === 'free' }"
          :disabled="currentPlan === 'free'"
          @click="selectPlan('free')"
        >
          {{ currentPlan === 'free' ? 'Plan actual' : 'Seleccionar' }}
        </button>
      </div>

      <!-- Pro Plan -->
      <div 
        class="plan-card featured" 
        :class="{ current: currentPlan === 'pro' }"
      >
        <div class="popular-badge">Más popular</div>
        <div class="plan-icon">⭐</div>
        <h3 class="plan-name">Pro</h3>
        <div class="plan-price">
          <span class="price-amount">${{ isAnnual ? '23' : '29' }}</span>
          <span class="price-period">/mes</span>
        </div>
        <p class="plan-description">Para negocios en crecimiento</p>
        
        <ul class="plan-features">
          <li><span class="check">✓</span> 5 cámaras</li>
          <li><span class="check">✓</span> 1,000 llamadas API/día</li>
          <li><span class="check">✓</span> Detección avanzada</li>
          <li><span class="check">✓</span> Dashboard Octopus</li>
          <li><span class="check">✓</span> IA avanzada</li>
          <li><span class="check">✓</span> Reconocimiento facial</li>
          <li class="disabled"><span class="x">✕</span> Soporte prioritario</li>
        </ul>

        <button 
          class="plan-btn featured" 
          :class="{ current: currentPlan === 'pro' }"
          :disabled="currentPlan === 'pro'"
          @click="selectPlan('pro')"
        >
          {{ currentPlan === 'pro' ? 'Plan actual' : 'Comenzar prueba' }}
        </button>
      </div>

      <!-- Enterprise Plan -->
      <div 
        class="plan-card" 
        :class="{ current: currentPlan === 'enterprise' }"
      >
        <div class="plan-icon">💎</div>
        <h3 class="plan-name">Enterprise</h3>
        <div class="plan-price">
          <span class="price-amount">${{ isAnnual ? '79' : '99' }}</span>
          <span class="price-period">/mes</span>
        </div>
        <p class="plan-description">Control total sin límites</p>
        
        <ul class="plan-features">
          <li><span class="check">✓</span> Cámaras ilimitadas</li>
          <li><span class="check">✓</span> API ilimitada</li>
          <li><span class="check">✓</span> Todas las funciones</li>
          <li><span class="check">✓</span> Dashboard Octopus</li>
          <li><span class="check">✓</span> IA avanzada</li>
          <li><span class="check">✓</span> Reconocimiento facial</li>
          <li><span class="check">✓</span> Soporte prioritario 24/7</li>
        </ul>

        <button 
          class="plan-btn" 
          :class="{ current: currentPlan === 'enterprise' }"
          :disabled="currentPlan === 'enterprise'"
          @click="selectPlan('enterprise')"
        >
          {{ currentPlan === 'enterprise' ? 'Plan actual' : 'Contactar ventas' }}
        </button>
      </div>
    </div>

    <!-- Features Comparison -->
    <div class="features-comparison" v-if="showComparison">
      <h3>Comparación de características</h3>
      <table class="comparison-table">
        <thead>
          <tr>
            <th>Característica</th>
            <th>Free</th>
            <th>Pro</th>
            <th>Enterprise</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Cámaras</td>
            <td>1</td>
            <td>5</td>
            <td>∞</td>
          </tr>
          <tr>
            <td>API calls/día</td>
            <td>10</td>
            <td>1,000</td>
            <td>∞</td>
          </tr>
          <tr>
            <td>Detección de objetos</td>
            <td><span class="check-cell">✓</span></td>
            <td><span class="check-cell">✓</span></td>
            <td><span class="check-cell">✓</span></td>
          </tr>
          <tr>
            <td>Reconocimiento facial</td>
            <td><span class="x-cell">✕</span></td>
            <td><span class="check-cell">✓</span></td>
            <td><span class="check-cell">✓</span></td>
          </tr>
          <tr>
            <td>Análisis de profundidad</td>
            <td><span class="x-cell">✕</span></td>
            <td><span class="check-cell">✓</span></td>
            <td><span class="check-cell">✓</span></td>
          </tr>
          <tr>
            <td>Vista Bird's Eye</td>
            <td><span class="x-cell">✕</span></td>
            <td><span class="check-cell">✓</span></td>
            <td><span class="check-cell">✓</span></td>
          </tr>
          <tr>
            <td>Alertas personalizadas</td>
            <td>Básicas</td>
            <td>Avanzadas</td>
            <td>Ilimitadas</td>
          </tr>
          <tr>
            <td>Retención de datos</td>
            <td>7 días</td>
            <td>30 días</td>
            <td>90 días</td>
          </tr>
          <tr>
            <td>Soporte</td>
            <td>Email</td>
            <td>Email + Chat</td>
            <td>24/7 Prioritario</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- FAQ Section -->
    <div class="faq-section">
      <h3>Preguntas frecuentes</h3>
      <div class="faq-grid">
        <div class="faq-item">
          <h4>¿Puedo cambiar de plan en cualquier momento?</h4>
          <p>Sí, puedes actualizar o degradar tu plan cuando quieras. Los cambios se aplican de inmediato.</p>
        </div>
        <div class="faq-item">
          <h4>¿Qué pasa si supero mis límites?</h4>
          <p>Te notificaremos cuando te acerques al límite. Las funciones se pausan hasta que actualices o inicie el nuevo ciclo.</p>
        </div>
        <div class="faq-item">
          <h4>¿Hay periodo de prueba?</h4>
          <p>Sí, Pro incluye 14 días de prueba gratis. No necesitas tarjeta para empezar.</p>
        </div>
        <div class="faq-item">
          <h4>¿Cómo funciona la facturación?</h4>
          <p>Facturamos mensual o anualmente según tu preferencia. Aceptamos todas las tarjetas principales.</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  currentPlan: { type: String, default: 'free' },
  showComparison: { type: Boolean, default: true }
})

const emit = defineEmits(['select', 'contact'])

const isAnnual = ref(false)

const selectPlan = (planSlug) => {
  if (planSlug === 'enterprise') {
    emit('contact', { plan: planSlug, billing: isAnnual.value ? 'annual' : 'monthly' })
  } else {
    emit('select', { plan: planSlug, billing: isAnnual.value ? 'annual' : 'monthly' })
  }
}
</script>

<style scoped>
.pricing-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 40px 20px;
}

/* Header */
.pricing-header {
  text-align: center;
  margin-bottom: 48px;
}

.pricing-header h2 {
  font-size: 2.5rem;
  font-weight: 700;
  color: #e2e8f0;
  margin-bottom: 12px;
}

.pricing-header p {
  font-size: 1.1rem;
  color: #94a3b8;
  margin-bottom: 32px;
}

/* Billing Toggle */
.billing-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  font-size: 0.95rem;
  color: #64748b;
}

.billing-toggle span.active {
  color: #e2e8f0;
  font-weight: 600;
}

.toggle-btn {
  position: relative;
  width: 56px;
  height: 28px;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 14px;
  cursor: pointer;
  padding: 0;
}

.toggle-slider {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 20px;
  height: 20px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  border-radius: 50%;
  transition: transform 0.3s ease;
}

.toggle-slider.annual {
  transform: translateX(28px);
}

.save-badge {
  background: linear-gradient(135deg, #10b981, #059669);
  color: white;
  font-size: 0.7rem;
  padding: 2px 8px;
  border-radius: 10px;
  margin-left: 8px;
  font-weight: 600;
}

/* Pricing Grid */
.pricing-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 24px;
  margin-bottom: 64px;
}

@media (max-width: 900px) {
  .pricing-grid {
    grid-template-columns: 1fr;
    max-width: 400px;
    margin: 0 auto 64px;
  }
}

/* Plan Card */
.plan-card {
  background: rgba(15, 23, 42, 0.8);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 20px;
  padding: 32px 24px;
  text-align: center;
  position: relative;
  transition: all 0.3s ease;
}

.plan-card:hover {
  transform: translateY(-8px);
  border-color: rgba(99, 102, 241, 0.3);
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
}

.plan-card.featured {
  border-color: rgba(99, 102, 241, 0.5);
  background: linear-gradient(180deg, rgba(99, 102, 241, 0.1), rgba(15, 23, 42, 0.9));
  transform: scale(1.05);
}

.plan-card.featured:hover {
  transform: scale(1.08) translateY(-8px);
}

.plan-card.current {
  border-color: rgba(34, 197, 94, 0.5);
}

.popular-badge {
  position: absolute;
  top: -12px;
  left: 50%;
  transform: translateX(-50%);
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: white;
  font-size: 0.75rem;
  font-weight: 600;
  padding: 4px 16px;
  border-radius: 12px;
}

.plan-icon {
  font-size: 3rem;
  margin-bottom: 16px;
}

.plan-name {
  font-size: 1.5rem;
  font-weight: 700;
  color: #e2e8f0;
  margin-bottom: 8px;
}

.plan-price {
  margin-bottom: 8px;
}

.price-amount {
  font-size: 3rem;
  font-weight: 700;
  color: #e2e8f0;
}

.price-period {
  font-size: 1rem;
  color: #64748b;
}

.plan-description {
  font-size: 0.9rem;
  color: #94a3b8;
  margin-bottom: 24px;
}

/* Features List */
.plan-features {
  list-style: none;
  padding: 0;
  margin: 0 0 32px;
  text-align: left;
}

.plan-features li {
  padding: 10px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  font-size: 0.9rem;
  color: #e2e8f0;
  display: flex;
  align-items: center;
  gap: 12px;
}

.plan-features li:last-child {
  border-bottom: none;
}

.plan-features li.disabled {
  color: #475569;
}

.check {
  color: #10b981;
  font-weight: bold;
}

.x {
  color: #475569;
}

/* Plan Button */
.plan-btn {
  width: 100%;
  padding: 14px 24px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  color: #e2e8f0;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
}

.plan-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1);
  transform: translateY(-2px);
}

.plan-btn.featured {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  border: none;
}

.plan-btn.featured:hover:not(:disabled) {
  box-shadow: 0 8px 24px rgba(99, 102, 241, 0.4);
}

.plan-btn.current,
.plan-btn:disabled {
  background: rgba(34, 197, 94, 0.2);
  border-color: rgba(34, 197, 94, 0.3);
  color: #86efac;
  cursor: default;
}

/* Features Comparison */
.features-comparison {
  margin-bottom: 64px;
}

.features-comparison h3 {
  text-align: center;
  font-size: 1.5rem;
  color: #e2e8f0;
  margin-bottom: 32px;
}

.comparison-table {
  width: 100%;
  border-collapse: collapse;
  background: rgba(15, 23, 42, 0.6);
  border-radius: 16px;
  overflow: hidden;
}

.comparison-table th,
.comparison-table td {
  padding: 16px;
  text-align: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.comparison-table th {
  background: rgba(0, 0, 0, 0.3);
  color: #e2e8f0;
  font-weight: 600;
}

.comparison-table th:first-child,
.comparison-table td:first-child {
  text-align: left;
  padding-left: 24px;
}

.comparison-table td {
  color: #94a3b8;
}

.check-cell {
  color: #10b981;
  font-weight: bold;
}

.x-cell {
  color: #475569;
}

/* FAQ Section */
.faq-section h3 {
  text-align: center;
  font-size: 1.5rem;
  color: #e2e8f0;
  margin-bottom: 32px;
}

.faq-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 24px;
}

@media (max-width: 768px) {
  .faq-grid {
    grid-template-columns: 1fr;
  }
}

.faq-item {
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  padding: 24px;
}

.faq-item h4 {
  color: #e2e8f0;
  font-size: 1rem;
  margin-bottom: 12px;
}

.faq-item p {
  color: #94a3b8;
  font-size: 0.9rem;
  line-height: 1.6;
  margin: 0;
}
</style>
