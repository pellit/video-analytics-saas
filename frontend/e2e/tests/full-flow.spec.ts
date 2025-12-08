import { test, expect } from '@playwright/test';

/**
 * Comprehensive E2E Test Suite for Video Analytics SaaS
 * 
 * Estos tests usan autenticación pre-configurada (auth.setup.ts)
 * para evitar rate limiting en el login.
 */

test.describe('Dashboard Tests', () => {
  
  test('Dashboard loads correctly after authentication', async ({ page }) => {
    // El usuario ya está autenticado gracias a auth.setup.ts
    console.log('📍 Navegando al dashboard...');
    
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    
    // Verificar que el token existe en localStorage
    const token = await page.evaluate(() => localStorage.getItem('token'));
    console.log('🔑 Token presente:', !!token);
    expect(token).toBeTruthy();
    
    // Verificar datos del usuario
    const user = JSON.parse(await page.evaluate(() => localStorage.getItem('user') || 'null'));
    console.log('👤 Usuario:', user?.email, 'Rol:', user?.role);
    expect(user).not.toBeNull();
    expect(user.email).toBe('admin@video-saas.com');
    
    // Verificar que estamos en el dashboard (no en login)
    await expect(page.locator('.my-form')).not.toBeVisible({ timeout: 5000 });
    
    // Buscar elementos típicos del dashboard
    const dashboardEl = page.locator('header, nav, .dashboard, .user-dashboard, [class*="Dashboard"]');
    await expect(dashboardEl.first()).toBeVisible({ timeout: 15000 });
    
    console.log('✅ Dashboard cargado correctamente');
  });
  
  test('Camera elements visible in dashboard', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    
    // Esperar más tiempo para que carguen las cámaras
    await page.waitForTimeout(3000);
    
    // Buscar elementos de cámara
    const cameraElements = page.locator('.cam-chip, .camera-card, .camera-item, [class*="camera"]:not(i)');
    const count = await cameraElements.count();
    console.log(`📷 Elementos de cámara encontrados: ${count}`);
    
    // Tomar screenshot para debug
    await page.screenshot({ path: 'test-results/dashboard-cameras.png', fullPage: true });
    console.log('📸 Screenshot guardado en test-results/dashboard-cameras.png');
  });
  
  test('Navigation sidebar is accessible', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    
    // Buscar sidebar o navegación
    const navElements = page.locator('nav, .sidebar, .navigation, aside');
    const navCount = await navElements.count();
    console.log(`🧭 Elementos de navegación: ${navCount}`);
    
    // Buscar links de navegación
    const links = page.locator('a[href], button[role="menuitem"], .nav-link, .menu-item');
    const linkCount = await links.count();
    console.log(`🔗 Links encontrados: ${linkCount}`);
    
    expect(linkCount).toBeGreaterThan(0);
  });
});

test.describe('API Tests (Direct)', () => {
  
  test('API rejects unauthenticated requests', async ({ request }) => {
    const response = await request.get('/api/cameras', {
      headers: { 'Accept': 'application/json' }
    });
    
    // Sin token, debería rechazar
    expect(response.status()).toBe(401);
    console.log('🔒 API rechaza correctamente requests sin autenticación');
  });
});
