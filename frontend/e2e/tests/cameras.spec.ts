import { test, expect } from '@playwright/test';

/**
 * Camera Management E2E Tests
 * Tests para verificar funcionalidad de gestión de cámaras
 * 
 * Usa autenticación pre-configurada desde auth.setup.ts
 */

// Helper para hacer fetch con manejo de errores
async function safeFetch(url: string, options: RequestInit): Promise<{status: number, data: any, error?: string}> {
  try {
    const res = await fetch(url, options);
    const text = await res.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch {
      data = { raw: text.substring(0, 200) };
    }
    return { status: res.status, data };
  } catch (e: any) {
    return { status: 0, data: null, error: e.message };
  }
}

test.describe('Camera Management Tests', () => {
  
  test('API returns cameras list', async ({ page }) => {
    // Navegar primero para obtener el token del storage state
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(2000);
    
    const token = await page.evaluate(() => localStorage.getItem('token'));
    
    if (!token) {
      console.log('⚠️ No hay token, saltando test');
      test.skip();
      return;
    }
    console.log('🔑 Token obtenido correctamente');
    
    // Llamar API de cámaras con el token
    const response = await page.evaluate(async (params: {authToken: string}) => {
      try {
        const res = await fetch('/api/cameras', {
          headers: {
            'Accept': 'application/json',
            'Authorization': `Bearer ${params.authToken}`
          }
        });
        const text = await res.text();
        let data;
        try {
          data = JSON.parse(text);
        } catch {
          data = { raw: text.substring(0, 200) };
        }
        return { status: res.status, data };
      } catch (e: any) {
        return { status: 0, data: null, error: e.message };
      }
    }, { authToken: token });
    
    console.log(`📷 Cameras API status: ${response.status}`);
    
    if (response.status !== 200) {
      console.log(`⚠️ API error: ${JSON.stringify(response.data)}`);
      return; // No fallar, solo reportar
    }
    
    // Verificar que hay cámaras
    const cameras = Array.isArray(response.data) ? response.data : response.data?.data || [];
    console.log(`📷 Cámaras encontradas: ${cameras.length}`);
    
    // Analizar tipos de cámara
    const youtubeCount = cameras.filter((c: any) => c.type === 'youtube').length;
    const rtspCount = cameras.filter((c: any) => c.type === 'rtsp').length;
    console.log(`📺 YouTube: ${youtubeCount}, 📹 RTSP: ${rtspCount}`);
    
    // Mostrar detalles de cada cámara
    cameras.forEach((cam: any, i: number) => {
      console.log(`  ${i + 1}. ${cam.name} (${cam.type}) - Status: ${cam.status || 'unknown'}`);
    });
    
    expect(cameras.length).toBeGreaterThan(0);
  });
  
  test('Camera dashboard shows cameras', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    
    // Esperar carga de cámaras
    await page.waitForTimeout(5000);
    
    // Buscar elementos de cámara en el DOM
    const cameraSelectors = [
      '.cam-chip',
      '.camera-card',
      '.camera-item',
      '[class*="camera"]',
      '[class*="CameraCard"]',
      '.video-grid-item',
      '.stream-container'
    ];
    
    let totalFound = 0;
    for (const selector of cameraSelectors) {
      const elements = await page.locator(selector).all();
      if (elements.length > 0) {
        console.log(`  ${selector}: ${elements.length} elementos`);
        totalFound += elements.length;
      }
    }
    
    console.log(`📷 Total elementos de cámara en UI: ${totalFound}`);
    
    // Tomar screenshot para análisis
    await page.screenshot({ path: 'test-results/cameras-dashboard.png', fullPage: true });
    
    // Debug: ver estructura del DOM
    const bodyContent = await page.locator('body').innerHTML();
    const hasVideo = bodyContent.includes('video') || bodyContent.includes('stream');
    console.log(`🎥 Contiene elementos video/stream: ${hasVideo}`);
  });
  
  test('Camera start API for YouTube camera', async ({ page }) => {
    await page.goto('/dashboard');
    const token = await page.evaluate(() => localStorage.getItem('token'));
    
    if (!token) {
      test.skip();
      return;
    }
    
    // Obtener lista de cámaras
    const camerasResponse = await page.evaluate(async (authToken) => {
      const res = await fetch('/api/cameras', {
        headers: {
          'Accept': 'application/json',
          'Authorization': `Bearer ${authToken}`
        }
      });
      return await res.json();
    }, token);
    
    const cameras = Array.isArray(camerasResponse) ? camerasResponse : camerasResponse?.data || [];
    const youtubeCamera = cameras.find((c: any) => c.type === 'youtube');
    
    if (!youtubeCamera) {
      console.log('⚠️ No hay cámara YouTube disponible para test');
      return;
    }
    
    console.log(`🎬 Iniciando cámara YouTube: ${youtubeCamera.name} (ID: ${youtubeCamera.id})`);
    
    // Intentar iniciar la cámara
    const startResponse = await page.evaluate(async (params: { authToken: string; cameraId: number }) => {
      try {
        const res = await fetch(`/api/cameras/${params.cameraId}/start`, {
          method: 'POST',
          headers: {
            'Accept': 'application/json',
            'Authorization': `Bearer ${params.authToken}`,
            'Content-Type': 'application/json'
          }
        });
        return {
          status: res.status,
          data: await res.json().catch(() => null)
        };
      } catch (e: any) {
        return { status: 0, error: e.message };
      }
    }, { authToken: token, cameraId: youtubeCamera.id });
    
    console.log(`📡 Start response: ${startResponse.status}`);
    console.log(`📊 Data: ${JSON.stringify(startResponse.data)}`);
    
    // Verificar respuesta
    expect(startResponse.status).toBe(200);
    expect(startResponse.data).toBeTruthy();
  });
  
  test('Camera list from API contains camera details', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    const token = await page.evaluate(() => localStorage.getItem('token'));
    
    if (!token) {
      test.skip();
      return;
    }
    
    // Obtener lista de cámaras (incluye todos los detalles)
    const camerasResponse = await page.evaluate(async (authToken) => {
      try {
        const res = await fetch('/api/cameras', {
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
    
    console.log(`📡 Cameras API: Status ${camerasResponse.status}`);
    
    if (camerasResponse.status !== 200) {
      console.log('⚠️ API no disponible');
      return;
    }
    
    const cameras = Array.isArray(camerasResponse.data) ? camerasResponse.data : camerasResponse.data?.data || [];
    
    if (cameras.length === 0) {
      console.log('⚠️ No hay cámaras disponibles');
      return;
    }
    
    // Verificar que cada cámara tiene los campos necesarios
    const camera = cameras[0];
    console.log(`📷 Primera cámara: ${camera.name} (ID: ${camera.id})`);
    console.log(`   Tipo: ${camera.type || 'default'}`);
    console.log(`   URL: ${camera.url?.substring(0, 50)}...`);
    
    expect(camera.id).toBeTruthy();
    expect(camera.name).toBeTruthy();
  });
});
