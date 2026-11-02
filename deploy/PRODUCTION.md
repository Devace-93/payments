# Production runbook

payments runs on the same Hetzner box as the 3m4 shortener (`/opt/3m4`), exp,
retro, metrics, smart-docs and accounts. The 3m4 stack's Caddy owns ports
80/443, so payments is deployed as another docker compose project without its
own Caddy, and the 3m4 Caddy routes `payments.3m4.net` to it over the shared
`edge` docker network. Identity comes from accounts (`3m4_session` cookie on
`.3m4.net`, verified locally against the JWKS fetched from `accounts-api-1`);
money goes through one Stripe account in Mexico.

## Box capacity (read before merging)

The Hetzner CX22 (4 GB, no swap) runs eight compose stacks. One
`docker compose up --build` (a Bun/Vite web build peaks near 500 MB) fits, two
at once do not (2026-10-21: two parallel deploys took every site and SSH down
for ~10 minutes).

- **Merge and deploy one app at a time.** Wait for the previous deploy workflow
  to finish (its containers show a fresh `Up … seconds`) before the next merge.
- Add a swap file once: `fallocate -l 2G /swapfile && chmod 600 /swapfile &&
  mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab`.
- Longer term: a CX32 (8 GB) removes the constraint.

## First-time setup

1. **Shared network** (once per server; already there if accounts is deployed):
   ```sh
   docker network inspect edge >/dev/null 2>&1 || docker network create edge
   ```
2. **Clone + configure**
   ```sh
   git clone git@github.com:Devace-93/payments.git /opt/payments
   cd /opt/payments && bash deploy/first-deploy.sh
   ```
   `first-deploy.sh` writes `.env` (fresh `POSTGRES_PASSWORD` + `DATABASE_URL`,
   `SECRET_KEY`, `STRIPE_INTEGRATION_IDENTIFIER`, `PAYMENTS_URL=https://payments.3m4.net`,
   `ACCOUNTS_URL=https://accounts.3m4.net`, `ACCOUNTS_INTERNAL_URL=http://accounts-api-1:5000`,
   `VITE_*`, PostHog keys copied from `/opt/3m4/.env`), leaves `STRIPE_*` and
   `SMTP_URL` empty, starts the stack and installs the cron lines (step 9). With
   an empty `STRIPE_SECRET_KEY` the stack runs with the **fake Stripe** (local
   success URLs, no real charges) until step 6 is done.
   `.env` keys you fill in by hand: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`,
   `STRIPE_PORTAL_CONFIGURATION` (optional), `SMTP_URL` + `MAIL_ENABLED=true`,
   `GITHUB_SPONSORS_URL` / `VITE_GITHUB_SPONSORS_URL`, `MAXMIND_LICENSE_KEY`
   (optional), `FX_RATES_MXN` (refresh now and then).
3. **Start / restart**
   ```sh
   cd /opt/payments/deploy
   docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   ```
   Container names are stable (`payments-api-1`, `payments-web-1`,
   `payments-worker-1`). The `migrate` service runs
   `python -m dbcore.cli upgrade && python -m dbcore.cli sync-catalog` before
   the API starts; the sync fails loudly when a catalog `lookup_key` has no
   Stripe price (run `cli create-prices` first, step 6.3).
4. **Edge routing** — in `/opt/3m4/deploy/Caddyfile.prod` add this block next
   to the accounts one, then `docker compose ... exec caddy caddy reload
   --config /etc/caddy/Caddyfile` from `/opt/3m4/deploy`:
   ```
   # payments (donations, subscriptions, badges for every 3m4 app): /opt/payments,
   # compose project `payments`. /badge/* is embedded in READMEs (GitHub camo),
   # /pay.js by the other apps and static sites, so both are cacheable and
   # CORS-open. Credentialed CORS for /api/* is handled by the API itself
   # (ALLOWED_ORIGINS), not here. /api/stripe/webhook must stay reachable
   # without auth (Stripe signs it).
   payments.3m4.net {
   	handle /api/* {
   		reverse_proxy payments-api-1:5000
   	}
   	@apiRoot path /badge/* /healthz
   	handle @apiRoot {
   		reverse_proxy payments-api-1:5000
   	}
   	@widget path /pay.js
   	handle @widget {
   		header {
   			Cache-Control "public, max-age=300"
   			Access-Control-Allow-Origin "*"
   			defer
   		}
   		reverse_proxy payments-web-1:3000
   	}
   	handle {
   		reverse_proxy payments-web-1:3000
   	}
   }
   ```
5. **DNS (Bluehost)**: A record `payments` → the server IP (`46.225.62.18`),
   same as `accounts`, `metrics`, `exp` and `retro` (see the `bluehost-subdomain`
   skill / Advanced DNS panel). Caddy issues the TLS certificate automatically
   once DNS resolves. Check: `curl -sS https://payments.3m4.net/api/healthz`.
6. **Stripe** (Dashboard, the existing MX account):
   1. **Activate the account** (RFC, CLABE, persona física / RESICO). Enable the
      payment methods you want in *Settings → Payment methods* (cards, OXXO,
      SPEI; Checkout picks them automatically — the API never sends
      `payment_method_types`). Turn **email receipts ON** (*Settings → Emails*):
      Stripe's receipt carries the legal lines, ours carries the claim code.
   2. **Restricted key** (*Developers → API keys → Create restricted key*), name
      `payments.3m4.net`. Permissions:
      | Resource | Permission |
      |---|---|
      | Checkout Sessions | Write |
      | Customers | Write |
      | Subscriptions | Write (portal cancellations / plan switches) |
      | Customer portal | Write |
      | Products, Prices | Write only while running `create-prices`; Read afterwards |
      | PaymentIntents, Charges, Invoices, Events | Read |
      | Webhook Endpoints | None |
      Paste it as `STRIPE_SECRET_KEY=rk_live_…` (sandbox: `rk_test_…`).
   3. **Products and prices**: `make create-prices` (or `docker compose … run
      --rm migrate python -m dbcore.cli create-prices`) creates everything
      `packages/shared/catalog.json` names and Stripe lacks, keyed by
      `lookup_key`: one Product per app plan with a multi-currency Price
      (`currency_options` usd/mxn/eur, `recurring.interval`) and one "Support
      3m4" Product with a pay-what-you-want Price per currency
      (`custom_unit_amount`, minimum from `fees.py`). Run it once per sandbox
      and once live, then `make sync-catalog` (or just redeploy).
   4. **Webhook endpoint** (*Developers → Webhooks → Add endpoint*):
      `https://payments.3m4.net/api/stripe/webhook`, API version
      `2026-10-28.endive`, events: `checkout.session.completed`,
      `checkout.session.async_payment_succeeded`, `checkout.session.expired`,
      `customer.subscription.created`, `customer.subscription.updated`,
      `customer.subscription.deleted`, `invoice.paid`, `invoice.payment_failed`,
      `charge.refunded`, `charge.dispute.created`. Copy the signing secret into
      `STRIPE_WEBHOOK_SECRET=whsec_…`.
   5. **Customer Portal** (*Settings → Billing → Customer portal*): allow
      cancelling (at period end), switching between the catalog's plans,
      updating the payment method, invoice history; business name "3m4",
      return URL `https://payments.3m4.net/me`. If you create a dedicated
      configuration, put its id in `STRIPE_PORTAL_CONFIGURATION=bpc_…`.
   6. **Checkout branding** (*Settings → Branding*): icon + accent colour; the
      portal pages are amber-themed.
   7. Restart `api` + `worker` (`up -d api worker`) after editing `.env`.
      Verify with the smallest live donation (`fees.min_amount`) and refund it
      from the Dashboard: the receipt mail arrives, the claim code is voided.
7. **Transactional mail (Resend)**: same domain `3m4.net` accounts already
   verified (SPF/DKIM/DMARC are in place). Create an API key (sending access)
   and set
   ```
   MAIL_ENABLED=true
   SMTP_URL=smtp://resend:re_xxxxxxxxx@smtp.resend.com:587?starttls=1
   MAIL_FROM=3m4 payments <no-reply@3m4.net>
   ```
   (587 + STARTTLS: Hetzner blocks outbound 465.) Restart the worker and make a
   test donation: the receipt lands in your inbox.
8. **App keys**: for every app that reads entitlements or receives pushes,
   `make app-key SLUG=retro WEBHOOK_URL=https://retro.3m4.net/api/billing/webhook`
   prints a service key (`m4pay_sk_…`) and a webhook secret **once**. Put them
   in that app's `.env` (`PAYMENTS_SERVICE_KEY`, `PAYMENTS_WEBHOOK_SECRET`).
   Re-running rotates both. Apps that only show a donate button need nothing.
9. **Backups + housekeeping**: `first-deploy.sh` adds the cron lines
   (`backup.sh` at 03:45; `python -m dbcore.cli prune` at 04:55 — finished
   outbox rows after 7 days, abandoned checkouts and processed Stripe events
   after 30, used/expired claim codes; `cli geoip-update` weekly, no-op
   without `MAXMIND_LICENSE_KEY`).
10. **GitHub Sponsors**: once the sponsors profile is live, set
    `GITHUB_SPONSORS_URL` and `VITE_GITHUB_SPONSORS_URL` and rebuild the web
    image; the donate page shows it as a second button.
11. **Feature flags** (PostHog, keys prefixed `payments-`): `site-building`
    (curtain), `donations`, `subscriptions` (checkout + portal; OFF by default
    until retro is migrated), `badges`, `fee-hint`. The Stripe webhook and the
    entitlement reads are never gated.

## Updates

```sh
cd /opt/payments && git pull --ff-only && cd deploy
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml up -d --build --remove-orphans
```
`.github/workflows/deploy.yml` does exactly this on every push to `main` once
`DEPLOY_ENABLED=true` and the `DEPLOY_HOST` / `DEPLOY_SSH_KEY` secrets are set.
The job is serialised; still, wait for a sibling's deploy to finish before
merging here.

## Local Stripe loop (sandbox)

```sh
stripe login                                  # once; then `stripe sandbox create payments-dev`
make up                                       # STRIPE_SECRET_KEY=rk_test_… from the sandbox in .env
make create-prices && make sync-catalog
make stripe-listen                            # prints whsec_… → STRIPE_WEBHOOK_SECRET, restart api
stripe trigger customer.subscription.deleted  # etc.
```
Test cards: `4242 4242 4242 4242` (ok), `4000 0025 0000 3155` (3DS),
`4000 0000 0000 9995` (declined), `4000 0000 0000 0341` (fails the first
invoice). Without a key the fake Stripe is used: `make seed-completed CS=cs_fake_…`
plays the completed event for a checkout started from the pages.

## Smoke

```sh
BASE_URL=https://payments.3m4.net sh deploy/smoke.sh
```

## Rotations

- **Service key / webhook secret of an app**: `make app-key SLUG=<app> [WEBHOOK_URL=…]`,
  then update the app's `.env` and restart it. Queued pushes pick up the new
  secret at send time.
- **Stripe keys**: create the new restricted key, swap `STRIPE_SECRET_KEY`,
  `up -d api worker`, revoke the old one. Webhook secret: roll it in the
  Dashboard (Stripe keeps the old one valid for the chosen window), swap
  `STRIPE_WEBHOOK_SECRET`, restart `api`.
