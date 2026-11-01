# accounts — Web (Qwik City)

The hosted pages of [3m4 accounts](https://accounts.3m4.net), the identity
service shared by every 3m4 app. One Qwik City app, SSR'd by a standalone
Node-compatible HTTP server on **port 3000** (run with Bun). Same chrome,
toolchain and code style as the sibling metrics / retro / exp apps; brand
colour is Tailwind indigo.

- `/login`, `/signup`, `/magic`, `/verify`, `/profile`, `/logout` — see the
  "Hosted pages" table in the repo-root `CONTRACT.md`. Every page honours
  `?return_to=` (validated in `src/lib/returnTo.ts`).
- `/` redirects to `/profile` or `/login` depending on the session cookie.
- Static: `/session.js`, the widget built from `packages/session-js`.

There is no token handling in the browser: the API sets HttpOnly cookies and
`src/lib/api.ts` just sends `credentials: "include"` (refreshing once on
`401 session_expired`). `src/lib/session.ts` caches the current user and
re-checks it when the tab regains focus.

Toolchain: **Bun** (do not use npm/pnpm). Stack: Qwik + Qwik City + Vite +
TypeScript + Tailwind CSS, with the official `@builder.io/qwik-city/adapters/node-server`.

## Develop

```bash
bun run widget       # once, builds ../../packages/session-js → public/session.js
bun install
bun run dev          # Vite dev server (SSR), http://localhost:5173
```

Point `VITE_API_URL` at a running API (`http://localhost:8085/api` through the
local Caddy) — the API's CORS allowlist already includes `http://localhost:*`.

## Build & serve (production)

```bash
bun install
bun run build        # check:i18n + types + client + SSR server → dist/ + server/entry.node-server.js
bun run serve        # starts the SSR server on 0.0.0.0:3000
```

`bun run check:i18n` verifies that every base-language catalog has every
English key (same placeholders, nothing extra) and that every locale in
`src/i18n/langs.ts` has a base catalog.

## Components worth knowing

- `components/password-field.tsx` — the one password input (eye / eye-off
  toggle) used by login, signup, confirm and the profile password form.
- `components/provider-buttons.tsx` — Google / GitHub / Discord
  buttons, rendered only for providers `GET /api/auth/providers` returns.
- `components/unverified-banner.tsx` — resend-verification notice on `/profile`.

## Environment (build-time, `VITE_*`)

See the repo `.env.example`: `VITE_API_URL`, `VITE_APP_URL`, `VITE_POSTHOG_KEY`,
`VITE_POSTHOG_HOST`, `VITE_INFO_URL`, `VITE_METRICS_PROJECT_KEY`,
`VITE_METRICS_TRACKER_URL`, `VITE_RETRO_PROJECT_KEY`, `VITE_RETRO_WIDGET_URL`.
At runtime the SSR server reads `API_INTERNAL_URL` to resolve the feature
switches (`GET /api/features`) before the first paint.
