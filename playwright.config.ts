import { defineConfig, devices } from "@playwright/test";

/**
 * Dashboard e2e against Light's cached Scenario A loop.
 * Starts uvicorn (USE_CACHED_STREAM=True) + Vite when not already running.
 */
export default defineConfig({
  testDir: "./tests",
  testMatch: "**/e2e_ui.spec.ts",
  timeout: 120_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://127.0.0.1:5173",
    trace: "on-first-retry",
  },
  webServer: [
    {
      command:
        "USE_CACHED_STREAM=True SCENARIO=scenario_a_galactic_ccsn VOICE_MODE=off BREAKOUT_DISABLE_AUTOSTART=1 python3 -m uvicorn backend.app:app --host 127.0.0.1 --port 8000",
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: "npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
