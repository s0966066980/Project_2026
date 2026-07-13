import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  retries: 0,
  reporter: 'line',
  use: {
    baseURL: 'http://127.0.0.1:9080',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'cd .. && MEMBER_STORAGE_BACKEND=json DATABASE_URL= APP_ENV=test "${PYTHON_BIN:-.venv/bin/python}" -m uvicorn main:app --host 127.0.0.1 --port 9080',
    url: 'http://127.0.0.1:9080/live',
    reuseExistingServer: true,
    timeout: 30_000,
  },
});
