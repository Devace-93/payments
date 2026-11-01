import { expect, type APIRequestContext, type Page } from "@playwright/test";
import { BASE_URL, MAILPIT_URL } from "./playwright.config";

export const API_URL = `${BASE_URL}/api`;
export const WIDGET_URL = `${BASE_URL}/session.js`;
export const JWKS_URL = `${BASE_URL}/.well-known/jwks.json`;

export const PASSWORD = "E2e-Passw0rd!";

/** Same UA as the browser project; API-level calls set it too for consistency. */
export const DESKTOP_UA =
  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36";

/** The CONTRACT.md User object. */
export interface User {
  id: string;
  email: string;
  email_verified: boolean;
  handle: string;
  name: string | null;
  avatar_url: string;
  created_at: string;
}

/**
 * A unique email whose local part is already a valid handle (lowercase, digits,
 * hyphens), so the handle the signup form derives from it is predictable.
 */
export function uniqueEmail(tag = "e2e"): { email: string; handle: string } {
  const handle = `${tag}-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
  return { email: `${handle}@example.com`, handle };
}

export function uniqueHandle(tag = "e2e"): string {
  return uniqueEmail(tag).handle;
}

/**
 * Sign up through the API. The cookies land in the request context (Playwright
 * shares them with the pages of the same browser context when `page.request`
 * is used). Never reuses existing data.
 */
export async function signup(
  request: APIRequestContext,
  opts: { email?: string; handle?: string; name?: string; password?: string } = {},
): Promise<{ user: User; email: string; handle: string; password: string }> {
  const fresh = uniqueEmail();
  const email = opts.email ?? fresh.email;
  const handle = opts.handle ?? (opts.email ? undefined : fresh.handle);
  const password = opts.password ?? PASSWORD;
  const res = await request.post(`${API_URL}/auth/signup`, {
    headers: { "User-Agent": DESKTOP_UA },
    data: { email, password, handle, name: opts.name },
  });
  expect(res.status(), `signup ${email}: ${await res.text()}`).toBe(201);
  const body = await res.json();
  return { user: body.user as User, email, handle: body.user.handle, password };
}

/** Log in through the API (cookies land in the request context). */
export async function login(request: APIRequestContext, email: string, password = PASSWORD): Promise<User> {
  const res = await request.post(`${API_URL}/auth/login`, {
    headers: { "User-Agent": DESKTOP_UA },
    data: { email, password },
  });
  expect(res.status(), `login ${email}: ${await res.text()}`).toBe(200);
  return (await res.json()).user as User;
}

/** GET /api/session → the user, or null on 401. */
export async function currentSession(request: APIRequestContext): Promise<User | null> {
  const res = await request.get(`${API_URL}/session`);
  if (res.status() === 401) return null;
  expect(res.status(), `session: ${await res.text()}`).toBe(200);
  return (await res.json()).user as User;
}

/** Log in through the real /login form. */
export async function loginViaUi(page: Page, email: string, password = PASSWORD, returnTo?: string): Promise<void> {
  await page.goto(returnTo ? `/login?return_to=${encodeURIComponent(returnTo)}` : "/login");
  await page.getByTestId("email").fill(email);
  await page.getByTestId("password").fill(password);
  await page.getByTestId("submit").click();
}

/** Sign up through the real /signup form; lands on /profile. */
export async function signupViaUi(page: Page, email: string, password = PASSWORD): Promise<void> {
  await page.goto("/signup");
  await page.getByTestId("email").fill(email);
  await page.getByTestId("password").fill(password);
  await page.getByTestId("password-confirm").fill(password);
  await page.getByTestId("submit").click();
  await expect(page).toHaveURL(/\/profile\/?(\?.*)?$/);
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

/** Messages addressed to `to`, newest first (Mailpit search API). */
export async function mailsTo(to: string): Promise<MailpitSummary[]> {
  const res = await fetch(`${MAILPIT_URL}/api/v1/search?query=${encodeURIComponent(`to:"${to}"`)}&limit=20`);
  if (!res.ok) throw new Error(`mailpit search failed: ${res.status}`);
  const body = (await res.json()) as { messages: MailpitSummary[] };
  return body.messages ?? [];
}

export async function readMail(id: string): Promise<MailpitMessage> {
  const res = await fetch(`${MAILPIT_URL}/api/v1/message/${id}`);
  if (!res.ok) throw new Error(`mailpit message ${id} failed: ${res.status}`);
  return (await res.json()) as MailpitMessage;
}

/**
 * Wait for a mail to `to` carrying a `/verify?token=` or `/magic?token=` link
 * and return that link (first match in the text part, then the HTML part).
 * `after` ignores mails created before that instant, so a resend is told apart
 * from the original.
 */
export async function waitForLink(
  to: string,
  kind: "verify" | "magic",
  { after, timeoutMs = 30_000 }: { after?: Date; timeoutMs?: number } = {},
): Promise<string> {
  const re = new RegExp(`${BASE_URL.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&")}/${kind}\\?[^\\s"'<>)]+`);
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    for (const summary of await mailsTo(to)) {
      if (after && new Date(summary.Created).getTime() < after.getTime() - 1000) continue;
      const mail = await readMail(summary.ID);
      const match = (mail.Text || "").match(re) ?? (mail.HTML || "").replace(/&amp;/g, "&").match(re);
      if (match) return match[0];
    }
    await new Promise((r) => setTimeout(r, 750));
  }
  throw new Error(`no ${kind} link mailed to ${to} within ${timeoutMs} ms`);
}

/** Token query parameter of a mailed link. */
export function tokenOf(link: string): string {
  const token = new URL(link).searchParams.get("token");
  if (!token) throw new Error(`no token in ${link}`);
  return token;
}

/* ─── Fixtures ─────────────────────────────────────────────────────────────── */

/** A valid 1×1 red PNG (68 bytes) for avatar uploads. */
export const TINY_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==",
  "base64",
);

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
