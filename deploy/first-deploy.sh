#!/usr/bin/env bash
# First production deploy of accounts on the 3m4 box. Run ON THE SERVER as root:
#   bash /opt/accounts/deploy/first-deploy.sh
# or from your machine:
#   ssh root@<server> 'bash -s' < deploy/first-deploy.sh
#
# Idempotent: re-running keeps an existing .env and just rebuilds/restarts.
# Prerequisites (see PRODUCTION.md): `edge` network created, 3m4's
# Caddyfile.prod has the accounts.3m4.net block, DNS A record accounts -> this
# server. OAuth client ids/secrets and the Resend SMTP URL are filled in by
# hand afterwards (the script leaves them empty: providers stay hidden and mail
# is logged-and-skipped until then).
set -euo pipefail

if [ ! -d /opt/accounts/.git ]; then
  git clone -q git@github.com:Devace-93/accounts.git /opt/accounts
  echo "✓ cloned /opt/accounts"
fi
cd /opt/accounts
git pull -q --ff-only

if [ ! -f .env ]; then
  cp .env.example .env
  set_var() { sed -i "s|^$1=.*|$1=$2|" .env; grep -q "^$1=" .env || echo "$1=$2" >> .env; }
  # Reuse a value from the 3m4 stack's env (same PostHog project; accounts prefixes its flag keys).
  from3m4() { v=$(grep -E "^$1=" /opt/3m4/.env | head -1 | cut -d= -f2-); set_var "$2" "$v"; }
  secret() { python3 -c "import secrets; print(secrets.token_urlsafe($1))"; }
  # Ed25519 seed, base64url without padding (what SESSION_SIGNING_KEY expects;
  # same output as `python -m dbcore.cli genkey`).
  seed() { python3 -c "import base64, secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip('='))"; }

  PG_PASS=$(secret 24)
  set_var POSTGRES_PASSWORD "$PG_PASS"
  set_var DATABASE_URL "postgresql+psycopg://accounts:$PG_PASS@postgres:5432/accounts"
  set_var SESSION_SIGNING_KEY "$(seed)"
  set_var SECRET_KEY "$(secret 48)"
  set_var IP_HASH_SECRET "$(secret 32)"
  set_var COOKIE_DOMAIN .3m4.net
  set_var COOKIE_SECURE true
  set_var ACCOUNTS_URL https://accounts.3m4.net
  set_var VITE_API_URL /api
  set_var VITE_APP_URL https://accounts.3m4.net
  # Mail stays disabled until SMTP_URL (Resend) is filled in by hand. Use
  # smtp://resend:<key>@smtp.resend.com:587?starttls=1 — Hetzner blocks port 465.
  set_var MAIL_ENABLED false
  from3m4 POSTHOG_API_KEY POSTHOG_API_KEY
  from3m4 POSTHOG_PERSONAL_API_KEY POSTHOG_PERSONAL_API_KEY
  from3m4 POSTHOG_HOST POSTHOG_HOST
  from3m4 VITE_POSTHOG_KEY VITE_POSTHOG_KEY
  from3m4 VITE_POSTHOG_HOST VITE_POSTHOG_HOST
  chmod 600 .env
  echo "✓ .env written — fill in SMTP_URL (then MAIL_ENABLED=true) and the OAUTH_* pairs, then re-run this script"
fi

cd deploy
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml up -d --build --remove-orphans
docker image prune -f >/dev/null

# Nightly backup + housekeeping (expired sessions / tokens, delivered outbox rows), added once.
CRON=$(crontab -l 2>/dev/null || true)
grep -q '/opt/accounts/deploy/backup.sh' <<<"$CRON" || CRON+=$'\n25 3 * * * /opt/accounts/deploy/backup.sh'
grep -q 'accounts-prune.log' <<<"$CRON" || CRON+=$'\n35 4 * * * cd /opt/accounts/deploy && docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml run --rm migrate python -m dbcore.cli prune >> /var/log/accounts-prune.log 2>&1'
printf '%s\n' "$CRON" | sed '/^$/d' | crontab -

echo "--- status"
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml ps --format '{{.Name}} {{.Status}}'
# Health through the edge Caddy (TLS needs DNS; this hits it by Host header over the docker network).
docker exec 3m4-caddy-1 wget -qO- --header 'Host: accounts.3m4.net' http://localhost/api/healthz 2>/dev/null || \
  docker run --rm --network edge curlimages/curl -s http://accounts-api-1:5000/api/healthz
echo
