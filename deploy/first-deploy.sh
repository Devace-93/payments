#!/usr/bin/env bash
# First production deploy of payments on the 3m4 box. Run ON THE SERVER as root:
#   bash /opt/payments/deploy/first-deploy.sh
# or from your machine:
#   ssh root@<server> 'bash -s' < deploy/first-deploy.sh
#
# Idempotent: re-running keeps an existing .env and just rebuilds/restarts.
# Prerequisites (see PRODUCTION.md): `edge` network created, 3m4's
# Caddyfile.prod has the payments.3m4.net block, DNS A record payments -> this
# server, accounts deployed (the JWKS is fetched from accounts-api-1). The
# Stripe keys and the Resend SMTP URL are filled in by hand afterwards (the
# script leaves them empty: the stack runs with the fake Stripe and mail is
# logged-and-skipped until then). Deploy ALONE: no other stack building at the
# same time (4 GB box).
set -euo pipefail

if [ ! -d /opt/payments/.git ]; then
  git clone -q git@github.com:Devace-93/payments.git /opt/payments
  echo "✓ cloned /opt/payments"
fi
cd /opt/payments
git pull -q --ff-only

if [ ! -f .env ]; then
  cp .env.example .env
  set_var() { sed -i "s|^$1=.*|$1=$2|" .env; grep -q "^$1=" .env || echo "$1=$2" >> .env; }
  # Reuse a value from the 3m4 stack's env (same PostHog project; payments prefixes its flag keys).
  from3m4() { v=$(grep -E "^$1=" /opt/3m4/.env | head -1 | cut -d= -f2-); set_var "$2" "$v"; }
  secret() { python3 -c "import secrets; print(secrets.token_urlsafe($1))"; }
  letters() { python3 -c "import random, string; print(''.join(random.choice(string.ascii_lowercase) for _ in range(8)))"; }

  PG_PASS=$(secret 24)
  set_var POSTGRES_PASSWORD "$PG_PASS"
  set_var DATABASE_URL "postgresql+psycopg://payments:$PG_PASS@postgres:5432/payments"
  set_var SECRET_KEY "$(secret 48)"
  set_var PAYMENTS_URL https://payments.3m4.net
  set_var ACCOUNTS_URL https://accounts.3m4.net
  set_var ACCOUNTS_INTERNAL_URL http://accounts-api-1:5000
  set_var STRIPE_SECRET_KEY ""
  set_var STRIPE_WEBHOOK_SECRET ""
  set_var STRIPE_INTEGRATION_IDENTIFIER "3m4-payments-$(letters)"
  set_var VITE_API_URL /api
  set_var VITE_APP_URL https://payments.3m4.net
  set_var VITE_ACCOUNTS_URL https://accounts.3m4.net
  # Mail stays disabled until SMTP_URL (Resend) is filled in by hand. Use
  # smtp://resend:<key>@smtp.resend.com:587?starttls=1 — Hetzner blocks port 465.
  set_var MAIL_ENABLED false
  set_var SMTP_URL ""
  from3m4 POSTHOG_API_KEY POSTHOG_API_KEY
  from3m4 POSTHOG_PERSONAL_API_KEY POSTHOG_PERSONAL_API_KEY
  from3m4 POSTHOG_HOST POSTHOG_HOST
  from3m4 VITE_POSTHOG_KEY VITE_POSTHOG_KEY
  from3m4 VITE_POSTHOG_HOST VITE_POSTHOG_HOST
  chmod 600 .env
  echo "✓ .env written — fill in STRIPE_SECRET_KEY / STRIPE_WEBHOOK_SECRET and SMTP_URL (then MAIL_ENABLED=true), then re-run this script"
fi

cd deploy
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml up -d --build --remove-orphans
docker image prune -f >/dev/null

# Nightly backup + housekeeping (finished outbox rows, stale checkouts, dead claim codes), added once.
CRON=$(crontab -l 2>/dev/null || true)
grep -q '/opt/payments/deploy/backup.sh' <<<"$CRON" || CRON+=$'\n45 3 * * * /opt/payments/deploy/backup.sh'
grep -q 'payments-prune.log' <<<"$CRON" || CRON+=$'\n55 4 * * * cd /opt/payments/deploy && docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml run --rm migrate python -m dbcore.cli prune >> /var/log/payments-prune.log 2>&1'
grep -q 'payments-geoip.log' <<<"$CRON" || CRON+=$'\n15 5 * * 2 cd /opt/payments/deploy && docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml exec -T api python -m dbcore.cli geoip-update >> /var/log/payments-geoip.log 2>&1'
printf '%s\n' "$CRON" | sed '/^$/d' | crontab -

echo "--- status"
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml ps --format '{{.Name}} {{.Status}}'
# Health through the edge Caddy (TLS needs DNS; this hits it by Host header over the docker network).
docker exec 3m4-caddy-1 wget -qO- --header 'Host: payments.3m4.net' http://localhost/api/healthz 2>/dev/null || \
  docker run --rm --network edge curlimages/curl -s http://payments-api-1:5000/api/healthz
echo
