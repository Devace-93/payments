#!/usr/bin/env bash
# Nightly Postgres dump for the accounts stack. Keeps 14 days.
set -euo pipefail
DIR=/opt/backups/accounts
mkdir -p "$DIR"
cd /opt/accounts/deploy
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U accounts -d accounts | gzip > "$DIR/accounts-$(date +%F).sql.gz"
find "$DIR" -name 'accounts-*.sql.gz' -mtime +14 -delete
