# payments — notes for agents

- Spec: `CONTRACT.md` (env, catalog, API shapes, error codes, push webhooks, fees, claim codes, fake Stripe). Keep it in sync with the code: a change to a route, a field or an error code lands in the contract in the same PR.
- Sibling projects and reference implementations: `/home/enrique/accounts` (this repo was bootstrapped from it: same Flask + Qwik + compose + worker + deploy shape; it also owns identity), `/home/enrique/retro` (first app to consume payments; its `blueprints/billing.py` + `Subscription` model are what `m4pay.py` replaces), `/home/enrique/metrics`. When in doubt, do what accounts does.
- Everything in this repo (code, comments, commits, docs) is written in English.
- Local stack: `make up` → http://localhost:8086 (8080 belongs to 3m4, 8081 to exp, 8082 to retro, 8083 to metrics, 8085 to accounts). Mailpit on 8026. Compose project name `payments`.
- Build mode: Claude writes the whole codebase unless Enrique says "modo aprender".
- Brand colour: Tailwind **amber** (3m4 blue, exp violet, retro emerald, metrics cyan, bubbles orange, accounts indigo).

## Rules

- **No Stripe calls outside `dbcore/stripe_client.py` + `services/api/`.** The client is built once in `dbcore.stripe_client.client()` (`StripeClient`, restricted key, pinned API version; the fake when the key is empty). Never set `stripe.api_key`; always go through `client().v1.*`; never pass `payment_method_types`.
- **Identity only from the JWT.** `customers.identity_id` is the accounts `sub`; there is no users table and no password anywhere. `dbcore/m4session.py` is vendored verbatim from accounts — do not edit it, re-vendor it.
- **Webhooks are the source of truth** for payments and subscriptions: insert `stripe_events` first (dedupe), handlers in `services/api/api/stripe_events.py` are pure functions over the Stripe object so `cli seed-completed` and the tests reuse them; upsert by Stripe id; every push to an app carries the full entitlement set.
- **Side effects go through the outbox** (`enqueue_mail`, `enqueue_webhook`) inside the same transaction as the business write; the worker delivers.
- Secrets at rest are hashes (claim codes, service keys). Never log tokens, codes or raw IPs.
- Minimums and presets come from `dbcore/fees.py`; never hardcode an amount.
- Feature flags: `donations` gates donation checkout, `subscriptions` gates subscription checkout + portal, `badges` gates badge content. The Stripe webhook and entitlement reads are never gated.
- Tests: `make test` (pytest against a throwaway Postgres; fake Stripe, fake JWKS) and `make lint` must pass. New handler → new test with a signed event.
