import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Career trade activity" })).toBeVisible();
  await expect(page.locator("#transactionRows tr[data-trade-id]").first()).toBeVisible();
});

test("persists density, event categories, and selected range", async ({ page }) => {
  const density = page.getByLabel("Cluster density");
  await density.fill("112");
  await page.getByLabel("SEC filing").uncheck();
  await page.getByRole("button", { name: "Select visible" }).click();

  await expect(page).toHaveURL(/density=112/);
  await expect(page).toHaveURL(/eventcats=/);
  await expect(page).toHaveURL(/brush=0\.00-100\.00/);
  await expect(page.getByText("7,179 of 7,179 records selected")).toBeVisible();

  await page.reload();
  await expect(density).toHaveValue("112");
  await expect(page.getByLabel("SEC filing")).not.toBeChecked();
  await expect(page.getByText("7,179 of 7,179 records selected")).toBeVisible();
});

test("shows neutral market comparison for a selected ticker transaction", async ({ page }) => {
  await page.getByLabel("Transactions").selectOption("ticker:JPM");
  const firstTrade = page.locator("#transactionRows tr[data-trade-id]").first();
  await expect(firstTrade).toBeVisible();
  await firstTrade.click();

  await expect(page.locator("#marketShell")).toBeVisible();
  await expect(page.getByText("Normalized movement around the disclosed transaction")).toBeVisible();
  await expect(page.locator("#marketComparisonSummary table")).toBeVisible();
  await expect(page.getByText(/descriptive price changes around a reported date/)).toBeVisible();
});

test("supports chart zoom, adding an official, and selecting an event", async ({ page }) => {
  const selectedOfficials = page.locator("#selectedOfficials .official-chip");
  const initialOfficialCount = await selectedOfficials.count();
  expect(initialOfficialCount).toBeGreaterThan(0);

  await page.locator("#tradeChart").focus();
  await page.locator("#tradeChart").press("+");
  await expect(page).toHaveURL(/zoom=15\.00-85\.00/);
  await page.locator("#tradeChart").press("0");
  await expect(page).not.toHaveURL(/zoom=/);

  await selectedOfficials.first().getByRole("button").click();
  await expect(selectedOfficials).toHaveCount(initialOfficialCount - 1);

  const officialSearch = page.locator("#officialSearch");
  await officialSearch.fill("Obama");
  const unselectedOfficial = page.locator("#officialResults [data-official-id][aria-selected='false']").first();
  await expect(unselectedOfficial).toBeVisible();
  await unselectedOfficial.click();
  await expect(selectedOfficials).toHaveCount(initialOfficialCount);

  const eventSearch = page.locator("#eventSearch");
  await eventSearch.fill("order");
  await expect(page.locator("#eventResults [data-event-id]").first()).toBeVisible();
  await page.locator("#eventResults [data-event-id]").first().click();
  await expect(page).toHaveURL(/event=[^&]+/);
  await expect(page.locator("#eventDetailTitle")).not.toHaveText("Select an event marker");
  await expect(page.getByRole("button", { name: "Event" })).toBeEnabled();
});

test("shows source-backed transaction evidence for a selected row", async ({ page }) => {
  const firstTrade = page.locator("#transactionRows tr[data-trade-id]").first();
  await firstTrade.click();

  await expect(page.locator("#recordDetailTitle")).not.toHaveText("Select a transaction marker or row");
  await expect(page.locator("#recordDetail")).toContainText("Transaction evidence");
  await expect(page.locator("#recordDetail")).toContainText("Interpretation boundary");
  await expect(page.locator("#recordDetail a, #recordDetail .state-label").first()).toBeVisible();
});

test("shows structured recovery details when required data cannot load", async ({ page }) => {
  await page.route("**/data/manifest.json", (route) =>
    route.fulfill({ status: 503, contentType: "application/json", body: '{"error":"fixture"}' })
  );
  await page.goto("/");

  await expect(page.locator("#loadFailure")).toBeVisible();
  await expect(page.locator("#loadFailureCode")).toHaveText("HTTP_503");
  await expect(page.locator("#loadFailureResource")).toHaveText("./data/manifest.json");
  await expect(page.locator("#retryDataButton")).toBeVisible();
  await expect(page.locator("#loadFailure a")).toHaveAttribute(
    "href",
    "https://dtrezise.github.io/CivicLedger/"
  );
});

test("keeps the public workbench inside the mobile viewport", async ({ page }, testInfo) => {
  test.skip(!testInfo.project.name.startsWith("mobile"), "Mobile-only layout assertion");
  const dimensions = await page.evaluate(() => ({
    body: document.body.scrollWidth,
    viewport: document.documentElement.clientWidth,
    nav: document.querySelector<HTMLElement>(".site-nav")?.scrollWidth || 0,
    navClient: document.querySelector<HTMLElement>(".site-nav")?.clientWidth || 0,
  }));
  expect(dimensions.body).toBeLessThanOrEqual(dimensions.viewport);
  expect(dimensions.nav).toBeLessThanOrEqual(dimensions.navClient);
});
