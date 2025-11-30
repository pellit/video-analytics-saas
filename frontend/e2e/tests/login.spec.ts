import { test, expect } from '@playwright/test';

test.describe('Authentication flow', () => {
  test('Super Admin can log in (UI)', async ({ page }) => {
    // 1) Open the frontend (respect base url env var)
    const baseUrl = process.env.E2E_BASE_URL || 'http://localhost:5173';
    await page.goto(baseUrl + '/');

    // 2) Fill login form
    await page.locator('input[placeholder="Email"]').fill('admin@video-saas.com');
    await page.locator('input[placeholder="Contraseña"]').fill('admin123');
    await page.locator('button:has-text("Entrar")').click();

    // 3) Wait for token to set in localStorage and user to be present
    await page.waitForFunction(() => !!localStorage.getItem('token'));
    const token = await page.evaluate(() => localStorage.getItem('token'));
    expect(token).toBeTruthy();

    // 4) Check user object and UI elements
    const user = JSON.parse(await page.evaluate(() => localStorage.getItem('user') || 'null'));
    expect(user).not.toBeNull();
    expect(user.email).toBe('admin@video-saas.com');
    expect(user.role).toBe('superadmin');

    // 5) Admin button visible after login
    await expect(page.locator('button.btn-admin')).toBeVisible();

    // 6) La lista de cámaras debe contener al menos 3 cámaras (las seeded)
    await page.waitForSelector('.cam-chip')
    await expect(page.locator('.cam-chip')).toHaveCount(3)

    // 7) Comprobar que al seleccionar la primera cámara se puede ver el vídeo (embed o stream)
    await page.click('.cam-chip')
    // Hacer click en Iniciar si existe
    const startButton = page.locator('button.btn-start')
    if (await startButton.count() > 0) {
      await startButton.click()
    }
    // Comprobar que hay iframe (YouTube embed) o imagen de stream
    await expect(page.locator('iframe, img.stream')).toBeVisible()
  });
});
