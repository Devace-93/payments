# payments

**One checkout for every 3m4 app.** `payments.3m4.net` owns donations ("buy me
a coffee"), subscriptions, receipts, claim codes, supporter badges and
Stripe's Customer Portal for the `*.3m4.net` apps. Apps never talk to Stripe:
they drop in a button and read entitlements. Identity is
[accounts.3m4.net](https://github.com/Devace-93/accounts); money is one Stripe
account in Mexico (usd / mxn / eur). MIT.

> Built by Enrique Magallon Alvarez. Hosted edition at `payments.3m4.net`; the
> core is free to self-host.

---

## How it works

```
app X (retro, exp, info, mousetouch site…)       payments.3m4.net                        Stripe
┌──────────────────────────────┐  popup/redirect ┌───────────────────────────┐ Checkout  ┌────────┐
│ <script src=…/pay.js         │ ──────────────▶ │ Qwik: / /donate /subscribe│ ────────▶ │ hosted │
│   data-app=retro data-kind=… │ ◀─ postMessage ─│  /success /claim /me      │ ◀ success_url ─────┘
└──────────────────────────────┘                 │ Flask: catalog, checkout, │ webhooks  ┌────────┐
     ▲ pull GET /api/v1/entitlements/<sub>?app=  │  claim, portal, badge,    │ ◀──────── │ events │
     │ push POST <app>/api/billing/webhook (HMAC)│  stripe webhook, outbox   │           └────────┘
     └────────────────────────────────────────── │  worker (mail + app push) │
                                                 └───────────────────────────┘
```

- **Donations** need no account: the receipt mail carries a claim code that
  attaches the donation to a 3m4 account later (`/claim?code=`).
- **Subscriptions** require a session; every change is pushed to the app with
  the full entitlement set and can be pulled at any time with a service key.
- **Catalog** (`packages/shared/catalog.json`) is the registry of apps and
  products, keyed by Stripe `lookup_key`; `cli sync-catalog` mirrors it into
  the DB and `cli create-prices` creates the Stripe side.
- **Minimums** are derived from a fee model (`dbcore/fees.py`: Stripe MX fees,
  IVA, ISR, FX), not hardcoded: a donation must leave at least `MIN_NET_RATIO`
  (80 %) after fees.
- The spec is [`CONTRACT.md`](CONTRACT.md).

## Layout

```
dbcore/               shared Python core: config, models, fees, catalog, claims, badges,
                      entitlements, stripe_client (+ FakeStripe), outbox, worker, mail, cli,
                      m4session (vendored from accounts, read-only)
services/api/         Flask REST API (+ pytest suite in services/api/tests)
apps/web/             Qwik City frontend (Bun): the hosted pages
packages/pay-js/      the drop-in button widget → apps/web/public/pay.js
packages/relying-party/  clients for apps: python/m4pay.py, ts/m4pay.ts
packages/shared/      catalog.json, feature_flags.json (single source of truth)
deploy/               docker-compose, Caddyfile, production runbook, smoke + test scripts
db/                   Alembic migrations
e2e/                  Playwright end-to-end suite
```

## Quick start (Docker)

```bash
cp .env.example .env        # defaults work locally: fake Stripe, mail to Mailpit
make up                     # build + start everything; runs migrations + catalog sync
# open http://localhost:8086  (mail sink: http://localhost:8026)
```

| Command | Does |
|---|---|
| `make up` / `make down` | start / stop the full stack |
| `make logs` | tail all logs |
| `make test` | backend pytest suite against a disposable Postgres + Redis |
| `make lint` | ruff over the Python side |
| `make smoke` | curl the running stack (health, catalog, pay.js headers, badge) |
| `make e2e` | Playwright suite against the running stack |
| `make widget` | rebuild `pay.js` |
| `make create-prices` / `make sync-catalog` | create the Stripe products/prices from the catalog / mirror it into the DB |
| `make app-key SLUG=retro WEBHOOK_URL=…` | print a service key + webhook secret for an app (once) |
| `make seed-completed CS=cs_fake_…` | fake-Stripe helper: complete a checkout as if Stripe had |
| `make stripe-listen` | forward sandbox webhooks to the local stack |

Without `STRIPE_SECRET_KEY` the API uses a fake Stripe: `POST /api/checkout`
returns a local success URL and `make seed-completed` plays the completed
event, so the whole flow (receipt mail, claim code, badge) works offline.

## Plugging an app in

1. **Button**: one script tag per button, served from here (CORS-open, cached):
   ```html
   <script src="https://payments.3m4.net/pay.js" data-app="retro" data-kind="donate"
           data-amount="500" data-currency="usd" data-label="Buy me a coffee" defer></script>
   <script src="https://payments.3m4.net/pay.js" data-app="retro" data-kind="subscribe"
           data-price="pro_monthly" data-return-to="https://retro.3m4.net/dashboard/billing" defer></script>
   ```
   The page gets a `m4pay:paid` event when the popup completes.
2. **Catalog**: add the app (slug, name, origins, products) to
   `packages/shared/catalog.json`; `make create-prices && make sync-catalog`.
3. **Backend** (apps with subscriptions): `make app-key SLUG=<app> WEBHOOK_URL=…`,
   vendor [`packages/relying-party/python/m4pay.py`](packages/relying-party/python/m4pay.py),
   verify pushes with `verify_webhook`, read with `M4PayClient.entitlements(sub)`.
4. **Badges / supporters**: `GET /badge/<handle>.svg` for READMEs,
   `GET /api/public/supporters?app=<slug>` for a sponsors page.

## Deploy

[`deploy/PRODUCTION.md`](deploy/PRODUCTION.md): same Hetzner box as the other
3m4 apps, routed by the 3m4 edge Caddy; DNS, the Stripe checklist (restricted
key, prices, webhook, portal) and the Resend SMTP setup are listed there.

## License

[MIT](LICENSE) © 2026 Enrique Magallon Alvarez.
