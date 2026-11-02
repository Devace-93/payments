/**
 * 3m4 payments — relying-party helper for browser apps (Qwik, Svelte, plain TS).
 *
 * Dependency-free. Apps never talk to Stripe: they open the hosted pages of
 * payments.3m4.net (donate / subscribe / portal) and read entitlements. The
 * session is the HttpOnly `3m4_session` cookie issued by accounts.3m4.net on
 * `.3m4.net`, so requests just send credentials.
 *
 *   const pay = createPayClient("https://payments.3m4.net", { app: "retro" });
 *   const result = await pay.open("subscription", { price: "pro_monthly" });  // popup → PayResult
 *   const ent = await pay.getEntitlements();                                   // ["pro"]
 *   location.assign(pay.portalUrl());                                          // Stripe Customer Portal via /me
 *
 * `open()` opens a 480×780 popup. It resolves when the success page posts
 * `{type:"m4pay:complete"}` (accepted only from the payments origin), or — for
 * subscriptions, since COOP may null the opener — when focus-triggered polling
 * of `GET /api/entitlements?app=` sees the entitlement set change (up to
 * 10 × 3 s). When the popup is blocked it falls back to `location.assign(url)`
 * and the promise never settles (the page is leaving).
 */

export type PayKind = "donation" | "subscription";

export interface PayResult {
  kind: PayKind;
  app: string;
  entitlements: string[];
  /** "message" = postMessage from the success page; "poll" = entitlements changed. */
  via: "message" | "poll";
}

export interface Entitlements {
  app: string;
  entitlements: string[];
  subscription: {
    status: string;
    current_period_end: string | null;
    cancel_at_period_end: boolean;
  } | null;
  updated_at: string;
}

export interface PayMe {
  identity: { id: string; email: string; handle: string; name: string | null };
  customer: { has_stripe_customer: boolean; public_supporter: boolean; display_name: string | null; preferred_currency: string | null };
  payments: unknown[];
  subscriptions: unknown[];
  badge: { svg_url: string; json_url: string; stable_svg_url: string; markdown: string; html: string; shields_url: string };
}

export interface DonateOptions {
  /** Minor units (500 = $5.00). */
  amount?: number;
  currency?: string;
  /** Where "Back to {app}" goes; defaults to the current page. */
  returnTo?: string;
  lang?: string;
}

export interface SubscribeOptions {
  price: string;
  currency?: string;
  returnTo?: string;
}

export interface OpenOptions extends DonateOptions {
  price?: string;
  /** Popup feature string; default "popup,width=480,height=780". */
  features?: string;
  /** Overall timeout for the promise (ms). Default 15 min. */
  timeoutMs?: number;
}

export interface PayClient {
  paymentsUrl: string;
  accountsUrl: string;
  app: string;
  donateUrl(opts?: DonateOptions): string;
  subscribeUrl(priceKey: string, opts?: Omit<SubscribeOptions, "price">): string;
  /** `/me?portal=1` — opens Stripe's Customer Portal after the login gate. */
  portalUrl(returnTo?: string): string;
  meUrl(): string;
  open(kind: PayKind, opts?: OpenOptions): Promise<PayResult>;
  getEntitlements(): Promise<Entitlements>;
  /** `null` when signed out. */
  getMe(): Promise<PayMe | null>;
}

export interface ApiErrorBody {
  error?: { code?: string; message?: string; [k: string]: unknown };
}

export class PayApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message?: string) {
    super(message || code);
    this.name = "PayApiError";
    this.status = status;
    this.code = code;
  }
}

const POLL_TRIES = 10;
const POLL_MS = 3000;

export function createPayClient(paymentsUrl: string, opts: { app: string; accountsUrl?: string }): PayClient {
  const origin = new URL(paymentsUrl, typeof location !== "undefined" ? location.href : "http://localhost").origin;
  const api = origin + "/api";
  const accountsUrl = (opts.accountsUrl || "https://accounts.3m4.net").replace(/\/$/, "");
  const app = opts.app;

  const here = (): string => (typeof location !== "undefined" ? location.href : "/");
  const myOrigin = (): string => (typeof location !== "undefined" ? location.origin : "");

  const build = (path: string, params: Record<string, string | number | undefined>): string => {
    const sp = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") sp.set(k, String(v));
    return `${origin}${path}?${sp}`;
  };

  const donateUrl = (o: DonateOptions = {}): string =>
    build("/donate", { app, amount: o.amount, currency: o.currency, return_to: o.returnTo ?? here(), origin: myOrigin(), lang: o.lang });
  const subscribeUrl = (price: string, o: Omit<SubscribeOptions, "price"> = {}): string =>
    build("/subscribe", { app, price, currency: o.currency, return_to: o.returnTo ?? here(), origin: myOrigin() });
  const portalUrl = (returnTo?: string): string => build("/me", { app, portal: 1, return_to: returnTo ?? here() });
  const meUrl = (): string => build("/me", { app });

  let refreshing: Promise<boolean> | null = null;
  const refresh = (): Promise<boolean> => {
    if (refreshing) return refreshing;
    refreshing = fetch(`${accountsUrl}/api/session/refresh`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    })
      .then((r) => r.ok)
      .catch(() => false)
      .finally(() => (refreshing = null));
    return refreshing;
  };

  const errorCode = async (res: Response): Promise<string> => {
    try {
      return ((await res.clone().json()) as ApiErrorBody).error?.code ?? "";
    } catch {
      return "";
    }
  };

  const call = async <T>(path: string, retried = false): Promise<T> => {
    const res = await fetch(api + path, { credentials: "include" });
    if (res.status === 401 && !retried && (await errorCode(res)) === "session_expired" && (await refresh())) {
      return call<T>(path, true);
    }
    if (!res.ok) {
      let body: ApiErrorBody = {};
      try {
        body = (await res.json()) as ApiErrorBody;
      } catch {
        /* no body */
      }
      throw new PayApiError(res.status, body.error?.code || "error", body.error?.message);
    }
    return (await res.json()) as T;
  };

  const getEntitlements = (): Promise<Entitlements> => call<Entitlements>(`/entitlements?app=${encodeURIComponent(app)}`);
  const getMe = async (): Promise<PayMe | null> => {
    try {
      return await call<PayMe>("/me");
    } catch (e) {
      if (e instanceof PayApiError && e.status === 401) return null;
      throw e;
    }
  };

  const open = (kind: PayKind, o: OpenOptions = {}): Promise<PayResult> => {
    const url = kind === "subscription" ? subscribeUrl(o.price || "", o) : donateUrl(o);
    return new Promise<PayResult>((resolve, reject) => {
      const popup = window.open(url, "m4pay", o.features || "popup,width=480,height=780");
      if (!popup) {
        // Blocked: full-page navigation; the app gets the user back via return_to.
        location.assign(url);
        return;
      }
      let settled = false;
      let before: string | null = null;
      let polls = 0;
      let pollTimer: ReturnType<typeof setTimeout> | null = null;

      const finish = (r: PayResult | null, err?: Error) => {
        if (settled) return;
        settled = true;
        window.removeEventListener("message", onMessage);
        window.removeEventListener("focus", onFocus);
        if (pollTimer) clearTimeout(pollTimer);
        clearTimeout(timeout);
        if (r) resolve(r);
        else reject(err || new Error("m4pay: cancelled"));
      };

      const onMessage = (e: MessageEvent) => {
        if (e.origin !== origin) return;
        const d = e.data as { type?: string; kind?: PayKind; app?: string; entitlements?: string[] } | null;
        if (!d || d.type !== "m4pay:complete") return;
        finish({ kind: d.kind || kind, app: d.app || app, entitlements: d.entitlements || [], via: "message" });
      };

      // For subscriptions, COOP may null `window.opener` after the Stripe hop,
      // so when focus comes back we poll the entitlements for a change.
      const poll = async () => {
        if (settled || kind !== "subscription") return;
        polls++;
        try {
          const ent = await getEntitlements();
          const now = JSON.stringify(ent.entitlements.slice().sort());
          if (before !== null && now !== before && ent.entitlements.length > 0) {
            finish({ kind, app, entitlements: ent.entitlements, via: "poll" });
            return;
          }
        } catch {
          /* keep polling */
        }
        if (polls < POLL_TRIES) pollTimer = setTimeout(poll, POLL_MS);
      };
      const onFocus = () => {
        if (settled || kind !== "subscription" || pollTimer) return;
        polls = 0;
        poll();
      };

      if (kind === "subscription") {
        getEntitlements()
          .then((ent) => (before = JSON.stringify(ent.entitlements.slice().sort())))
          .catch(() => (before = "[]"));
      }

      window.addEventListener("message", onMessage);
      window.addEventListener("focus", onFocus);
      const timeout = setTimeout(() => finish(null, new Error("m4pay: timeout")), o.timeoutMs ?? 15 * 60 * 1000);
    });
  };

  return { paymentsUrl: origin, accountsUrl, app, donateUrl, subscribeUrl, portalUrl, meUrl, open, getEntitlements, getMe };
}
