/**
 * Typed client for the payments API (CONTRACT.md §5).
 *
 * - Base URL from VITE_API_URL (fallback "/api" — works behind Caddy).
 * - Always sends cookies (`credentials: "include"`); there is no token in JS.
 *   The `3m4_session` cookie is issued by accounts.3m4.net on `.3m4.net`.
 * - JSON bodies get `Content-Type: application/json`.
 * - On `401 session_expired` it calls `POST {VITE_ACCOUNTS_URL}/api/session/refresh`
 *   once (credentials) and retries, as §4 says.
 *
 * Throws `ApiRequestError` (carrying the parsed `error` body + HTTP status) so
 * callers can branch on the stable error codes.
 */
import type {
  ApiError,
  Catalog,
  Checkout,
  CheckoutBody,
  CheckoutCreated,
  Customer,
  Entitlements,
  Fees,
  Geo,
  Me,
  Payment,
  Supporter,
} from "./types";

export const BASE = (import.meta.env.VITE_API_URL || "/api").replace(/\/$/, "");
export const ACCOUNTS_URL = (import.meta.env.VITE_ACCOUNTS_URL || "http://localhost:8085").replace(/\/$/, "");

export class ApiRequestError extends Error {
  status: number;
  error: ApiError;
  constructor(status: number, error: ApiError) {
    super(error.message || error.code);
    this.name = "ApiRequestError";
    this.status = status;
    this.error = error;
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  /** Internal: prevents infinite refresh loops. */
  _retried?: boolean;
}

async function parseError(res: Response): Promise<ApiError> {
  try {
    const data = await res.json();
    if (data?.error) return data.error as ApiError;
    return { code: "error", message: data?.message || res.statusText };
  } catch {
    return { code: "error", message: res.statusText || "Request failed" };
  }
}

let refreshInFlight: Promise<boolean> | null = null;

/** One refresh at a time; concurrent 401s share the same attempt. */
export async function tryRefresh(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    try {
      const res = await fetch(`${ACCOUNTS_URL}/api/session/refresh`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      return res.ok;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

export async function apiFetch<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, headers = {}, _retried = false } = opts;
  const init: RequestInit = { method, credentials: "include", headers };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }

  const res = await fetch(`${BASE}${path}`, init);

  if (res.status === 401 && !_retried) {
    const err = await parseError(res.clone());
    if (err.code === "session_expired" && (await tryRefresh())) {
      return apiFetch<T>(path, { ...opts, _retried: true });
    }
    throw new ApiRequestError(res.status, err);
  }
  if (!res.ok) throw new ApiRequestError(res.status, await parseError(res));
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Hosted login on accounts, coming back to the current page (§10 login gate). */
export function loginUrl(returnTo?: string): string {
  const back = returnTo ?? (typeof location !== "undefined" ? location.href : "/");
  return `${ACCOUNTS_URL}/login?return_to=${encodeURIComponent(back)}`;
}

export function signupUrl(returnTo?: string): string {
  const back = returnTo ?? (typeof location !== "undefined" ? location.href : "/");
  return `${ACCOUNTS_URL}/signup?return_to=${encodeURIComponent(back)}`;
}

const q = (params: Record<string, string | number | undefined>): string => {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") sp.set(k, String(v));
  const s = sp.toString();
  return s ? `?${s}` : "";
};

export const api = {
  /* ─── Public ───────────────────────────────────────────────────────── */
  getCatalog: (app: string) => apiFetch<Catalog>(`/catalog${q({ app })}`),
  getGeo: () => apiFetch<Geo>("/geo"),
  getFees: (amount: number, currency: string, kind: "donation" | "subscription" = "donation") =>
    apiFetch<Fees>(`/fees${q({ amount, currency, kind })}`),
  getSupporters: (app: string, limit = 50) => apiFetch<{ items: Supporter[] }>(`/public/supporters${q({ app, limit })}`),
  getCheckout: (id: string) => apiFetch<Checkout>(`/checkout/${encodeURIComponent(id)}`),

  /* ─── Checkout (optional session) ──────────────────────────────────── */
  createCheckout: (body: CheckoutBody) => apiFetch<CheckoutCreated>("/checkout", { method: "POST", body }),

  /* ─── Session ──────────────────────────────────────────────────────── */
  /** `null` when there is no session (401 no_session / invalid / expired-and-unrefreshable). */
  getMe: async (): Promise<Me | null> => {
    try {
      return await apiFetch<Me>("/me");
    } catch (e) {
      if (e instanceof ApiRequestError && e.status === 401) return null;
      throw e;
    }
  },
  patchMe: (body: { public_supporter?: boolean; display_name?: string | null; preferred_currency?: string | null }) =>
    apiFetch<{ customer: Customer }>("/me", { method: "PATCH", body }),
  claim: (code: string) => apiFetch<{ payment: Payment }>("/claim", { method: "POST", body: { code } }),
  createPortal: (return_to?: string) =>
    apiFetch<{ url: string }>("/portal", { method: "POST", body: return_to ? { return_to } : {} }),
  getEntitlements: (app: string) => apiFetch<Entitlements>(`/entitlements${q({ app })}`),
};
