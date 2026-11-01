/**
 * 3m4 accounts — relying-party helper for browser apps (Qwik, Svelte, plain TS).
 *
 * Dependency-free. The session lives in the HttpOnly `3m4_session` cookie set
 * by accounts.3m4.net on `.3m4.net`, so an app never handles tokens: it just
 * sends credentials and reacts to the error codes from CONTRACT.md.
 *
 *   const session = createSessionClient("https://accounts.3m4.net");
 *   const user = await session.getSession();          // User | null
 *   location.assign(session.loginUrl());              // → hosted login, back here after
 *   const res = await session.fetchWithSession("/api/links");  // this app's own API
 */

export interface SessionUser {
  id: string;
  email: string;
  email_verified: boolean;
  handle: string;
  name: string | null;
  avatar_url: string;
  created_at?: string;
}

export interface SessionClient {
  /** The accounts origin this client talks to. */
  accountsUrl: string;
  /** Current user (cached ~30 s; `force` bypasses the cache). `null` = signed out. */
  getSession(force?: boolean): Promise<SessionUser | null>;
  /** POST /api/session/refresh once; true when a new access cookie was set. */
  refresh(): Promise<boolean>;
  /** Revoke the session (everywhere with `all`) and clear the cache. */
  logout(all?: boolean): Promise<void>;
  loginUrl(returnTo?: string): string;
  signupUrl(returnTo?: string): string;
  profileUrl(): string;
  logoutUrl(returnTo?: string): string;
  /**
   * `fetch` with credentials that, on `401 session_expired`, refreshes once and
   * retries. Any other 401 / 403 is returned as-is for the caller to handle
   * (`no_session` → send to `loginUrl()`, `email_unverified` → explain).
   */
  fetchWithSession(input: RequestInfo | URL, init?: RequestInit): Promise<Response>;
  /** Drop the cached user (e.g. after this app learns of a logout). */
  invalidate(): void;
}

export interface ApiErrorBody {
  error?: { code?: string; message?: string };
}

async function errorCode(res: Response): Promise<string> {
  try {
    return ((await res.clone().json()) as ApiErrorBody).error?.code ?? "";
  } catch {
    return "";
  }
}

export function createSessionClient(accountsUrl: string, opts: { cacheMs?: number } = {}): SessionClient {
  const origin = accountsUrl.replace(/\/$/, "");
  const api = origin + "/api";
  const cacheMs = opts.cacheMs ?? 30_000;

  let cached: { user: SessionUser | null; at: number } | null = null;
  let inFlight: Promise<SessionUser | null> | null = null;
  let refreshing: Promise<boolean> | null = null;

  const here = (): string => (typeof location !== "undefined" ? location.href : "/");
  const page = (path: string, returnTo?: string): string =>
    `${origin}${path}?return_to=${encodeURIComponent(returnTo ?? here())}`;

  const refresh = (): Promise<boolean> => {
    if (refreshing) return refreshing;
    refreshing = fetch(`${api}/session/refresh`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    })
      .then((r) => r.ok)
      .catch(() => false)
      .finally(() => {
        refreshing = null;
      });
    return refreshing;
  };

  const fetchWithSession = async (input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> => {
    const run = () => fetch(input, { credentials: "include", ...init });
    let res = await run();
    if (res.status === 401 && (await errorCode(res)) === "session_expired" && (await refresh())) {
      res = await run();
    }
    return res;
  };

  const getSession = (force = false): Promise<SessionUser | null> => {
    if (!force && cached && Date.now() - cached.at < cacheMs) return Promise.resolve(cached.user);
    if (inFlight) return inFlight;
    inFlight = (async () => {
      try {
        const res = await fetchWithSession(`${api}/session`);
        const user = res.ok ? ((await res.json()) as { user: SessionUser }).user : null;
        cached = { user, at: Date.now() };
        return user;
      } catch {
        return cached?.user ?? null;
      } finally {
        inFlight = null;
      }
    })();
    return inFlight;
  };

  return {
    accountsUrl: origin,
    getSession,
    refresh,
    async logout(all = false) {
      try {
        await fetch(`${api}/session/logout`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ all }),
        });
      } finally {
        cached = { user: null, at: Date.now() };
      }
    },
    loginUrl: (rt?: string) => page("/login", rt),
    signupUrl: (rt?: string) => page("/signup", rt),
    profileUrl: () => page("/profile"),
    logoutUrl: (rt?: string) => page("/logout", rt),
    fetchWithSession,
    invalidate() {
      cached = null;
    },
  };
}
