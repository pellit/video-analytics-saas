import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 120_000,
  expect: { timeout: 30000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: process.env.E2E_BASE_URL || 'https://dev.pellit.com.ar',
    trace: 'on-first-retry',
    navigationTimeout: 60000,
    actionTimeout: 30000,
    ignoreHTTPSErrors: true,
  },
  projects: [
    // Setup project: hace login una sola vez y guarda el estado
    {
      name: 'setup',
      testMatch: /auth\.setup\.ts/,
      use: {
        ...devices['Desktop Chrome'],
        headless: true,
        launchOptions: {
          args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
        },
      },
    },
    // Tests que dependen de autenticación
    { 
      name: 'chromium', 
      testMatch: /tests\/.*\.spec\.ts$/,
      use: { 
        ...devices['Desktop Chrome'],
        headless: true,
        viewport: { width: 1280, height: 720 },
        storageState: './e2e/.auth/user.json',
        launchOptions: {
          args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
        },
      },
      dependencies: ['setup'],
    },
  ],
});
