import { expect, test } from "@playwright/test";
import { ACCOUNTS_URL } from "../playwright.config";
import { signup } from "../helpers";

/**
 * /me: login gate, public-supporter toggle + display name (PATCH /api/me),
 * preferred currency, badge snippets.
 */
test.describe("me", () => {
  test("anonymous → accounts login", async ({ page }) => {
    await page.goto("/me");
    await page.waitForURL((u) => u.origin === ACCOUNTS_URL && u.pathname.replace(/\/$/, "") === "/login", { timeout: 20_000 });
    expect(new URL(page.url()).searchParams.get("return_to")).toMatch(/\/me$/);
  });

  test("toggle public supporter and set a display name @critical", async ({ page }) => {
    const { handle } = await signup(page.request);
    await page.goto("/me");
    await expect(page.getByTestId("me-handle")).toContainText(handle);
    await expect(page.getByTestId("public-toggle")).not.toBeChecked();
    await page.getByTestId("public-toggle").check();
    await page.getByTestId("display-name").fill("Ana E2E");
    const [res] = await Promise.all([
      page.waitForResponse((r) => r.url().includes("/api/me") && r.request().method() === "PATCH"),
      page.getByTestId("save-public").click(),
    ]);
    expect(res.status()).toBe(200);
    await expect(page.getByTestId("public-supporter").locator(".alert-ok")).toBeVisible();

    await page.reload();
    await expect(page.getByTestId("public-toggle")).toBeChecked();
    await expect(page.getByTestId("display-name")).toHaveValue("Ana E2E");
  });

  test("preferred currency is saved and preselected on /donate", async ({ page }) => {
    await signup(page.request);
    await page.goto("/me");
    await expect(page.getByTestId("me-handle")).toBeVisible();
    await page.getByTestId("preferred-currency-select").selectOption("eur");
    const [res] = await Promise.all([
      page.waitForResponse((r) => r.url().includes("/api/me") && r.request().method() === "PATCH"),
      page.getByTestId("save-currency").click(),
    ]);
    expect(res.status()).toBe(200);
    await page.goto("/donate?app=3m4");
    await expect(page.getByTestId("donating-as")).toBeVisible();
    await expect(page.getByTestId("currency")).toHaveValue("eur");
  });

  test("badge snippets are shown", async ({ page }) => {
    const { handle } = await signup(page.request);
    await page.goto("/me");
    await expect(page.getByTestId("me-handle")).toBeVisible();
    const badge = page.getByTestId("badge");
    const off = await badge.getByText(/turned off/i).count();
    test.skip(off > 0, "badges feature is off");
    await expect(page.getByTestId("badge-img")).toHaveAttribute("src", /\/badge\//);
    await expect(page.getByTestId("badge-markdown")).toHaveValue(new RegExp(`\\[.*\\]\\(.*/badge/.*${handle}.*\\)`));
    await expect(page.getByTestId("badge-html")).toHaveValue(/<img/);
    await expect(page.getByTestId("badge-shields")).toHaveValue(/\.json/);
  });
});
