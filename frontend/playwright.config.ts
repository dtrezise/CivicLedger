import { defineConfig, devices } from "@playwright/test";

const liveProductionSmoke = Boolean(
  process.env.LIVE_PRODUCTION_SMOKE &&
    (process.env.PRODUCTION_BASE_URL || process.env.CIVICLEDGER_PRODUCTION_URL)
);

export default defineConfig({
  testDir: "./tests/pages",
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: liveProductionSmoke
      ? process.env.PRODUCTION_BASE_URL || process.env.CIVICLEDGER_PRODUCTION_URL
      : "http://127.0.0.1:4173",
    trace: "retain-on-failure",
  },
  webServer: liveProductionSmoke
    ? undefined
    : {
        command: "python3 -m http.server 4173 --directory ../pages-site",
        url: "http://127.0.0.1:4173",
        reuseExistingServer: !process.env.CI,
        timeout: 30_000,
      },
  projects: [
    {
      name: "desktop-chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1000 } },
    },
    {
      name: "mobile-chromium",
      use: {
        browserName: "chromium",
        viewport: { width: 390, height: 844 },
        deviceScaleFactor: 2,
        hasTouch: true,
        isMobile: true,
        userAgent: devices["iPhone 13"].userAgent,
      },
    },
  ],
});
