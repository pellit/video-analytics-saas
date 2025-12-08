import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 10000 },
  fullyParallel: false,
  workers: 1, // Ejecutar tests en serie para evitar rate limiting
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: process.env.E2E_BASE_URL || 'https://dev.pellit.com.ar',
    trace: 'on-first-retry',
    navigationTimeout: 60000,
    actionTimeout: 10000,
    ignoreHTTPSErrors: true,
  },
  projects: [
    { 
      name: 'chromium', 
      use: { 
        ...devices['Desktop Chrome'],
        headless: true,
        viewport: { width: 1280, height: 720 },
        launchOptions: {
          args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
        },
      } 
    },
  ],
  // No webServer - la app ya está corriendo en dev.pellit.com.ar
});
