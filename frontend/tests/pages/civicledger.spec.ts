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
