import { defineConfig, devices } from "@playwright/test";

/**
 * E2E suite for accounts. Runs against an already-running stack (docker compose):
 *   E2E_BASE_URL     base of the Caddy entrypoint (default http://localhost:8085)
 *   E2E_MAILPIT_URL  Mailpit's HTTP API (default http://localhost:8025), where the
 *                    verification and magic-link mails are read back from.
 * The API lives under <base>/api, the JWKS at <base>/.well-known/jwks.json and
 * the widget at <base>/session.js.
 *
 * The browser gets a real Chrome UA like the other 3m4 suites. Chromium's
 * Local Network Access checks are disabled so a routed "host" page on another
 * localhost port can load /session.js and call the API on the loopback stack,
 * like a static 3m4 site would against accounts.3m4.net.
 */
export const BASE_URL = process.env.E2E_BASE_URL?.replace(/\/$/, "") || "http://localhost:8085";
export const MAILPIT_URL = process.env.E2E_MAILPIT_URL?.replace(/\/$/, "") || "http://localhost:8025";

const DESKTOP_UA =
  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36";

export default defineConfig({
  globalSetup: "./global-setup.ts",
  testDir: "./tests",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  // Files share nothing (each creates its own users), but several tests within
  // a file reuse one user/session, so keep each file sequential.
  fullyParallel: false,
  workers: process.env.CI ? 2 : undefined,
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
          args: ["--disable-features=LocalNetworkAccessChecks,PrivateNetworkAccessSendPreflights,PrivateNetworkAccessRespectPreflightResults"],
        },
      },
    },
  ],
});
