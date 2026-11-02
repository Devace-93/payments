import { expect, test } from "@playwright/test";
import { ACCOUNTS_URL, BASE_URL } from "../playwright.config";
import { catalog, signup } from "../helpers";

/**
 * /subscribe: the login gate sends an anonymous visitor to accounts' hosted
 * login with return_to = this exact URL; a logged-in user sees the plan card.
 */
test.describe("subscribe", () => {
  const path = "/subscribe?app=retro&price=pro_monthly&currency=usd";

  test("unauthenticated → accounts login with the exact return_to @critical", async ({ page }) => {
    await page.goto(path);
    await page.waitForURL((u) => u.origin === ACCOUNTS_URL && u.pathname.replace(/\/$/, "") === "/login", { timeout: 20_000 });
    const back = new URL(page.url()).searchParams.get("return_to");
    // Qwik City normalises the pathname with a trailing slash before the query string.
    expect(back?.replace("/subscribe/?", "/subscribe?")).toBe(`${BASE_URL}${path}`);
  });

  test("logged in → plan card with amount and interval", async ({ page }) => {
    const cat = await catalog(page.request, "retro");
    const plan = cat.products.find((p) => p.key === "pro_monthly");
    test.skip(!plan, "retro has no pro_monthly in the catalog");
    const { handle } = await signup(page.request);
    await page.goto(path);
    await expect(page.getByTestId("subscribing-as")).toContainText(handle);
    await expect(page.getByTestId("plan-card")).toContainText(plan!.label);
    await expect(page.getByTestId("plan-amount")).toContainText("5");
    await expect(page.getByTestId("currency")).toHaveValue("usd");
  });

  test("logged in → Continue to Stripe creates a subscription checkout", async ({ page }) => {
    const cat = await catalog(page.request, "retro");
    test.skip(!cat.products.some((p) => p.key === "pro_monthly"), "retro has no pro_monthly in the catalog");
    await signup(page.request);
    await page.goto(path);
    await expect(page.getByTestId("plan-card")).toBeVisible();
    const submit = page.getByTestId("submit");
    test.skip(await submit.isDisabled(), "subscriptions feature is off");
    const [res] = await Promise.all([
      page.waitForResponse((r) => r.url().includes("/api/checkout") && r.request().method() === "POST"),
      submit.click(),
    ]);
    expect(res.status()).toBe(201);
    await expect(page).toHaveURL(/\/success\/?\?cs=cs_fake_/);
  });
});
