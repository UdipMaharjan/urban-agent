import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './e2e',
  testIgnore: ['pipeline.spec.ts'],
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  outputDir: '../.artifacts/browser-tests',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:3000',
    channel: 'msedge',
    headless: true,
    viewport: { width: 1440, height: 1000 },
    trace: 'retain-on-failure',
  },
});
