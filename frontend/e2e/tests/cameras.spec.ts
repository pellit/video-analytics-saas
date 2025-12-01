import { test, expect } from '@playwright/test';

test.describe('Cameras UI', () => {
  test('Admin sees 3 default YouTube cameras in dashboard', async ({ page }) => {
    // Collect frontend console logs to help diagnose issues
    page.on('console', msg => console.log('PAGE LOG:', msg.text()));
    page.on('pageerror', err => console.log('PAGE ERROR:', err.toString()));
    const baseUrl = process.env.E2E_BASE_URL || 'http://localhost:5173';
    await page.goto(baseUrl + '/');

    // Wait for login form and Login as SuperAdmin
    await page.waitForSelector('input[placeholder="Email"]', { timeout: 60000 });
    await page.locator('input[placeholder="Email"]').fill('admin@video-saas.com');
    await page.locator('input[placeholder="Contraseña"]').fill('admin123');
    await page.locator('button:has-text("Entrar")').click();

    // Wait for token and dashboard
    await page.waitForFunction(() => !!localStorage.getItem('token'));

    // Wait for camera chips to load
    await page.waitForSelector('.cam-chip');

    const chips = await page.locator('.cam-chip').allTextContents();
    expect(chips).toContain('Cámara YouTube 1');
    expect(chips).toContain('Cámara YouTube 2');
    expect(chips).toContain('Cámara YouTube 3');
  });
});
