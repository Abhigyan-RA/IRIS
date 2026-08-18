import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for the single end-to-end journey.
 *
 * Only one path is covered end to end: the journey a reader actually takes through
 * the five screens. Everything else is covered by component tests, which are faster,
 * more precise about failures, and do not need a browser. An end-to-end suite that
 * tries to cover every screen becomes slow and flaky, and people start ignoring it.
 *
 * Two servers are started: a stub API with fixed replies, and the dashboard pointed
 * at it. Fixed replies mean the test can assert the exact figures a reader sees.
 */
const STUB_PORT = 8123;
const WEB_PORT = 3123;

export default defineConfig({
  testDir: './e2e',
  testMatch: /.*\.spec\.ts/,
  // A failing end-to-end test is a real signal, so it is never retried into passing.
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: `http://localhost:${String(WEB_PORT)}`,
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `npx tsx e2e/stub-api.ts`,
      url: `http://localhost:${String(STUB_PORT)}/api/risk-map`,
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      // Built and served in production mode rather than run in development mode. The
      // production server is what ships, and the address of the API is baked into the
      // browser bundle at build time, so building here exercises that step too.
      command: `npx next build && npx next start --port ${String(WEB_PORT)}`,
      url: `http://localhost:${String(WEB_PORT)}/risk-map`,
      reuseExistingServer: false,
      timeout: 240_000,
      env: {
        NEXT_PUBLIC_API_URL: `http://localhost:${String(STUB_PORT)}`,
      },
    },
  ],
});
