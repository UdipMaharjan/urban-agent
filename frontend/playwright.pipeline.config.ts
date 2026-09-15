import { defineConfig } from '@playwright/test';
import base from './playwright.config';
export default defineConfig({
  ...base,
  testMatch: ['pipeline.spec.ts', 'workspace.spec.ts'],
  testIgnore: [],
  timeout: 60000,
  use: { ...base.use, baseURL: 'http://127.0.0.1:13001' },
  webServer: [
    {
      command:
        '.venv\\Scripts\\python.exe -m uvicorn browser_pipeline_server:app --app-dir tests --host 127.0.0.1 --port 18001',
      cwd: '..',
      url: 'http://127.0.0.1:18001/__test__/identity',
      reuseExistingServer: false,
    },
    {
      command: 'npm.cmd run dev -- --port 13001',
      url: 'http://127.0.0.1:13001',
      env: {
        BACKEND_API_URL: 'http://127.0.0.1:18001',
        NEXT_PUBLIC_API_BASE_URL: '/backend',
        NEXT_TELEMETRY_DISABLED: '1',
        URBANAGENT_TEST_BUILD_DIR: '.next/pipeline-browser',
      },
      reuseExistingServer: false,
      timeout: 120000,
    },
  ],
});
