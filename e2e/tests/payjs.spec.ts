import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { BASE_URL } from "../playwright.config";
import { canSeed, createCheckout, seedCompleted, WIDGET_URL } from "../helpers";

/**
 * pay.js on a host page served from another localhost origin (routed, no real
 * server): the button renders, the click opens a popup on the payments origin
 * with the right query, and `m4pay:paid` fires on the host when the popup
 * reaches the success page of a completed checkout opened for this origin.
 */
const HOST_ORIGIN = "http://localhost:4173";

test.describe("pay.js", () => {
  const demo = readFileSync(new URL("../../packages/pay-js/demo.html", import.meta.url), "utf8").split("http://localhost:8086").join(BASE_URL);

  test.beforeEach(async ({ page }) => {
    await page.route(`${HOST_ORIGIN}/**`, (route) => route.fulfill({ status: 200, contentType: "text/html; charset=utf-8", body: demo }));
  });

  test("/pay.js is served with CORS and cache headers", async ({ request }) => {
    const res = await request.get(WIDGET_URL);
    expect(res.status()).toBe(200);
    expect(res.headers()["content-type"]).toMatch(/javascript/);
    expect(res.headers()["access-control-allow-origin"]).toBe("*");
    expect(res.headers()["cache-control"]).toMatch(/max-age=300/);
    expect(await res.text()).toContain("3m4 payments pay.js");
  });

  test("renders a button and opens the donate popup @critical", async ({ page }) => {
    await page.goto(`${HOST_ORIGIN}/demo.html`);
    const btn = page.locator('[data-m4pay="donate"]');
    await expect(btn).toBeVisible();
    await expect(btn).toContainText(/coffee|café/i);
    expect(await page.evaluate(() => (window as unknown as { m4pay?: { origin: string } }).m4pay?.origin)).toBe(BASE_URL);

    const [popup] = await Promise.all([page.waitForEvent("popup"), btn.click()]);
    await popup.waitForLoadState();
    const u = new URL(popup.url());
    expect(u.origin).toBe(BASE_URL);
    expect(u.pathname.replace(/\/$/, "")).toBe("/donate");
    expect(u.searchParams.get("app")).toBe("3m4");
    expect(u.searchParams.get("amount")).toBe("500");
    expect(u.searchParams.get("currency")).toBe("usd");
    expect(u.searchParams.get("origin")).toBe(HOST_ORIGIN);
    expect(u.searchParams.get("return_to")).toBe(`${HOST_ORIGIN}/demo.html`);
    await expect(popup.getByTestId("preset").first()).toBeVisible();
    await popup.close();
  });

  test("m4pay:paid fires when the popup reaches a completed success page", async ({ page }) => {
    test.skip(!canSeed, "E2E_SEED_CMD not set: cannot complete a fake checkout");
    // A guest donation opened "from" the host origin, so the success page posts to it.
    const { cs } = await createCheckout(page.request, {
      app: "3m4",
      kind: "donation",
      amount: 500,
      currency: "usd",
      return_to: `${HOST_ORIGIN}/demo.html`,
      origin: HOST_ORIGIN,
      lang: "en",
    });
    seedCompleted(cs);

    await page.goto(`${HOST_ORIGIN}/demo.html`);
    await page.evaluate(() => {
      (window as unknown as { __paid: unknown[] }).__paid = [];
      window.addEventListener("m4pay:paid", (e) => (window as unknown as { __paid: unknown[] }).__paid.push((e as CustomEvent).detail));
    });
    const [popup] = await Promise.all([page.waitForEvent("popup"), page.locator('[data-m4pay="donate"]').click()]);
    // Drive the popup to the success page of the completed checkout (what Stripe would do).
    await popup.goto(`${BASE_URL}/success?cs=${encodeURIComponent(cs)}`);
    await expect(popup.getByTestId("success-done")).toBeVisible({ timeout: 30_000 });
    await expect(popup.getByTestId("back-to-app")).toBeVisible();

    await expect
      .poll(async () => page.evaluate(() => (window as unknown as { __paid: { kind: string; app: string }[] }).__paid), { timeout: 10_000 })
      .toEqual([expect.objectContaining({ kind: "donation", app: "3m4", via: "message" })]);
    await expect(page.locator("#out")).toContainText('"kind": "donation"');
    // "Back to {app}" closes the popup when it has an opener.
    await popup.getByTestId("back-to-app").click();
    await expect.poll(() => popup.isClosed()).toBe(true);
  });
});
