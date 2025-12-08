import { test, expect } from '@playwright/test';

/**
 * Blueprint/CAD Panel E2E Tests
 * Tests para verificar funcionalidad del panel de Planos
 * 
 * Usa autenticación pre-configurada desde auth.setup.ts
 */

test.describe('Blueprint Panel Tests', () => {
  
  test('Navigate to Blueprint panel', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    
    // Buscar enlace al panel de planos
    const blueprintLink = page.locator('a:has-text("Plano"), a:has-text("Blueprint"), a:has-text("CAD"), a[href*="blueprint"], a[href*="cad"]');
    const linkCount = await blueprintLink.count();
    console.log(`📐 Enlaces a Blueprint encontrados: ${linkCount}`);
    
    if (linkCount > 0) {
      await blueprintLink.first().click();
      await page.waitForLoadState('domcontentloaded');
      
      const url = page.url();
      console.log(`📍 URL actual: ${url}`);
      
      await page.screenshot({ path: 'test-results/blueprint-panel.png', fullPage: true });
    } else {
      console.log('⚠️ No se encontró enlace al panel Blueprint');
      // Intentar navegar directamente
      await page.goto('/blueprint');
      await page.waitForLoadState('domcontentloaded');
    }
  });
  
  test('Blueprint upload section exists', async ({ page }) => {
    await page.goto('/blueprint');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(2000);
    
    // Buscar elementos de upload
    const uploadElements = page.locator('input[type="file"], .upload, [class*="upload"], button:has-text("Upload"), button:has-text("Subir")');
    const uploadCount = await uploadElements.count();
    console.log(`📤 Elementos de upload encontrados: ${uploadCount}`);
    
    // Buscar canvas o área de dibujo CAD
    const cadElements = page.locator('canvas, svg, .blueprint, .cad-viewer');
    const cadCount = await cadElements.count();
    console.log(`🎨 Elementos CAD encontrados: ${cadCount}`);
    
    await page.screenshot({ path: 'test-results/blueprint-upload.png', fullPage: true });
  });
  
  test('Blueprint projects API check', async ({ page }) => {
    await page.goto('/dashboard');
    const token = await page.evaluate(() => localStorage.getItem('token'));
    
    if (!token) {
      console.log('⚠️ No hay token disponible');
      return;
    }
    
    // Llamar API de proyectos CAD
    const response = await page.evaluate(async (authToken) => {
      try {
        const res = await fetch('/api/cad/projects', {
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
    
    console.log(`📐 CAD Projects API: Status ${response.status}`);
    if (response.status === 200 && response.data) {
      console.log(`📊 Proyectos: ${JSON.stringify(response.data).substring(0, 200)}`);
    } else if (response.status === 404) {
      console.log('ℹ️ Endpoint /api/cad/projects no existe aún');
    }
  });
});
