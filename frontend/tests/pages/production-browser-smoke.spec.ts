import { expect, test } from "@playwright/test";

const liveSmokeEnabled = Boolean(
  process.env.LIVE_PRODUCTION_SMOKE &&
    (process.env.PRODUCTION_BASE_URL || process.env.CIVICLEDGER_PRODUCTION_URL)
);

test.describe("live mobile production browser smoke", () => {
  test.skip(!liveSmokeEnabled, "Set LIVE_PRODUCTION_SMOKE=1 and PRODUCTION_BASE_URL to run live smoke.");

  test("loads the public workbench without mobile overflow", async ({ page }, testInfo) => {
    test.skip(!testInfo.project.name.startsWith("mobile"), "Mobile project only.");
    const pageErrors: string[] = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));

    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page.getByRole("heading", { name: "Career trade activity" })).toBeVisible();
    await expect(page.locator("#tradeChart")).toBeVisible();
    await expect(page.locator("#officialSearch")).toBeVisible();
    await expect(page.locator("#eventSearch")).toBeVisible();
    await expect(page.locator("#transactionRows tr[data-trade-id]").first()).toBeVisible();

    const dimensions = await page.evaluate(() => ({
      body: document.body.scrollWidth,
      viewport: document.documentElement.clientWidth,
      nav: document.querySelector<HTMLElement>(".site-nav")?.scrollWidth || 0,
      navClient: document.querySelector<HTMLElement>(".site-nav")?.clientWidth || 0,
    }));
    expect(dimensions.body).toBeLessThanOrEqual(dimensions.viewport);
    expect(dimensions.nav).toBeLessThanOrEqual(dimensions.navClient);
    expect(pageErrors).toEqual([]);
  });
});
