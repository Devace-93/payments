/**
 * Thin PostHog wrapper. No-ops entirely when VITE_POSTHOG_KEY is unset
 * (self-host default). Safe to import anywhere; only initializes in the browser.
 */
import type { PostHog } from "posthog-js";

let client: PostHog | null = null;
let initialized = false;

const KEY = import.meta.env.VITE_POSTHOG_KEY;
const HOST = import.meta.env.VITE_POSTHOG_HOST || "https://us.i.posthog.com";

export async function initAnalytics(): Promise<void> {
  if (initialized || typeof window === "undefined" || !KEY) {
    initialized = true;
    return;
  }
  initialized = true;
  const posthog = (await import("posthog-js")).default;
  posthog.init(KEY, {
    api_host: HOST,
    capture_pageview: true,
    // No autocapture on an auth service: form fields must never leak.
    autocapture: false,
    persistence: "localStorage+cookie",
  });
  client = posthog;
}

export function capture(event: string, props?: Record<string, unknown>): void {
  if (!client) return;
  client.capture(event, props);
}

/** Associate subsequent events with the signed-in user (person id = user id). */
export function identify(userId: string): void {
  if (!client) return;
  client.identify(userId);
}

export function resetAnalytics(): void {
  if (!client) return;
  client.reset();
}
