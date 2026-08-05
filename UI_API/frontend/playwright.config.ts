import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  // The suite models one physical Kiosk device with durable, device-scoped flows.
  // Running files in parallel would make independent browser contexts contend for
  // the same active entry flow and would not represent a supported deployment.
  workers: 1,
  retries: 0,
  reporter: 'line',
  use: {
    baseURL: 'http://127.0.0.1:9080',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{
    name: 'chromium',
    use: {
      ...devices['Desktop Chrome'],
      launchOptions: {
        args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'],
      },
    },
  }],
  webServer: {
    command: 'cd .. && env -u MEMBER_STORAGE_BACKEND -u DATABASE_PORT APP_ENV=test DATABASE_BACKEND=sqlite DATABASE_TOPOLOGY=single DATABASE_URL= RUNTIME_DATA_ROOT="${PLAYWRIGHT_RUNTIME_DATA_ROOT:-${TMPDIR:-/tmp}/project-2026-playwright-${PPID}}" "${PYTHON_BIN:-python}" -m uvicorn main:app --host 127.0.0.1 --port 9080',
    url: 'http://127.0.0.1:9080/live',
    reuseExistingServer: true,
    timeout: 30_000,
  },
});
