#!/usr/bin/env bash
# Nightly Postgres dump for the payments stack. Keeps 14 days.
set -euo pipefail
DIR=/opt/backups/payments
mkdir -p "$DIR"
cd /opt/payments/deploy
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U payments -d payments | gzip > "$DIR/payments-$(date +%F).sql.gz"
find "$DIR" -name 'payments-*.sql.gz' -mtime +14 -delete
