# payments — Web (Qwik City)

The hosted pages of [3m4 payments](https://payments.3m4.net), the one portal
that owns every payment for the `*.3m4.net` apps (donations, subscriptions,
receipts, claim codes, supporter badges, Stripe's Customer Portal). One Qwik
City app, SSR'd by a standalone Node-compatible HTTP server on **port 3000**
(run with Bun). Same chrome, toolchain and code style as the sibling accounts /
metrics / retro apps; brand colour is Tailwind **amber**.

- `/` (`?app=` → catalog, else app picker), `/donate`, `/subscribe`, `/success?cs=`,
  `/cancel?id=`, `/claim?code=`, `/me` (`?portal=1` opens the Customer Portal) —
  see CONTRACT.md §10. Every page honours `?return_to=` (validated in
  `src/lib/returnTo.ts`) and `?origin=` (postMessage target of the opener).
- Static: `/pay.js`, the button widget built from `packages/pay-js`.
- Login gate: pages that need a session send the browser to
  `${VITE_ACCOUNTS_URL}/login?return_to=<current url>`.

There is no token handling in the browser: accounts sets the HttpOnly
`3m4_session` cookie on `.3m4.net` and `src/lib/api.ts` just sends
`credentials: "include"` (refreshing once via accounts on `401 session_expired`).
Currency preselection follows CONTRACT.md §7 (`src/lib/currency.ts`).

Toolchain: **Bun** (do not use npm/pnpm). Stack: Qwik + Qwik City + Vite +
TypeScript + Tailwind CSS, with the official `@builder.io/qwik-city/adapters/node-server`.

## Develop

```bash
bun run widget       # once, builds ../../packages/pay-js → public/pay.js
bun install
bun run dev          # Vite dev server (SSR), http://localhost:5173
```

Point `VITE_API_URL` at a running API (`http://localhost:8086/api` through the
local Caddy) and `VITE_ACCOUNTS_URL` at accounts (`http://localhost:8085`).

## Build & serve (production)

```bash
bun install
bun run build        # check:i18n + types + client + SSR server → dist/ + server/entry.node-server.js
bun run serve        # starts the SSR server on 0.0.0.0:3000
```

`bun run check:i18n` verifies that every base-language catalog has every
English key (same placeholders, nothing extra) and that every locale in
`src/i18n/langs.ts` has a base catalog. English source: `src/i18n/catalog/en/{chrome,pay}.ts`.

## Components worth knowing

- `components/currency-select.tsx` — the `<select>` over the catalog's
  currencies; persists the choice in `localStorage["3m4.currency"]`.
- `components/copy-field.tsx` — read-only snippet + Copy button (badge embeds).
- `routes/(portal)/layout.tsx` — the centered card layout (logo, "Your
  support" link, language picker, theme toggle, footer).

## Environment (build-time, `VITE_*`)

See the repo `.env.example`: `VITE_API_URL`, `VITE_APP_URL`, `VITE_ACCOUNTS_URL`
(default `http://localhost:8085`), `VITE_GITHUB_SPONSORS_URL`, `VITE_POSTHOG_KEY`,
`VITE_POSTHOG_HOST`, `VITE_INFO_URL`, `VITE_METRICS_PROJECT_KEY`,
`VITE_METRICS_TRACKER_URL`, `VITE_RETRO_PROJECT_KEY`, `VITE_RETRO_WIDGET_URL`.
At runtime the SSR server reads `API_INTERNAL_URL` to resolve the feature
switches (`GET /api/features`) before the first paint.
