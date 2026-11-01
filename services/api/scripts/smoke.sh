#!/usr/bin/env bash
# Walk the CONTRACT.md happy path with curl against a RUNNING stack (mail may
# be disabled: nothing here needs a link from an e-mail).
#
#   services/api/scripts/smoke.sh                     # http://localhost:8085
#   BASE=https://accounts.3m4.net services/api/scripts/smoke.sh
#
# signup -> GET /session -> GET /me -> PATCH name -> refresh -> logout -> 401.
# Needs curl + jq.
set -euo pipefail

BASE="${BASE:-http://localhost:8085}"
API="$BASE/api"
EMAIL="${SMOKE_EMAIL:-smoke+$(date +%s)@example.com}"
PASSWORD="${SMOKE_PASSWORD:-Smoke-Passw0rd!}"
JAR="$(mktemp)"
trap 'rm -f "$JAR"' EXIT

step() { printf '\n\033[36m▶ %s\033[0m\n' "$*"; }
need() { command -v "$1" >/dev/null || { echo "missing: $1" >&2; exit 1; }; }
need curl; need jq
C=(curl -sS -c "$JAR" -b "$JAR" -H 'Content-Type: application/json')

step "health"
curl -fsS "$API/healthz" | jq -c .

step "jwks"
curl -fsS "$BASE/.well-known/jwks.json" | jq -c '.keys[0] | {kty, crv, kid, alg}'

step "signup $EMAIL"
"${C[@]}" -X POST "$API/auth/signup" -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"name\":\"Smoke Test\"}" | jq -c '.user // .error'

step "session"
"${C[@]}" "$API/session" | jq -c '{handle: .user.handle, verified: .user.email_verified, expires_at: .session.expires_at}'

step "me"
"${C[@]}" "$API/me" | jq -c '{has_password, identities}'

step "patch name"
"${C[@]}" -X PATCH "$API/me" -d '{"name":"Smoke Renamed"}' | jq -c '.user.name'

step "avatar (default svg)"
UID_=$("${C[@]}" "$API/me" | jq -r .user.id)
curl -fsS -o /dev/null -w "  %{http_code} %{content_type}\n" "$BASE/avatars/$UID_"

step "refresh"
"${C[@]}" -X POST "$API/session/refresh" | jq -c '.user.email // .error'

step "logout"
"${C[@]}" -o /dev/null -w "  %{http_code}\n" -X POST "$API/session/logout" -d '{}'

step "session after logout (expect no_session)"
"${C[@]}" "$API/session" | jq -c '.error.code'

echo
echo "smoke ok"
