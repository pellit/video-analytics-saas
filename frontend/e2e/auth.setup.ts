import { test as setup, expect } from '@playwright/test';

const authFile = './e2e/.auth/user.json';

setup('authenticate', async ({ page }) => {
  console.log('🔐 Iniciando autenticación...');
  
  // Capturar errores de consola y red
  page.on('console', msg => console.log('BROWSER:', msg.type(), msg.text()));
  page.on('pageerror', err => console.log('PAGE ERROR:', err.message));
  page.on('requestfailed', req => console.log('REQUEST FAILED:', req.url(), req.failure()?.errorText));
  
  // Navegar al login
  await page.goto('/login');
  await page.waitForLoadState('networkidle');
  
  // Screenshot inicial
  await page.screenshot({ path: './test-results/01-login-page.png' });
  
  // Esperar que la página cargue completamente
  await page.waitForTimeout(2000);
  
  // Verificar que estamos en la página de login
  const emailInput = page.locator('input[type="email"], input[placeholder*="correo"], input[placeholder*="mail"]');
  await expect(emailInput).toBeVisible({ timeout: 30000 });
  
  // Credenciales de prueba
  const testEmail = 'admin@video-saas.com';
  const testPassword = 'admin123';
  
  console.log(`📧 Ingresando credenciales para: ${testEmail}`);
  
  // Completar formulario de login
  await emailInput.fill(testEmail);
  
  const passwordInput = page.locator('input[type="password"]');
  await expect(passwordInput).toBeVisible();
  await passwordInput.fill(testPassword);
  
  // Screenshot antes de submit
  await page.screenshot({ path: './test-results/02-before-submit.png' });
  
  // Click en el botón de submit
  const submitButton = page.locator('button[type="submit"], button:has-text("Entrar"), button:has-text("Login"), button:has-text("Iniciar")');
  await expect(submitButton).toBeVisible();
  
  // Interceptar la llamada a la API de login
  const loginResponsePromise = page.waitForResponse(resp => 
    resp.url().includes('/api/login') && resp.request().method() === 'POST',
    { timeout: 60000 }
  );
  
  await submitButton.click();
  console.log('⏳ Esperando respuesta de login...');
  
  try {
    const loginResponse = await loginResponsePromise;
    console.log(`📡 Login response: ${loginResponse.status()}`);
    const responseBody = await loginResponse.text();
    console.log(`📦 Response body: ${responseBody.substring(0, 200)}`);
    
    if (loginResponse.status() !== 200) {
      await page.screenshot({ path: './test-results/03-login-error.png' });
      throw new Error(`Login failed with status ${loginResponse.status()}: ${responseBody}`);
    }
  } catch (e: any) {
    console.log('❌ Error esperando respuesta:', e.message);
    await page.screenshot({ path: './test-results/03-login-error.png' });
    throw e;
  }
  
  // Esperar que el token se guarde
  console.log('⏳ Esperando token en localStorage...');
  await page.waitForFunction(() => {
    const token = localStorage.getItem('token');
    return !!token;
  }, { timeout: 30000 });
  
  const currentUrl = page.url();
  console.log(`📍 URL actual: ${currentUrl}`);
  
  // Verificar que el token está en localStorage
  const token = await page.evaluate(() => localStorage.getItem('token'));
  expect(token).toBeTruthy();
  console.log(`🔑 Token obtenido: ${token?.substring(0, 20)}...`);
  
  // Navegar manualmente al dashboard si es necesario
  if (!currentUrl.includes('dashboard')) {
    console.log('🔄 Navegando manualmente al dashboard...');
    await page.goto('/dashboard');
    // No usar networkidle porque SSE mantiene conexión abierta
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(3000); // Dar tiempo a que cargue
  }
  
  // Screenshot final
  await page.screenshot({ path: './test-results/04-dashboard.png' });
  
  console.log('✅ Login exitoso, guardando estado de autenticación...');
  
  // Guardar el estado de autenticación
  await page.context().storageState({ path: authFile });
  
  console.log(`💾 Estado guardado en: ${authFile}`);
});
