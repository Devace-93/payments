import { expect, test } from "@playwright/test";
import { canSeed, catalog, csOf, seedCompleted } from "../helpers";

/**
 * /donate: presets + currency from the catalog, currency switch updates the
 * presets, "Donate with card" POSTs /api/checkout and follows the (fake Stripe)
 * URL to /success?cs=, which shows the guest claim explanation once the
 * checkout is completed (`cli seed-completed`).
 */
test.describe("donate", () => {
  test("renders presets and currency for the app @critical", async ({ page }) => {
    const cat = await catalog(page.request, "3m4");
    await page.goto("/donate?app=3m4&currency=usd");
    await expect(page.getByRole("heading", { level: 1 })).toContainText(cat.app.name);
    await expect(page.getByTestId("currency")).toHaveValue("usd");
    await expect(page.getByTestId("preset")).toHaveCount(cat.donation.presets.usd.length);
    // Guest: the claim explanation is shown; a GitHub Sponsors button only when configured.
    await expect(page.getByTestId("claim-explainer")).toBeVisible();
    if (cat.github_sponsors_url) await expect(page.getByTestId("sponsor-github")).toBeVisible();
    else await expect(page.getByTestId("sponsor-github")).toHaveCount(0);
  });

  test("changing the currency updates the presets", async ({ page }) => {
    const cat = await catalog(page.request, "3m4");
    test.skip(!cat.currencies.includes("mxn"), "mxn not in CURRENCIES");
    await page.goto("/donate?app=3m4&currency=usd");
    const before = await page.getByTestId("preset").allTextContents();
    await page.getByTestId("currency").selectOption("mxn");
    await expect(page.getByTestId("preset")).toHaveCount(cat.donation.presets.mxn.length);
    await expect.poll(async () => page.getByTestId("preset").allTextContents()).not.toEqual(before);
    await expect(page.locator("#custom-amount").locator("..")).toContainText("MXN");
    // The choice is remembered (CONTRACT.md §7).
    expect(await page.evaluate(() => localStorage.getItem("3m4.currency"))).toBe("mxn");
  });

  test("enforces the server minimum client-side", async ({ page }) => {
    const cat = await catalog(page.request, "3m4");
    await page.goto("/donate?app=3m4&currency=usd");
    await page.getByTestId("custom-amount").fill(String((cat.donation.min.usd - 100) / 100));
    await expect(page.getByTestId("amount-error")).toBeVisible();
    await expect(page.getByTestId("submit")).toBeDisabled();
  });

  test("donate with card creates a checkout and lands on /success @critical", async ({ page }) => {
    await page.goto("/donate?app=3m4&amount=500&currency=usd");
    await expect(page.getByTestId("preset").first()).toBeVisible();
    const [res] = await Promise.all([
      page.waitForResponse((r) => r.url().includes("/api/checkout") && r.request().method() === "POST"),
      page.getByTestId("submit").click(),
    ]);
    expect(res.status()).toBe(201);
    // Fake Stripe sends us straight to our own success page (Qwik City adds a trailing slash).
    await expect(page).toHaveURL(/\/success\/?\?cs=cs_fake_/);
    const cs = csOf(page.url());
    await expect(page.getByTestId("success-waiting")).toBeVisible();

    test.skip(!canSeed, "E2E_SEED_CMD not set: cannot complete the fake checkout");
    seedCompleted(cs);
    await expect(page.getByTestId("success-done")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("success-done")).toHaveAttribute("data-kind", "donation");
    await expect(page.getByTestId("claim-explainer")).toBeVisible();
    await expect(page.getByTestId("create-account")).toHaveAttribute("href", /\/signup\?return_to=.*%2Fclaim/);
  });
});
