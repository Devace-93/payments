import { ACCOUNTS_URL, BASE_URL } from "./playwright.config";

/** Fail fast with a readable hint when the stacks are not up. */
export default async function globalSetup(): Promise<void> {
  for (const [name, url] of [
    ["payments", `${BASE_URL}/api/healthz`],
    ["accounts", `${ACCOUNTS_URL}/api/healthz`],
  ] as const) {
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(5000) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
    } catch (e) {
      throw new Error(`${name} is not reachable at ${url} (${(e as Error).message}). Start it with \`make up\` in its repo, or set E2E_BASE_URL / E2E_ACCOUNTS_URL.`);
    }
  }
}
