# Relying party — TypeScript helper

`m4pay.ts` is a dependency-free browser client for apps that take payments
through `payments.3m4.net`. Apps never talk to Stripe: they open the hosted
pages (donate / subscribe / Customer Portal) and read **entitlements**. Copy
the file into the app (`src/lib/m4pay.ts`) or import it from this folder in a
monorepo — it is small on purpose. The session is the `3m4_session` cookie
from accounts.3m4.net, so there is nothing to configure beyond the two URLs.

```ts
import { createPayClient } from "./m4pay";

export const pay = createPayClient(import.meta.env.VITE_PAYMENTS_URL || "https://payments.3m4.net", {
  app: "retro",
  accountsUrl: import.meta.env.VITE_ACCOUNTS_URL || "https://accounts.3m4.net",
});
```

| Call | Does |
|---|---|
| `pay.donateUrl({ amount?, currency?, returnTo?, lang? })` | `/donate?app=…&origin=<this origin>&return_to=<here>` |
| `pay.subscribeUrl("pro_monthly", { currency?, returnTo? })` | `/subscribe?app=…&price=…` (login gate on payments) |
| `pay.portalUrl(returnTo?)` / `pay.meUrl()` | `/me?portal=1` (Stripe Customer Portal) / `/me` |
| `pay.open("donation" \| "subscription", opts)` | popup `480×780`; resolves `PayResult` on the success page's `postMessage` (payments origin only) or, for subscriptions, when focus-triggered polling of `GET /api/entitlements?app=` (10 × 3 s) sees the entitlements change. Popup blocked → `location.assign(url)`. |
| `pay.getEntitlements()` | `{ app, entitlements, subscription, updated_at }` (credentials; one refresh on `session_expired`) |
| `pay.getMe()` | the `/api/me` body, or `null` when signed out |

`PayResult` is `{ kind, app, entitlements, via: "message" | "poll" }`. Errors
from the API are thrown as `PayApiError { status, code }`.

Never trust `PayResult` alone for access control: the app's **backend** gets
the signed push webhook (`subscription.updated`, `payment.*`) and can call
`GET /api/v1/entitlements/<identity_id>` with its service key (see
`../python/m4pay.py` and CONTRACT.md §5–6). The browser result is for UX
(flip the plan badge, close the paywall).

## Retro recipe (same for exp / metrics / 3m4 / oops)

1. Backend: vendor `dbcore/m4pay.py`; env `PAYMENTS_URL`, `PAYMENTS_INTERNAL_URL`,
   `PAYMENTS_SERVICE_KEY`, `PAYMENTS_WEBHOOK_SECRET` replace `REVENUECAT_*`.
   `blueprints/billing.py`: `verify_webhook(...)` + existing event dedupe +
   `resolve_plan_from_entitlements(data["entitlements"])`. Nightly reconcile
   with `M4PayClient.subscriptions(updated_since)`.
2. Dashboard billing page: drop `@revenuecat/purchases-js`;
   `const r = await pay.open("subscription", { price: "pro_monthly" })` → refetch
   `/auth/me`; **Manage** → `location.assign(pay.portalUrl())`.
3. Marketing `/sponsors`: list `GET {PAYMENTS_URL}/api/public/supporters?app=retro`
   and add a donate button (`pay.open("donation", { amount: 500, currency: "usd" })`
   or the `pay.js` tag).
4. Static sites (3m4-info, kinegrama, bubbles, MouseTouch site) only add a
   `pay.js` donate tag — see `packages/pay-js/README.md`.

## Typecheck

```bash
bun install && bun run typecheck
```
