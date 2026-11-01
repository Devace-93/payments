/**
 * Typed client for the accounts API (CONTRACT.md → REST API).
 *
 * - Base URL from VITE_API_URL (fallback "/api" — works behind Caddy).
 * - Always sends cookies (`credentials: "include"`); there is no token in JS.
 * - JSON bodies get `Content-Type: application/json` (the CSRF guard the
 *   contract relies on); the avatar upload sends `X-Requested-With: 3m4`.
 * - On `401 session_expired` it calls POST /session/refresh once and retries.
 *
 * Throws `ApiRequestError` (carrying the parsed `error` body + HTTP status) so
 * callers can branch on the stable error codes.
 */
import type { ApiError, Me, Provider, SessionResponse, SessionRow, User } from "./types";

export const BASE = (import.meta.env.VITE_API_URL || "/api").replace(/\/$/, "");

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
  formData?: FormData;
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
      const res = await fetch(`${BASE}/session/refresh`, {
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
  const { method = "GET", body, formData, headers = {}, _retried = false } = opts;
  const init: RequestInit = { method, credentials: "include", headers };
  if (formData) {
    init.body = formData;
    headers["X-Requested-With"] = "3m4";
  } else if (body !== undefined) {
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

/** Absolute or root-relative URL of the OAuth start endpoint for a provider. */
export function oauthStartUrl(provider: Provider, returnTo: string, link = false): string {
  const params = new URLSearchParams({ return_to: returnTo });
  if (link) params.set("link", "1");
  return `${BASE}/auth/oauth/${provider}/start?${params}`;
}

export const api = {
  /* ─── Public ───────────────────────────────────────────────────────── */
  features: () => apiFetch<{ features: Record<string, boolean> }>("/features"),
  providers: () => apiFetch<{ providers: Provider[] }>("/auth/providers"),

  /* ─── Auth ─────────────────────────────────────────────────────────── */
  signup: (data: { email: string; password: string; handle?: string; name?: string; lang?: string }) =>
    apiFetch<{ user: User }>("/auth/signup", { method: "POST", body: data }),
  login: (email: string, password: string) =>
    apiFetch<{ user: User }>("/auth/login", { method: "POST", body: { email, password } }),
  magic: (email: string, return_to?: string, lang?: string) =>
    apiFetch<Record<string, never>>("/auth/magic", { method: "POST", body: { email, return_to, lang } }),
  magicConsume: (token: string) =>
    apiFetch<{ user: User }>("/auth/magic/consume", { method: "POST", body: { token } }),
  verifyConsume: (token: string) =>
    apiFetch<{ user: User }>("/auth/verify/consume", { method: "POST", body: { token } }),
  verifyResend: (lang?: string) =>
    apiFetch<Record<string, never>>("/auth/verify/resend", { method: "POST", body: { lang } }),

  /* ─── Session ──────────────────────────────────────────────────────── */
  session: () => apiFetch<SessionResponse>("/session"),
  refresh: () => apiFetch<{ user: User }>("/session/refresh", { method: "POST", body: {} }),
  logout: (all = false) => apiFetch<void>("/session/logout", { method: "POST", body: { all } }),
  sessions: () => apiFetch<{ items: SessionRow[] }>("/session/list"),
  revokeSession: (id: string) => apiFetch<void>(`/session/${encodeURIComponent(id)}`, { method: "DELETE" }),

  /* ─── Me ───────────────────────────────────────────────────────────── */
  me: () => apiFetch<Me>("/me"),
  updateMe: (data: { name?: string; handle?: string }) =>
    apiFetch<{ user: User }>("/me", { method: "PATCH", body: data }),
  setPassword: (new_password: string, current_password?: string) =>
    apiFetch<void>("/me/password", { method: "PUT", body: { new_password, current_password } }),
  uploadAvatar: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return apiFetch<{ user: User }>("/me/avatar", { method: "PUT", formData: fd });
  },
  removeAvatar: () => apiFetch<{ user: User }>("/me/avatar", { method: "DELETE" }),
  unlinkIdentity: (provider: Provider) =>
    apiFetch<void>(`/me/identities/${provider}`, { method: "DELETE" }),
};
