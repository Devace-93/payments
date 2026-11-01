# Production runbook

accounts runs on the same Hetzner box as the 3m4 shortener (`/opt/3m4`), exp
(`/opt/exp`), retro (`/opt/retro`), metrics (`/opt/metrics`) and smart-docs
(`/opt/smart-docs`). The 3m4 stack's Caddy owns ports 80/443, so accounts is
deployed as another docker compose project without its own Caddy, and the 3m4
Caddy routes `accounts.3m4.net` to it over the shared `edge` docker network.

Because every 3m4 app is a subdomain of `3m4.net`, the `3m4_session` cookie is
set with `Domain=.3m4.net` and reaches all of them: that is the whole SSO
mechanism. Nothing else needs to run on the other hosts (GitHub Pages sites
included) besides verifying the JWT.

## Box capacity (read before merging several PRs)

The Hetzner CX22 (4 GB, no swap) runs seven compose stacks. At idle it sits at
about 75 % memory; one `docker compose up --build` (a Bun/Vite web build peaks
near 500 MB) fits, two at once do not. On 2026-10-21 exp and retro were merged
11 seconds apart, both deploys built in parallel, load went past 200 and every
site plus SSH was unreachable for ~10 minutes.

Rules:
- **Merge and deploy one app at a time.** Wait for the previous deploy workflow
  to finish (its containers show a fresh `Up … seconds`) before the next merge.
- Add a swap file once: `fallocate -l 2G /swapfile && chmod 600 /swapfile &&
  mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab`.
  It turns a thrash into a slow build.
- Longer term: a CX32 (8 GB) removes the constraint; see the sizing table in
  smart-docs' runbook (its Ollama container is the largest single tenant).

## First-time setup

1. **Shared network** (once per server; already there if exp is deployed):
   ```sh
   docker network inspect edge >/dev/null 2>&1 || docker network create edge
   ```
2. **Clone + configure**
   ```sh
   git clone git@github.com:Devace-93/accounts.git /opt/accounts
   cd /opt/accounts && cp .env.example .env && $EDITOR .env
   ```
   Prod `.env` checklist: `ACCOUNTS_URL=https://accounts.3m4.net`,
   `COOKIE_DOMAIN=.3m4.net`, `COOKIE_SECURE=true`, `VITE_API_URL=/api`,
   `VITE_APP_URL=https://accounts.3m4.net`, a fresh `SESSION_SIGNING_KEY`
   (`make genkey`, or the inline python in `first-deploy.sh`), fresh
   `SECRET_KEY` and `IP_HASH_SECRET`, PostHog keys (`POSTHOG_API_KEY`,
   `POSTHOG_PERSONAL_API_KEY`, `VITE_POSTHOG_KEY`; flags are prefixed
   `accounts-` in the shared PostHog project), the Resend SMTP URL (step 6) and
   the OAuth pairs (step 7), a fresh Postgres password: set `POSTGRES_PASSWORD`
   (read by the postgres service through `--env-file ../.env`) and use the same
   value in `DATABASE_URL`. `deploy/first-deploy.sh` does the generated parts
   (steps 1-4 and 9) in one go and leaves SMTP + OAuth for you to fill in.
3. **Start**
   ```sh
   cd /opt/accounts/deploy
   docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   ```
   Container names are stable (`accounts-api-1`, `accounts-web-1`,
   `accounts-worker-1`): compose project `accounts`, one replica each. The edge
   Caddy routes by name. Mailpit and the local Caddy are disabled by the prod
   override.
4. **Edge routing** — in `/opt/3m4/deploy/Caddyfile.prod` add this block next
   to the other sibling stacks (the `caddy` service is already attached to the
   external `edge` network), then `docker compose ... exec caddy caddy reload
   --config /etc/caddy/Caddyfile` from `/opt/3m4/deploy`:
   ```
   # accounts (identity / SSO for every 3m4 app): /opt/accounts, compose
   # project `accounts`. The JWKS and the avatars are fetched by every relying
   # app; /session.js is embedded by the static sites, so it is served
   # cacheable and CORS-open. Credentialed CORS for /api/* is handled by the
   # API itself (ALLOWED_ORIGINS), not here.
   accounts.3m4.net {
   	handle /api/* {
   		reverse_proxy accounts-api-1:5000
   	}
   	@apiRoot path /.well-known/* /avatars/* /healthz
   	handle @apiRoot {
   		reverse_proxy accounts-api-1:5000
   	}
   	@widget path /session.js
   	handle @widget {
   		header {
   			Cache-Control "public, max-age=300"
   			Access-Control-Allow-Origin "*"
   			# defer: replace the upstream Cache-Control instead of adding a second one
   			defer
   		}
   		reverse_proxy accounts-web-1:3000
   	}
   	handle {
   		reverse_proxy accounts-web-1:3000
   	}
   }
   ```
5. **DNS (Bluehost)**: A record `accounts` → the server IP (`46.225.62.18`),
   same as `metrics`, `exp` and `retro` (see the `bluehost-subdomain` skill /
   Advanced DNS panel). Caddy issues the TLS certificate automatically once
   DNS resolves. Check: `curl -sS https://accounts.3m4.net/api/healthz`.
6. **Transactional mail (Resend)**:
   1. Create a Resend account, add the domain `3m4.net` (region closest to the
      box: EU), and add the DNS records Resend shows at Bluehost. They are
      always of this shape (copy the exact values from the Resend dashboard):
      | Type | Host | Value | Purpose |
      |---|---|---|---|
      | TXT | `send` (or `resend._domainkey`-style name Resend shows) | `v=spf1 include:amazonses.com ~all` | SPF for the bounce subdomain |
      | MX | `send` | `feedback-smtp.<region>.amazonses.com`, priority 10 | bounces / feedback |
      | TXT | `resend._domainkey` | `p=MIGf…` (DKIM public key) | DKIM |
      | TXT | `_dmarc` | `v=DMARC1; p=none; rua=mailto:dmarc@3m4.net` | DMARC (start with `p=none`, tighten later) |
      Wait for Resend to report the domain **Verified**.
   2. Create an API key (sending access, domain `3m4.net`) and put it in `.env`:
      ```
      MAIL_ENABLED=true
      SMTP_URL=smtp://resend:re_xxxxxxxxx@smtp.resend.com:587?starttls=1
      MAIL_FROM=3m4 accounts <no-reply@3m4.net>
      ```
      (`resend` is the literal SMTP username; the API key is the password.
      Use 587 + STARTTLS: Hetzner blocks outbound port 465 on this server (the
      worker logs `timed out` on every attempt). `smtps://…:465` works elsewhere;
      `smtp://resend:re_xxx@smtp.resend.com:587?starttls=1`
      also works.)
   3. Restart the worker (`docker compose ... up -d worker`) and send yourself
      a magic link from `/login` to confirm delivery. Resend's free tier
      (3 000 mails/month, 100/day) is plenty for verification + magic links.
7. **OAuth providers** — one app registration per provider. Redirect /
   callback URL for each (production, plus the local one for development):
   - `https://accounts.3m4.net/api/auth/oauth/<provider>/callback`
   - `http://localhost:8085/api/auth/oauth/<provider>/callback`

   A provider is enabled as soon as both of its env vars are set (the
   `/login` and `/signup` pages read `GET /api/auth/providers`).

   | Provider | Where | Settings | `.env` |
   |---|---|---|---|
   | Google | [Google Cloud console → APIs & Services → Credentials](https://console.cloud.google.com/apis/credentials) → *Create credentials → OAuth client ID*, type **Web application**. First configure the *OAuth consent screen* (External, app name "3m4 accounts", support email, authorised domain `3m4.net`, scopes `openid`, `email`, `profile`). Add both callback URLs as *Authorised redirect URIs*. Publish the consent screen (otherwise only test users can log in). | scopes `openid email profile` | `OAUTH_GOOGLE_CLIENT_ID`, `OAUTH_GOOGLE_CLIENT_SECRET` |
   | GitHub | [github.com/settings/developers](https://github.com/settings/developers) → *OAuth Apps → New OAuth App* (one app per callback URL: GitHub allows a single *Authorization callback URL* per app, so register a second app for localhost, or set the local pair only in your local `.env`). Homepage `https://accounts.3m4.net`. | scope `read:user user:email` (GitHub emails are fetched from `/user/emails`; only `verified: true` ones count) | `OAUTH_GITHUB_CLIENT_ID`, `OAUTH_GITHUB_CLIENT_SECRET` |
   | Discord | [discord.com/developers/applications](https://discord.com/developers/applications) → *New Application* → **OAuth2**: add both redirect URLs, copy the *Client ID* and *Reset Secret*. | scopes `identify email` | `OAUTH_DISCORD_CLIENT_ID`, `OAUTH_DISCORD_CLIENT_SECRET` |

   After editing `.env`: `docker compose ... up -d api web` and check
   `curl -sS https://accounts.3m4.net/api/auth/providers`.
8. **Facebook** (later, for sharing from the games): needs a Meta developer
   app, *Facebook Login* product, business verification and app review before
   non-testers can log in. Out of scope for phase 1; the provider table in the
   API is the only place to add it.
9. **Backups + housekeeping**: `first-deploy.sh` adds both cron lines
   (`backup.sh` at 03:25, `python -m dbcore.cli prune` at 04:35 — expired
   sessions and email tokens, delivered outbox rows older than 7 days).
10. **Relying apps**: each app only needs `ACCOUNTS_URL=https://accounts.3m4.net`
    (issuer + JWKS location) and, for the web nav, `VITE_ACCOUNTS_URL`. See
    `CONTRACT.md → Relying apps` and `packages/relying-party/`.

## Updates

```sh
cd /opt/accounts && git pull --ff-only && cd deploy
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml up -d --build --remove-orphans
```
`.github/workflows/deploy.yml` does exactly this on every push to `main` once
`DEPLOY_ENABLED=true` and the `DEPLOY_HOST` / `DEPLOY_SSH_KEY` secrets are set.

## Key rotation

1. `make genkey` → new seed. Put the **current** public key (base64url; print it
   with `python -m dbcore.cli pubkey`) into `SESSION_PREVIOUS_PUBLIC_KEYS` and
   the new seed into `SESSION_SIGNING_KEY`.
2. `up -d api web worker`. New sessions are signed with the new key; the JWKS
   lists both, so tokens signed by the old key keep verifying.
3. After `SESSION_TTL_MIN` (15 min) every old access token has expired: clear
   `SESSION_PREVIOUS_PUBLIC_KEYS` and restart once more. Refresh tokens are not
   signed, so nobody is logged out by a rotation.

## Smoke

```sh
BASE_URL=https://accounts.3m4.net sh deploy/smoke.sh
```

## OAuth providers

Installing the pairs: `bash deploy/set-oauth.sh [google github discord]` from your
machine asks for each client id and secret (secret without echo), writes them into
`/opt/accounts/.env` over SSH and restarts the API, then prints the providers now enabled.
