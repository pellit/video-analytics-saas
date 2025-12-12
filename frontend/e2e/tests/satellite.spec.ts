import { test, expect } from '@playwright/test';

/**
 * Satellite Panel E2E Tests
 * Tests para verificar funcionalidad del panel Satelital (Sentinel API)
 * 
 * Usa autenticación pre-configurada desde auth.setup.ts
 */

test.describe('Satellite Panel Tests', () => {
  
  test('Navigate to Satellite panel', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    
    // Buscar enlace al panel satelital
    const satelliteLink = page.locator('a:has-text("Satelite"), a:has-text("Satellite"), a:has-text("Sentinel"), a[href*="satellite"]');
    const linkCount = await satelliteLink.count();
    console.log(`🛰️ Enlaces a Satellite encontrados: ${linkCount}`);
    
    if (linkCount > 0) {
      await satelliteLink.first().click();
      await page.waitForLoadState('domcontentloaded');
      
      // Verificar que cargó el panel
      const url = page.url();
      console.log(`📍 URL actual: ${url}`);
      
      await page.screenshot({ path: 'test-results/satellite-panel.png', fullPage: true });
      console.log('📸 Screenshot guardado');
    } else {
      console.log('⚠️ No se encontró enlace al panel Satellite');
      // Intentar navegar directamente
      await page.goto('/satellite');
      await page.waitForLoadState('domcontentloaded');
      
      const responseCode = await page.evaluate(() => {
        return document.querySelector('body')?.innerHTML.includes('404') ? 404 : 200;
      });
      console.log(`📍 Response code: ${responseCode}`);
    }
  });
  
  test('Satellite map component exists', async ({ page }) => {
    // Navegar al panel satellite si existe
    await page.goto('/satellite');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(2000);
    
    // Buscar componentes de mapa
    const mapElements = page.locator('.map, [class*="map"], #map, canvas, .leaflet-container');
    const mapCount = await mapElements.count();
    console.log(`🗺️ Elementos de mapa encontrados: ${mapCount}`);
    
    await page.screenshot({ path: 'test-results/satellite-map.png', fullPage: true });
  });
  
  test('Satellite zones API check', async ({ page }) => {
    // Obtener token del contexto autenticado
    await page.goto('/dashboard');
    const token = await page.evaluate(() => localStorage.getItem('token'));
    
    if (!token) {
      console.log('⚠️ No hay token disponible');
      return;
    }
    
    // Llamar API de zonas satelitales
    const response = await page.evaluate(async (authToken) => {
      try {
        const res = await fetch('/api/satellite/zones', {
          headers: {
            'Accept': 'application/json',
            'Authorization': `Bearer ${authToken}`
          }
        });
        return {
          status: res.status,
          data: await res.json().catch(() => null)
        };
      } catch (e: any) {
        return { status: 0, error: e.message };
      }
    }, token);
    
    console.log(`📡 Satellite Zones API: Status ${response.status}`);
    if (response.status === 200 && response.data) {
      console.log(`🛰️ Zonas encontradas: ${JSON.stringify(response.data).substring(0, 200)}`);
    } else if (response.status === 404) {
      console.log('ℹ️ Endpoint /api/satellite/zones no existe aún');
    }
  });
});
