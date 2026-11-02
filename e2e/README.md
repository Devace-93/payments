# payments e2e

Playwright suite against running stacks: **payments** (`make up` here →
http://localhost:8086) and **accounts** (`make up` in `/home/enrique/accounts`
→ http://localhost:8085), which issues the `3m4_session` cookie. Each spec
creates its own users (through accounts' API) and checkouts; nothing is shared
or reused between runs. Receipts are read back from payments' Mailpit JSON API
(http://localhost:8026), so the local `.env` needs `MAIL_ENABLED=true` and
`SMTP_URL=smtp://mailpit:1025`. With an empty `STRIPE_SECRET_KEY` the API uses
the fake Stripe (CONTRACT.md §11): checkouts land straight on `/success?cs=cs_fake_…`
and are completed by `python -m dbcore.cli seed-completed <cs>`.

```bash
# from the repo root, both stacks up
cd e2e && bun install && bunx playwright install chromium
E2E_SEED_CMD='docker compose --env-file ../.env -f ../deploy/docker-compose.yml run --rm migrate python -m dbcore.cli seed-completed {cs}' \
  bun run test            # or: make e2e
bun run test:critical     # only the @critical tests
bun run typecheck         # type-checks the suite without a running stack
```

| Env | Default | Meaning |
|---|---|---|
| `E2E_BASE_URL` | `http://localhost:8086` | payments Caddy entrypoint (`/api`, `/pay.js`, pages) |
| `E2E_ACCOUNTS_URL` | `http://localhost:8085` | accounts Caddy entrypoint (signup/login API + hosted login) |
| `E2E_MAILPIT_URL` | `http://localhost:8026` | payments' Mailpit HTTP API |
| `E2E_SEED_CMD` | unset | completes a fake checkout; `{cs}` is replaced (appended when absent). Tests needing a completed payment are **skipped** when unset. |

| Spec | Covers |
|---|---|
| `donate.spec.ts` | presets + currency from the catalog, currency switch updates presets and `3m4.currency`, client-side minimum, "Donate with card" → `POST /api/checkout` 201 → `/success?cs=` → (seeded) thanks + claim explanation |
| `subscribe.spec.ts` | anonymous → accounts `/login?return_to=<exact url>`; logged in → plan card, amount, "Continue to Stripe" creates the checkout |
| `claim.spec.ts` | (seeded) guest donation → receipt in Mailpit → `/claim?code=` prefilled → claimed card + badge snippet → payment on `/me`; reused and invalid codes rejected |
| `me.spec.ts` | login gate, public-supporter toggle + display name (PATCH), preferred currency preselected on `/donate`, badge snippets |
| `payjs.spec.ts` | `/pay.js` headers, the button on a routed host page (`http://localhost:4173`), popup on the payments origin with app/amount/currency/origin/return_to, (seeded) `m4pay:paid` on the host when the popup reaches a completed `/success`, "Back to app" closes the popup |

Pages are addressed by `data-testid` (`currency`, `preset`, `custom-amount`,
`amount-error`, `fee-hint`, `message`, `public`, `display-name`, `submit`,
`sponsor-github`, `claim-explainer`, `donating-as`, `subscribing-as`,
`plan-card`, `plan-amount`, `login-redirect`, `success-waiting`,
`success-pending`, `success-done` (+ `data-kind`), `create-account`, `log-in`,
`back-to-app`, `entitlements`, `cancel`, `retry`, `code`, `claimed`,
`claim-login`, `me-handle`, `subscription-row`, `manage`, `payment-row`,
`claim-another`, `public-toggle`, `save-public`, `preferred-currency-select`,
`save-currency`, `badge-img`, `badge-markdown`, `badge-html`, `badge-shields`,
`error`); keep them when touching the web app.

Why the cookie works across ports: accounts sets `3m4_session` host-only on
`localhost` (no `COOKIE_DOMAIN` locally), and browsers scope cookies by host,
not port, so a user created on :8085 is logged in on :8086 too.
