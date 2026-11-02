# payments.3m4.net — contract

Source of truth for the payments service: what apps may rely on, what the web
calls, what the API guarantees. Keep this file in sync with the code.

## 1. Purpose and roles

One hosted portal owns every payment for the `*.3m4.net` apps: donations
("buy me a coffee"), subscriptions, receipts, claim codes, supporter badges and
Stripe's Customer Portal. Apps never talk to Stripe. They add a button and read
entitlements.

- **Identity**: accounts.3m4.net. The `3m4_session` cookie (Ed25519 JWT, claims
  `sub, sid, email, email_verified, handle, name, avatar_url, iat, exp`,
  optional `currency`) is verified locally with the vendored `dbcore/m4session.py`
  (JWKS from `ACCOUNTS_INTERNAL_URL`, issuer `ACCOUNTS_URL`, audience `3m4`).
  An explicit `Authorization: Bearer <jwt>` beats the cookie. There is **no
  local users table**: `customers.identity_id` is the JWT `sub`.
- **Donations** need no account. **Subscriptions** require one.
- **Money**: Stripe account in Mexico (settles MXN). Prices in `usd`, `mxn`,
  `eur`. `automatic_tax` is a config switch, OFF by default.

## 2. Environment

| Var | Default (local) | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://payments:payments@postgres:5432/payments` | |
| `REDIS_URL` | `redis://redis:6379/0` | limiter |
| `POSTGRES_PASSWORD` | `payments` | |
| `PAYMENTS_URL` | `http://localhost:8086` | public base URL (success/cancel URLs, mail links) |
| `ACCOUNTS_URL` | `http://localhost:8085` | JWT issuer + hosted login pages |
| `ACCOUNTS_INTERNAL_URL` | `http://accounts-api-1:5000` | where the JWKS is fetched (edge network) |
| `ALLOWED_ORIGINS` | `https://3m4.net,https://*.3m4.net,http://localhost:*,http://127.0.0.1:*` | CORS + `return_to` + `origin` |
| `SECRET_KEY` | | HMACs |
| `STRIPE_SECRET_KEY` | `` | restricted key `rk_…`. **Empty = fake Stripe** (see §11) |
| `STRIPE_WEBHOOK_SECRET` | `` | `whsec_…` |
| `STRIPE_AUTOMATIC_TAX` | `false` | |
| `STRIPE_PORTAL_CONFIGURATION` | `` | optional `bpc_…` |
| `STRIPE_INTEGRATION_IDENTIFIER` | `3m4-payments-xxxxxxxx` | 8 random letters suffix |
| `CURRENCIES` | `usd,mxn,eur` | first = fallback |
| `DEFAULT_CURRENCY` | `usd` | |
| `MIN_NET_RATIO` | `0.80` | minimum share of a donation that must reach Enrique (fees.py) |
| `ISR_RATE` | `0.01` | RESICO income tax used by fees.py |
| `FX_RATES_MXN` | `{"usd":18.5,"eur":21.5,"mxn":1}` | JSON, MXN per unit |
| `DONATION_MAX_CENTS` | `{"usd":50000,"mxn":1000000,"eur":50000}` | JSON |
| `CLAIM_CODE_TTL_DAYS` | `90` | |
| `GITHUB_SPONSORS_URL` | `` | shown as second donate button when set |
| `GITHUB_WEBHOOK_SECRET` | `` | phase 3 |
| `MAXMIND_LICENSE_KEY` | `` | optional; `/api/geo` returns `null` country without it |
| `MAIL_ENABLED`, `SMTP_URL`, `MAIL_FROM` | as accounts; `MAIL_FROM=3m4 payments <no-reply@3m4.net>` | |
| `POSTHOG_*`, `POSTHOG_FLAG_PREFIX=payments-`, `FEATURE_FLAG_OVERRIDES` | as accounts | |
| `RATE_LIMIT_DEFAULT` | `120/minute` | |
| **Vite (build-time)** `VITE_API_URL`, `VITE_APP_URL`, `VITE_ACCOUNTS_URL`, `VITE_GITHUB_SPONSORS_URL`, `VITE_POSTHOG_*`, `VITE_INFO_URL`, `VITE_METRICS_*`, `VITE_RETRO_*` | `VITE_ACCOUNTS_URL=http://localhost:8085` | `VITE_APP_URL` = `PAYMENTS_URL` |

Compose project `payments`, Caddy on **8086**, Mailpit UI on **8026**. Feature
flags (`packages/shared/feature_flags.json`): `site-building`, `donations`,
`subscriptions`, `badges`, `fee-hint`.

## 3. Catalog

`packages/shared/catalog.json` is the registry of apps and products, keyed by
Stripe `lookup_key`. `python -m dbcore.cli sync-catalog` mirrors it into the
`apps` and `products` tables and resolves `stripe_price_id` from Stripe by
lookup key (fails loudly listing missing keys; `cli create-prices` creates
them). Donation prices are global (app slug `3m4`), one per currency, with
`custom_unit_amount`.

```json
{
  "apps": [
    {"slug": "3m4", "name": "3m4", "origins": ["https://3m4.net", "https://*.3m4.net", "http://localhost:*"]},
    {"slug": "retro", "name": "Retro", "origins": ["https://retro.3m4.net", "http://localhost:*"],
     "products": [
       {"key": "pro_monthly", "kind": "subscription", "entitlement": "pro", "interval": "month",
        "lookup_key": "retro_pro_monthly", "label": "Pro", "amounts": {"usd": 500, "mxn": 9900, "eur": 500}}
     ]}
  ],
  "donation": {"lookup_keys": {"usd": "donation_usd", "mxn": "donation_mxn", "eur": "donation_eur"},
               "presets": {"usd": [300, 500, 1000], "eur": [300, 500, 1000], "mxn": [5000, 10000, 20000]}}
}
```

## 4. Error envelope

Always `{"error": {"code": "...", "message": "..."}}`. Codes used here:
`no_session` 401, `session_expired` 401, `invalid_session` 401,
`email_unverified` 403, `forbidden` 403, `not_found` 404, `validation_error` 400,
`unknown_app` 400, `unknown_price` 400, `amount_too_small` 400 (payload adds
`"min": <cents>`), `amount_too_large` 400, `unsupported_currency` 400,
`bad_origin` 400, `already_subscribed` 409, `invalid_code` 400, `expired_code`
410, `used_code` 409, `no_customer` 404, `rate_limited` 429.

Clients handle `401 session_expired` by `POST {ACCOUNTS_URL}/api/session/refresh`
(credentials) and one retry, as in `apps/web/src/lib/api.ts`.

## 5. API

Auth kinds: **public**; **session** (cookie/bearer, required); **optional
session**; **service** (`Authorization: Bearer m4pay_sk_<40 chars>`, matched by
sha256 against `apps.service_key_hash`; the app may only act on its own slug);
**stripe** (`Stripe-Signature`, `construct_event(request.get_data(), …)`).

### Public
- `GET /api/catalog?app=retro` → `200 {app:{slug,name}, currencies:["usd","mxn","eur"], default_currency, donation:{presets:{usd:[…]}, min:{usd:200,…}, max:{…}}, products:[{key, kind, entitlement, interval, label, amounts:{usd:500,…}}], github_sponsors_url, fee_hint:bool}`. `Cache-Control: public, max-age=300`. Unknown app → `400 unknown_app`.
- `GET /api/geo` → `{country:"MX"|null, currency:"mxn"}` from the client IP (X-Forwarded-For first hop). Never errors.
- `GET /api/fees?amount=500&currency=usd&kind=donation` → `{amount, currency, fee, net_mxn, retention, min_amount}` (fees.py estimate; used for the fee hint).
- `GET /api/public/supporters?app=retro&limit=50` → `{items:[{display_name, handle|null, tier:"supporter"|"pro"|"team", since:"2026-11", message|null}]}`, max-age 300. Only opted-in rows.
- `GET /badge/<handle>.svg`, `GET /badge/<handle>.json`, `GET /badge/u/<identity_id>.svg|.json` → SVG (`image/svg+xml`, `Cache-Control: public, max-age=3600`, `ETag`, CORS `*`) or shields endpoint JSON `{"schemaVersion":1,"label":"3m4","message":"supporter|pro|team|not a supporter","color":"f59e0b|9f9f9f"}`. Always 200. Served by the API at host root.
- `GET /api/checkout/<id>` (our uuid or `cs_…`) → `{id, status:"created"|"open"|"completed"|"expired", kind, app:{slug,name}, amount, currency, return_to, opener_origin, needs_claim:bool, claimed:bool, entitlements:[…]}`.
- `GET /healthz`, `GET /api/healthz`.

### Checkout (optional session; limit 10/minute per IP)
`POST /api/checkout`
```json
{"app":"retro","kind":"donation|subscription","price":"pro_monthly","amount":500,"currency":"usd",
 "return_to":"https://retro.3m4.net/x","origin":"https://retro.3m4.net","public":false,
 "display_name":"Ana","message":"thanks!","lang":"es"}
```
→ `201 {"id":"<uuid>","url":"https://checkout.stripe.com/…"}`.
Rules: `app` must exist and be active; `return_to` passes `safe_return_to` **and** matches the app's `origins`; `origin` (postMessage target) must match the app's origins; `currency` ∈ `CURRENCIES`; donation `amount` ≥ `fees.min_amount(currency)` and ≤ max; `kind=subscription` requires a session (`401 no_session`), a product of that app (`400 unknown_price`) and no active subscription for (sub, app) (`409 already_subscribed`). A `checkout_sessions` row is created first; its id is the Stripe idempotency key, `client_reference_id` and `metadata.checkout_id`. Stripe session params: `mode`, `line_items` (donation: the per-currency donation price with `custom_unit_amount`… actually the amount is fixed by passing `price_data`? **No**: use the donation price + `line_items[0].price` and let Checkout show the preset `amount` via `custom_unit_amount.preset` is not per-session, so we pass **`price_data` inline** `{currency, unit_amount: amount, product: <donation product id>}` for donations; subscriptions pass `price` + `currency`), `success_url={PAYMENTS_URL}/success?cs={CHECKOUT_SESSION_ID}`, `cancel_url={PAYMENTS_URL}/cancel?id=<uuid>`, `submit_type=donate` (donations), `customer` when the identity already has a Stripe customer else `customer_creation=always` (payment mode) / `customer_email` (when logged in), `metadata` + `subscription_data.metadata` / `payment_intent_data.metadata` = `{app, kind, checkout_id, identity_id?}`, `locale`, `allow_promotion_codes` (subscriptions), `automatic_tax` per config, `integration_identifier`. Never pass `payment_method_types`.

### Session
- `GET /api/me` → `{identity:{id,email,handle,name}, customer:{has_stripe_customer, public_supporter, display_name, preferred_currency}, payments:[{id, app, kind, amount, currency, status, created_at, public, message}], subscriptions:[{id, app, entitlement, status, current_period_end, cancel_at_period_end, label}], badge:{svg_url, json_url, stable_svg_url, markdown, html, shields_url}}`. Upserts `customers` from claims.
- `PATCH /api/me` `{public_supporter?, display_name?, preferred_currency?}` → `200 {customer}`.
- `POST /api/claim` `{code}` (limits 5/minute per identity, 20/hour per IP) → `200 {payment}`; `400 invalid_code`, `410 expired_code`, `409 used_code`. Code normalisation: uppercase, strip spaces/dashes, Crockford base32 (I→1, O→0, L→1).
- `POST /api/portal` `{return_to?}` → `200 {url}`; `404 no_customer`.
- `GET /api/entitlements?app=retro` → `{app, entitlements:["pro"], subscription:{status, current_period_end, cancel_at_period_end}|null, updated_at}`.

### Service (app backends)
- `GET /api/v1/entitlements/<identity_id>?app=retro` → same body as above. `403 forbidden` if `app` ≠ the key's app.
- `GET /api/v1/subscriptions?app=retro&updated_since=<iso>&cursor=` → `{items:[…], next_cursor}`.

### Stripe
- `POST /api/stripe/webhook` — limiter exempt. Insert `stripe_events` first (duplicate → `200 {"status":"duplicate"}`), then handle; always re-`retrieve` the object. Handled: `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.expired`, `customer.subscription.created|updated|deleted`, `invoice.paid`, `invoice.payment_failed`, `charge.refunded`, `charge.dispute.created`. Anything else → `200 {"status":"ignored"}`.

## 6. Push webhooks to apps

Queued in `outbox` (`kind="webhook"`), delivered by the worker to
`apps.webhook_url` with retries (same backoff as mail).

```
POST <webhook_url>
Content-Type: application/json
X-M4Pay-Event-Id: <uuid>
X-M4Pay-Timestamp: <unix seconds>
X-M4Pay-Signature: v1=<hex hmac_sha256(webhook_secret, f"{timestamp}.{raw_body}")>

{"id":"<uuid>","type":"subscription.updated|payment.succeeded|payment.refunded|payment.claimed",
 "created":"<iso>","app":"retro","identity_id":"<sub>|null","email":"…",
 "data":{"entitlements":["pro"],"subscription":{…}|null,"payment":{…}|null,"updated_at":"<iso>"}}
```
Every event carries the **full current entitlement set** for (identity, app), so
receivers upsert idempotently and ignore ordering. Receivers verify with
`m4pay.verify_webhook(secret, body, headers, tolerance=300)` and dedupe on `id`.

## 7. Currency resolution (web)

1. JWT claim `currency` (from `GET /api/me` → `customer.preferred_currency`), 2.
`localStorage["3m4.currency"]`, 3. country of `localStorage["3m4.lang"]`
(`es-MX`→mxn, `en-US`→usd, EU locales→eur, else usd), 4. `GET /api/geo`, 5.
`DEFAULT_CURRENCY`. The user can always change it; the choice is stored in
`3m4.currency`.

## 8. Fees and minimums (`dbcore/fees.py`)

Stripe MX: 3.6% + MXN 3.00 domestic card; +0.5% international card; +2% FX when
the charge currency ≠ MXN; 16% IVA on Stripe's fee; +0.7% Billing on
subscriptions; ISR `ISR_RATE` on the gross. `estimate(amount, currency, kind,
domestic=None)` → `{fee_mxn, tax_mxn, net_mxn, retention}` (international card
assumed unless currency is mxn). `min_amount(currency)` = smallest amount whose
retention ≥ `MIN_NET_RATIO`, rounded up to a whole unit (`usd`/`eur`) or 5 MXN,
never below Stripe's charge minimum (usd 50, eur 50, mxn 1000 cents). With
defaults: usd 200, eur 200, mxn 2500.

## 9. Claim codes

Created for guest donations only. 16 Crockford-base32 chars shown as
`XXXX-XXXX-XXXX-XXXX` (80 bits), stored as sha256 only, expire after
`CLAIM_CODE_TTL_DAYS`, single use (`UPDATE … WHERE used_at IS NULL`). Refund or
dispute voids the code. The receipt mail carries `{PAYMENTS_URL}/claim?code=…`.

## 10. Hosted pages (web) and `pay.js`

Pages: `/` (`?app=` catalog, else app picker), `/donate?app=&amount=&currency=&origin=&return_to=`,
`/subscribe?app=&price=&currency=&origin=&return_to=`, `/success?cs=`,
`/cancel?id=`, `/claim?code=`, `/me` (`?portal=1` auto-opens the portal).
Login gate: `location.assign(`${VITE_ACCOUNTS_URL}/login?return_to=${encodeURIComponent(location.href)}`)`.
Success page posts `{type:"m4pay:complete", kind, app, entitlements}` to
`window.opener` with `opener_origin` as target, then offers "Back to {app}".

`/pay.js` (built from `packages/pay-js`, served by web, CORS `*`, max-age 300):
```html
<script src="https://payments.3m4.net/pay.js" data-app="retro" data-kind="donate"
        data-amount="500" data-currency="usd" data-label="Buy me a coffee" data-mount="#support" defer></script>
<script src="https://payments.3m4.net/pay.js" data-app="retro" data-kind="subscribe"
        data-price="pro_monthly" data-return-to="https://retro.3m4.net/dashboard/billing" defer></script>
```
One button per tag (`data-mount` or inserted after the script). Opens
`window.open(url, "m4pay", "popup,width=480,height=780")`; popup blocked →
`location.assign(url)`. Accepts `message` events only from the payments origin
and `data.type === "m4pay:complete"`; dispatches `window` CustomEvent
`m4pay:paid` with `detail`. For `subscribe`, also polls `GET /api/entitlements?app=`
(credentials) on `focus`, up to 10 × 3 s. Exposes `window.m4pay = {open, entitlements, origin}`.
Theme/lang from `localStorage 3m4.theme` / `3m4.lang` (en/es strings, en fallback).

## 11. Fake Stripe (CI / no key)

When `STRIPE_SECRET_KEY` is empty, `dbcore/stripe_client.py` returns a
`FakeStripe` whose `checkout.sessions.create` yields `{id:"cs_fake_<uuid>",
url:"{PAYMENTS_URL}/success?cs=cs_fake_<uuid>"}` and whose other calls return
plausible objects. `python -m dbcore.cli seed-completed <cs_id>` runs the same
code path as `checkout.session.completed` for that session (guest donation →
claim code + mail). The web does not know the difference.

## 12. Mail

Templates (`dbcore/mail_templates.py`, en/es): `donation_receipt` (amount, app,
optional claim code + link), `subscription_started`, `subscription_cancelled`,
`payment_failed`. Enqueued via `enqueue_mail(session, *, template, to, lang,
params)`. Stripe's own receipts stay enabled in the Dashboard.

## 13. Backend notes (implementation, 2026-11-01)

Additive details the sections above leave open; everything else is as
specified.

- `GET /api/checkout/<id>` also returns `email` (the payer's e-mail once the
  payment landed, else `null`). `status` is `created` only between the row
  insert and the Stripe call; the web will normally see `open` → `completed`
  (or `expired`). With a real key, a poll after 20 s re-`retrieve`s the Stripe
  session and completes it inline if the webhook has not landed yet.
- `GET /api/fees` returns, besides `{amount, currency, fee, net_mxn,
  retention, min_amount}`, the breakdown `fee_mxn`, `tax_mxn`, `isr_mxn`,
  `gross_mxn`. `fee` = Stripe fee + IVA in MXN.
- `GET /api/me` payments carry `amount_refunded`, `claimed_at` and
  `display_name` too; subscriptions carry `id` and `app`. `badge` is `null`
  when the `badges` flag is off. `GET /api/me/customer` returns only
  `{customer}` (cheap read for the currency selector). `GET /api/features`
  returns `{features: {key: bool}}` for the pages (as in accounts).
- `POST /api/checkout` with a *subscription* and an expired cookie answers
  `401 session_expired` (so the client refreshes and retries); with no cookie
  at all `401 no_session`. A stale cookie on a *donation* is ignored (guest
  flow). A disabled flag answers `403 feature_disabled`. `return_to` must be
  absolute and on the app's origins (no root-relative paths); `origin` must
  match both `ALLOWED_ORIGINS` and the app's origins. Stripe `locale` is
  `es-419` for any Spanish except `es-ES`.
- `POST /api/stripe/webhook`: a handler failure answers `500 handler_failed`
  (Stripe retries; the retry is allowed through, only processed events are
  `duplicate`). With an empty `STRIPE_WEBHOOK_SECRET` the endpoint accepts the
  raw JSON **only** in fake-Stripe mode (503 `webhook_not_configured`
  otherwise). Subscription events older than the newest applied one (by the
  event's `created`) answer `{"status":"stale"}`.
- `customers.lang` mirrors the language of the last checkout, so
  `payment_failed` / `subscription_cancelled` mails use it.
- Service keys are `m4pay_sk_` + 40 url-safe chars; webhook secrets
  `whsec_m4pay_…` (both printed once by `cli app-key <slug> [webhook_url]`).
  Service endpoints answer `401 unauthorized` for a missing/bad key.
- `GET /api/v1/subscriptions` items: `{id, app, identity_id, email,
  entitlement, status, current_period_end, cancel_at_period_end, label,
  entitlements, updated_at}`; pages of 100, opaque `cursor`.
- Supporters list: a row needs `customers.public_supporter=true` **and**
  (a `public` paid payment or an entitled subscription); guest donations with
  `public=true` are listed under their `display_name` with `handle: null`.
  Tier for the list and the badge: `team` > `pro` (entitlement names) >
  `supporter` (any other entitled subscription or paid donation).
- Fake Stripe: `GET /api/checkout/<id>` never auto-completes; only
  `cli seed-completed <cs_id>` (or a signed webhook) does.
