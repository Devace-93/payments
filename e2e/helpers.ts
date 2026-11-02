import { expect, type APIRequestContext, type Page } from "@playwright/test";
import { execSync } from "node:child_process";
import { ACCOUNTS_URL, BASE_URL, MAILPIT_URL, SEED_CMD } from "./playwright.config";

export const API_URL = `${BASE_URL}/api`;
export const ACCOUNTS_API_URL = `${ACCOUNTS_URL}/api`;
export const WIDGET_URL = `${BASE_URL}/pay.js`;

export const PASSWORD = "E2e-Passw0rd!";

/** Same UA as the browser project; API-level calls set it too for consistency. */
export const DESKTOP_UA =
  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36";

/** The accounts CONTRACT.md User object. */
export interface User {
  id: string;
  email: string;
  email_verified: boolean;
  handle: string;
  name: string | null;
  avatar_url: string;
  created_at: string;
}

/** CONTRACT.md §3 catalog (the parts the tests read). */
export interface Catalog {
  app: { slug: string; name: string; icon?: string | null };
  currencies: string[];
  default_currency: string;
  donation: { presets: Record<string, number[]>; min: Record<string, number>; max: Record<string, number> };
  products: { key: string; label: string; interval: string; amounts: Record<string, number> }[];
  github_sponsors_url: string | null;
  fee_hint: boolean;
}

export interface Checkout {
  id: string;
  status: "created" | "open" | "completed" | "expired";
  kind: "donation" | "subscription";
  app: { slug: string; name: string; icon?: string | null };
  amount: number;
  currency: string;
  needs_claim: boolean;
  claimed: boolean;
  entitlements: string[];
}

/* ─── accounts (identity) ──────────────────────────────────────────────────── */

/**
 * A unique email whose local part is already a valid handle (lowercase, digits,
 * hyphens), so the handle the signup derives from it is predictable.
 */
export function uniqueEmail(tag = "pay-e2e"): { email: string; handle: string } {
  const handle = `${tag}-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
  return { email: `${handle}@example.com`, handle };
}

/**
 * Sign up on accounts through its API. The `3m4_session` cookie lands in the
 * request context (host-only on `localhost`, so the browser also sends it to the
 * payments origin on another port when `page.request` is used).
 */
export async function signup(
  request: APIRequestContext,
  opts: { email?: string; handle?: string; name?: string; password?: string } = {},
): Promise<{ user: User; email: string; handle: string; password: string }> {
  const fresh = uniqueEmail();
  const email = opts.email ?? fresh.email;
  const handle = opts.handle ?? (opts.email ? undefined : fresh.handle);
  const password = opts.password ?? PASSWORD;
  const res = await request.post(`${ACCOUNTS_API_URL}/auth/signup`, {
    headers: { "User-Agent": DESKTOP_UA },
    data: { email, password, handle, name: opts.name },
  });
  expect(res.status(), `signup ${email}: ${await res.text()}`).toBe(201);
  const body = await res.json();
  return { user: body.user as User, email, handle: body.user.handle, password };
}

/** Log in on accounts through its API (cookies land in the request context). */
export async function login(request: APIRequestContext, email: string, password = PASSWORD): Promise<User> {
  const res = await request.post(`${ACCOUNTS_API_URL}/auth/login`, {
    headers: { "User-Agent": DESKTOP_UA },
    data: { email, password },
  });
  expect(res.status(), `login ${email}: ${await res.text()}`).toBe(200);
  return (await res.json()).user as User;
}

/** Log in through accounts' real /login form (lands on `returnTo`). */
export async function loginViaUi(page: Page, email: string, password = PASSWORD, returnTo?: string): Promise<void> {
  await page.goto(`${ACCOUNTS_URL}/login${returnTo ? `?return_to=${encodeURIComponent(returnTo)}` : ""}`);
  await page.getByTestId("email").fill(email);
  await page.getByTestId("password").fill(password);
  await page.getByTestId("submit").click();
}

/* ─── payments API ─────────────────────────────────────────────────────────── */

export async function catalog(request: APIRequestContext, app = "3m4"): Promise<Catalog> {
  const res = await request.get(`${API_URL}/catalog?app=${app}`);
  expect(res.status(), `catalog ${app}: ${await res.text()}`).toBe(200);
  return (await res.json()) as Catalog;
}

/** POST /api/checkout → `{ id, url }` (fake Stripe: url is our own /success?cs=cs_fake_…). */
export async function createCheckout(
  request: APIRequestContext,
  body: Record<string, unknown>,
): Promise<{ id: string; url: string; cs: string }> {
  const res = await request.post(`${API_URL}/checkout`, { headers: { "User-Agent": DESKTOP_UA }, data: body });
  expect(res.status(), `checkout: ${await res.text()}`).toBe(201);
  const data = (await res.json()) as { id: string; url: string };
  return { ...data, cs: csOf(data.url) };
}

export async function getCheckout(request: APIRequestContext, id: string): Promise<Checkout> {
  const res = await request.get(`${API_URL}/checkout/${encodeURIComponent(id)}`);
  expect(res.status(), `checkout ${id}: ${await res.text()}`).toBe(200);
  return (await res.json()) as Checkout;
}

/** The `cs` query parameter of a success URL (`/success?cs=cs_fake_…`). */
export function csOf(url: string): string {
  const cs = new URL(url, BASE_URL).searchParams.get("cs");
  if (!cs) throw new Error(`no cs in ${url}`);
  return cs;
}

/* ─── fake Stripe completion ───────────────────────────────────────────────── */

export const canSeed = !!SEED_CMD;

/**
 * Complete a fake-Stripe checkout the way `checkout.session.completed` would
 * (CONTRACT.md §11): runs `E2E_SEED_CMD` with `{cs}` replaced (or appended).
 * Callers `test.skip(!canSeed, …)` first.
 */
export function seedCompleted(cs: string): void {
  if (!SEED_CMD) throw new Error("E2E_SEED_CMD is not set");
  const cmd = SEED_CMD.includes("{cs}") ? SEED_CMD.split("{cs}").join(cs) : `${SEED_CMD} ${cs}`;
  execSync(cmd, { stdio: "inherit", timeout: 300_000 });
}

/* ─── Mailpit ──────────────────────────────────────────────────────────────── */

interface MailpitSummary {
  ID: string;
  Subject: string;
  To: { Address: string }[];
  Created: string;
}

interface MailpitMessage extends MailpitSummary {
  Text: string;
  HTML: string;
}

/** Newest messages (optionally only those addressed to `to`). */
export async function mails(to?: string): Promise<MailpitSummary[]> {
  const url = to
    ? `${MAILPIT_URL}/api/v1/search?query=${encodeURIComponent(`to:"${to}"`)}&limit=20`
    : `${MAILPIT_URL}/api/v1/messages?limit=20`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`mailpit ${url} failed: ${res.status}`);
  const body = (await res.json()) as { messages: MailpitSummary[] };
  return body.messages ?? [];
}

export async function readMail(id: string): Promise<MailpitMessage> {
  const res = await fetch(`${MAILPIT_URL}/api/v1/message/${id}`);
  if (!res.ok) throw new Error(`mailpit message ${id} failed: ${res.status}`);
  return (await res.json()) as MailpitMessage;
}

/**
 * Wait for a receipt mail carrying a `/claim?code=` link and return that link
 * (text part first, then HTML). `after` ignores mails created before that
 * instant; `to` narrows to one recipient when the guest email is known.
 */
export async function waitForClaimLink({
  to,
  after,
  timeoutMs = 30_000,
}: { to?: string; after?: Date; timeoutMs?: number } = {}): Promise<string> {
  const re = new RegExp(`${BASE_URL.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&")}/claim\\?[^\\s"'<>)]+`);
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    for (const summary of await mails(to)) {
      if (after && new Date(summary.Created).getTime() < after.getTime() - 1000) continue;
      const mail = await readMail(summary.ID);
      const match = (mail.Text || "").match(re) ?? (mail.HTML || "").replace(/&amp;/g, "&").match(re);
      if (match) return match[0];
    }
    await new Promise((r) => setTimeout(r, 750));
  }
  throw new Error(`no claim link mailed${to ? ` to ${to}` : ""} within ${timeoutMs} ms`);
}

/** `code` query parameter of a mailed claim link. */
export function codeOf(link: string): string {
  const code = new URL(link).searchParams.get("code");
  if (!code) throw new Error(`no code in ${link}`);
  return code;
}

/* ─── misc ─────────────────────────────────────────────────────────────────── */

/** Poll an async condition until it holds. */
export async function pollUntil<T>(
  fn: () => Promise<T>,
  predicate: (v: T) => boolean,
  { timeoutMs = 15_000, intervalMs = 500 } = {},
): Promise<T> {
  const deadline = Date.now() + timeoutMs;
  let last: T = await fn();
  while (!predicate(last) && Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, intervalMs));
    last = await fn();
  }
  return last;
}
