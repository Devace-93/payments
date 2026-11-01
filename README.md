# accounts

**One login for every 3m4 app.** `accounts.3m4.net` is the identity service
behind the 3m4 shortener, exp, retro, metrics, smart-docs, bubbles, kinegram
and the apps index: one email + password (or Google, GitHub, Discord, or a
magic link), one profile (handle, name, avatar), one session that
every app recognises. Apps keep their own workspaces, plans and data; they just
stop owning identity. MIT.

> Built by Enrique Magallon Alvarez. Hosted edition at `accounts.3m4.net`; the
> core is free to self-host.

---

## How the session works

Logging in sets an `HttpOnly` cookie `3m4_session` on `Domain=.3m4.net`
carrying a short-lived JWT (Ed25519, 15 min) plus a rotating refresh cookie
scoped to accounts itself. Every subdomain receives the session cookie, and
each app verifies it **locally** with the public keys published at
`/.well-known/jwks.json` — no call to accounts in the request path. Logging
out revokes the refresh session and clears the cookies, so you are logged out
everywhere at once. New accounts get a verification mail; until the address
is verified the JWT says `email_verified: false` and apps gate their features
on it. The spec is [`CONTRACT.md`](CONTRACT.md).

## Architecture

```
Caddy (3m4 edge, accounts.3m4.net)
 ├─ web     Qwik City (Bun)  /login /signup /magic /verify /profile + /session.js widget
 ├─ api     Flask            auth, OAuth, sessions, JWKS, profile, avatars
 └─ worker  Python           transactional outbox → SMTP (Resend) for verification / magic-link mail
      Postgres (users, identities, sessions, tokens, avatars, outbox) · Redis (rate limits)
```

```
dbcore/               shared Python core (config, models, keys, mail, outbox, worker, cli)
services/api/         Flask REST API (+ pytest suite in services/api/tests)
apps/web/             Qwik City frontend (Bun): the hosted auth pages
packages/session-js/  the drop-in widget for static sites → apps/web/public/session.js
packages/relying-party/  reference verifiers for apps: python/m4session.py, ts/
packages/shared/      reserved_handles.json, feature_flags.json (single source of truth)
deploy/               docker-compose, Caddyfile, production runbook, smoke test
db/                   Alembic migrations
e2e/                  Playwright end-to-end suite (signup, login, magic link, profile, widget)
```

## Quick start (Docker)

```bash
cp .env.example .env        # defaults work locally; mail goes to Mailpit
make up                     # build + start everything; runs migrations
# open http://localhost:8085  (mail sink: http://localhost:8025)
```

| Command | Does |
|---|---|
| `make up` / `make down` | start / stop the full stack |
| `make logs` | tail all logs |
| `make genkey` | print a fresh `SESSION_SIGNING_KEY` |
| `make test` | backend pytest suite against a disposable Postgres + Redis |
| `make smoke` | curl the running stack (health, JWKS, signup → session → logout) |
| `make e2e` | Playwright suite against the running stack |
| `make widget` | rebuild `session.js` |

## Plugging an app in

1. Verify the `3m4_session` cookie (or `Authorization: Bearer`) with the JWKS;
   accept `iss` = your `ACCOUNTS_URL` and `aud` = `3m4`. Reference code:
   [`packages/relying-party/python/m4session.py`](packages/relying-party/python/m4session.py)
   (Flask `@require_session`) and [`packages/relying-party/ts/`](packages/relying-party/ts/)
   (browser fetch wrapper with a one-shot refresh).
2. On the first `sub` you see, create your local user row from the claims and
   keep it fresh from them afterwards.
3. Send `/login` and `/signup` to `https://accounts.3m4.net/login?return_to=…`;
   log out with `POST https://accounts.3m4.net/api/session/logout`
   (credentials included).
4. Static sites only need the widget:
   ```html
   <div id="session"></div>
   <script src="https://accounts.3m4.net/session.js" data-mount="#session" defer></script>
   ```

Details, error codes and the verification gate: `CONTRACT.md → Relying apps`.

## Deploy

[`deploy/PRODUCTION.md`](deploy/PRODUCTION.md): same Hetzner box as the other
3m4 apps, routed by the 3m4 edge Caddy; DNS, Resend (SPF/DKIM/DMARC) and the
OAuth app registrations are listed there step by step.

## License

[MIT](LICENSE) © 2026 Enrique Magallon Alvarez.
