import { expect, test } from "@playwright/test";
import { BASE_URL } from "../playwright.config";
import { canSeed, codeOf, createCheckout, seedCompleted, signup, waitForClaimLink } from "../helpers";

/**
 * Guest donation → fake checkout completed (`cli seed-completed`) → receipt in
 * Mailpit with a /claim?code= link → log in on accounts → claim → payment
 * attached + badge snippet shown.
 */
test.describe("claim", () => {
  test.skip(!canSeed, "E2E_SEED_CMD not set: cannot complete a fake checkout");

  test("claim a guest donation from the mailed code @critical", async ({ page }) => {
    const since = new Date();
    // Guest checkout: the page context is still logged out here.
    const { cs } = await createCheckout(page.request, {
      app: "3m4",
      kind: "donation",
      amount: 500,
      currency: "usd",
      return_to: `${BASE_URL}/`,
      origin: BASE_URL,
      lang: "en",
    });
    seedCompleted(cs);
    const link = await waitForClaimLink({ after: since });
    const code = codeOf(link);

    // Login gate: an anonymous visitor is sent to accounts; we create the user
    // through the API instead (same cookie jar) and open the link again.
    const { handle } = await signup(page.request);
    await page.goto(link);
    await expect(page.getByTestId("code")).toHaveValue(/[0-9A-Z]{4}-[0-9A-Z]{4}-[0-9A-Z]{4}-[0-9A-Z]{4}/);
    expect((await page.getByTestId("code").inputValue()).replace(/-/g, "")).toBe(code.toUpperCase().replace(/[-\s]/g, ""));
    await page.getByTestId("submit").click();
    await expect(page.getByTestId("claimed")).toBeVisible();
    await expect(page.getByTestId("claimed")).toContainText("3m4");
    await expect(page.getByTestId("badge-markdown")).toHaveValue(/\/badge\//);

    // The payment is on /me now; claiming the same code again fails with used_code.
    await page.goto("/me");
    await expect(page.getByTestId("me-handle")).toContainText(handle);
    await expect(page.getByTestId("payment-row")).toHaveCount(1);
    await page.goto(`/claim?code=${encodeURIComponent(code)}`);
    await page.getByTestId("submit").click();
    await expect(page.getByTestId("error")).toBeVisible();
  });

  test("an invalid code is rejected", async ({ page }) => {
    await signup(page.request);
    await page.goto("/claim");
    await page.getByTestId("code").fill("AAAA-AAAA-AAAA-AAAA");
    await page.getByTestId("submit").click();
    await expect(page.getByTestId("error")).toBeVisible();
    await expect(page.getByTestId("claimed")).toHaveCount(0);
  });
});
