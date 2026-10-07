import { defineConfig, devices } from "@playwright/test";

const liveProductionSmoke = Boolean(
  process.env.LIVE_PRODUCTION_SMOKE &&
    (process.env.PRODUCTION_BASE_URL || process.env.CIVICLEDGER_PRODUCTION_URL)
);
const localPort = process.env.CIVICLEDGER_TEST_PORT || "4173";
const localBaseUrl = `http://127.0.0.1:${localPort}`;

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
      : localBaseUrl,
    trace: "retain-on-failure",
  },
  webServer: liveProductionSmoke
    ? undefined
    : {
        command: `python3 -m http.server ${localPort} --directory ../pages-site`,
        url: localBaseUrl,
        reuseExistingServer: false,
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
