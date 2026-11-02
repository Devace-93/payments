import { defineConfig, devices } from "@playwright/test";

/**
 * E2E suite for payments. Runs against already-running stacks (docker compose):
 *   E2E_BASE_URL      payments Caddy entrypoint (default http://localhost:8086)
 *   E2E_ACCOUNTS_URL  accounts Caddy entrypoint (default http://localhost:8085) —
 *                     users are created there; the `3m4_session` cookie is host-only
 *                     on `localhost`, which browsers share across ports.
 *   E2E_MAILPIT_URL   payments' Mailpit HTTP API (default http://localhost:8026),
 *                     where the donation receipts (claim codes) are read back from.
 *   E2E_SEED_CMD      command that completes a fake-Stripe checkout, e.g.
 *                     `docker compose --env-file .env -f deploy/docker-compose.yml run --rm migrate python -m dbcore.cli seed-completed {cs}`
 *                     (`{cs}` is replaced; appended when absent). Tests that need
 *                     a completed payment are skipped when it is unset.
 *
 * The browser gets a real Chrome UA like the other 3m4 suites. Chromium's
 * Local Network Access checks are disabled so a routed "host" page on another
 * localhost origin can load /pay.js and open popups on the loopback stack,
 * like a static 3m4 site would against payments.3m4.net.
 */
export const BASE_URL = process.env.E2E_BASE_URL?.replace(/\/$/, "") || "http://localhost:8086";
export const ACCOUNTS_URL = process.env.E2E_ACCOUNTS_URL?.replace(/\/$/, "") || "http://localhost:8085";
export const MAILPIT_URL = process.env.E2E_MAILPIT_URL?.replace(/\/$/, "") || "http://localhost:8026";
export const SEED_CMD = process.env.E2E_SEED_CMD || "";

const DESKTOP_UA =
  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36";

export default defineConfig({
  globalSetup: "./global-setup.ts",
  testDir: "./tests",
  timeout: 90_000,
  expect: { timeout: 10_000 },
  // Files share nothing (each creates its own users / checkouts), but several
  // tests within a file reuse one user/session, so keep each file sequential.
  fullyParallel: false,
  workers: 2, // seeds shell out to docker compose; keep concurrency low
  forbidOnly: !!process.env.CI,
  retries: 1,
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  outputDir: "test-results",
  use: {
    baseURL: BASE_URL,
    userAgent: DESKTOP_UA,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        userAgent: DESKTOP_UA,
        launchOptions: {
          args: [
            "--disable-features=LocalNetworkAccessChecks,PrivateNetworkAccessSendPreflights,PrivateNetworkAccessRespectPreflightResults",
            "--disable-popup-blocking",
          ],
        },
      },
    },
  ],
});
