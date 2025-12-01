import { test, expect } from '@playwright/test';

test.describe('Detections live update', () => {
  test('When worker posts detection UI shows it in list', async ({ page, request }) => {
    // Collect frontend console logs to help diagnose issues
    page.on('console', msg => console.log('PAGE LOG:', msg.text()));
    page.on('pageerror', err => console.log('PAGE ERROR:', err.toString()));
    const baseUrl = process.env.E2E_BASE_URL || 'http://localhost:5173';
    await page.goto(baseUrl + '/');

    // login as admin (wait for login form)
    await page.waitForSelector('input[placeholder="Email"]', { timeout: 60000 });
    await page.locator('input[placeholder="Email"]').fill('admin@video-saas.com');
    await page.locator('input[placeholder="Contraseña"]').fill('admin123');
    await page.locator('button:has-text("Entrar")').click();

    await page.waitForFunction(() => !!localStorage.getItem('token'))
    const token = await page.evaluate(() => localStorage.getItem('token'))
    expect(token).toBeTruthy();

    // ensure camera exists and select first
    await page.waitForSelector('.cam-chip')
    await page.click('.cam-chip')
    // Start analysis
    await page.locator('button.btn-start').click()

    // Post a detection through worker API
    const apiBase = process.env.E2E_API_URL || 'http://localhost:8000/api';
    const res = await request.post(`${apiBase}/worker/detections`, {
      data: {
        camera_id: 1,
        event: 'person_detected',
        payload: { label: 'person', score: 0.89, bbox: [10,10,100,200] }
      },
      headers: { 'X-WORKER-KEY': process.env.WORKER_API_KEY || 'dev_worker_key_123' }
    });
    expect(res.status()).toBe(201);

    // Wait for detection to show up in the UI
    await page.waitForSelector('.detections-panel');
    // Ensure at least one list item displays the detection
    await expect(page.locator('.detections-panel')).toContainText('person');
  });
});
