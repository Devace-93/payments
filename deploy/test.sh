#!/usr/bin/env sh
# Run the backend test suite (services/api/tests) against a disposable Postgres
# and Redis started with `docker run`, using a local virtualenv in .venv.
#   make test            # or: sh deploy/test.sh [pytest args]
# The containers are removed when the script exits, whatever the outcome.
set -eu
cd "$(dirname "$0")/.."

PG=accounts-test-pg
RD=accounts-test-redis
PG_PORT="${TEST_PG_PORT:-55432}"
RD_PORT="${TEST_REDIS_PORT:-56379}"

cleanup() { docker rm -f "$PG" "$RD" >/dev/null 2>&1 || true; }
trap cleanup EXIT INT TERM
cleanup

docker run -d --rm --name "$PG" -e POSTGRES_USER=accounts -e POSTGRES_PASSWORD=accounts -e POSTGRES_DB=accounts_test \
  -p "$PG_PORT:5432" postgres:16-alpine >/dev/null
docker run -d --rm --name "$RD" -p "$RD_PORT:6379" redis:7-alpine >/dev/null

i=0
until docker exec "$PG" pg_isready -U accounts >/dev/null 2>&1; do
  i=$((i + 1)); [ "$i" -lt 60 ] || { echo "postgres did not come up" >&2; exit 1; }; sleep 1
done

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate
pip install -q -r services/api/requirements.txt -r services/api/requirements-dev.txt

export DATABASE_URL="postgresql+psycopg://accounts:accounts@localhost:$PG_PORT/accounts_test"
export TEST_DATABASE_URL="$DATABASE_URL"
export REDIS_URL="redis://localhost:$RD_PORT/0"
export SESSION_SIGNING_KEY="${SESSION_SIGNING_KEY:-$(python3 -c "import base64, secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip('='))")}"
export SECRET_KEY=test-secret IP_HASH_SECRET=test-ip-salt MAIL_ENABLED=false ACCOUNTS_URL=http://localhost:8085
export PYTHONPATH="$PWD:$PWD/services/api"

python -m pytest services/api/tests "$@"
