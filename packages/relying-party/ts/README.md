# Relying party — TypeScript helper

`m4session.ts` is a dependency-free browser client for apps that trust the
`3m4_session` cookie issued by `accounts.3m4.net`. Copy the file into the app
(or import it from this folder in a monorepo) — it is small on purpose.

```ts
import { createSessionClient } from "./m4session";

export const session = createSessionClient(import.meta.env.VITE_ACCOUNTS_URL || "https://accounts.3m4.net");
```

| Call | Does |
|---|---|
| `session.getSession()` | `User \| null`, cached 30 s. Re-check on `visibilitychange` if you render auth state. |
| `session.fetchWithSession(url, init)` | `fetch` with credentials; on `401 session_expired` refreshes once and retries. |
| `session.loginUrl()` / `signupUrl()` / `profileUrl()` / `logoutUrl()` | hosted pages with `return_to` = current page. |
| `session.logout(all?)` | `POST /api/session/logout` and clears the cache. |

Your own API must answer `401 no_session`, `401 session_expired` and
`403 email_unverified` as CONTRACT.md says (the Python verifier in
`../python/m4session.py` does). Treat them like this:

```ts
const res = await session.fetchWithSession(`${API}/links`);
if (res.status === 401) location.assign(session.loginUrl());          // no_session (or refresh failed)
if (res.status === 403 && (await res.clone().json()).error?.code === "email_unverified") {
  location.assign(`${session.accountsUrl}/verify?return_to=${encodeURIComponent(location.href)}`);
}
```

## Migrating a template Qwik app (3m4, exp, retro, metrics)

1. **Delete** `src/lib/auth.ts` (localStorage tokens) and the token handling
   in `src/lib/api.ts`. Make `apiFetch` use `session.fetchWithSession` (or set
   `credentials: "include"` and add the one-shot refresh on `session_expired`).
   Remove `register` / `login` / `refresh` / `logout` from `api`.
2. **Replace the pages** under `src/routes/(auth)/login` and `/signup` with a
   request handler that redirects:

   ```ts
   import type { RequestHandler } from "@builder.io/qwik-city";
   export const onGet: RequestHandler = ({ redirect, url, env }) => {
     const accounts = env.get("ACCOUNTS_URL") || "https://accounts.3m4.net";
     const back = url.searchParams.get("return_to") || `${url.origin}/dashboard`;
     throw redirect(302, `${accounts}/login?return_to=${encodeURIComponent(back)}`);
   };
   ```

   (`/signup` → `${accounts}/signup?...`.) Keep the routes so old links and
   the Caddy matchers still work.
3. **Dashboard guard** (`routes/(dashboard)/layout.tsx`): replace
   `isAuthenticated()` with `await session.getSession()`; `null` →
   `location.assign(session.loginUrl())`. Keep resolving `/auth/me` from the
   app's API for app-specific data (plan, features); it now reads the cookie.
4. **Nav**: show `user.avatar_url` + `@handle` linking to
   `session.profileUrl()`, and make **Log out** call `session.logout()` then
   `location.assign("/")`. Drop the email/password strings from the catalogs.
5. **Marketing nav**: `authed` comes from `session.getSession()`; the
   Log in / Sign up links point to `session.loginUrl()` / `signupUrl()`.
6. **Env**: add `VITE_ACCOUNTS_URL` (and `ACCOUNTS_URL` for SSR handlers) to
   `.env.example`, the web Dockerfile ARGs and compose build args.
7. **Playwright**: log in through the hosted pages (`accounts` must be part of
   the local stack) or set the cookie from a test-only token the API fork
   documents.

For static sites (Astro / Svelte / Phaser pages) use `session.js` instead of
this file: it renders the widget and exposes the same operations on
`window.m4session`.
