#!/usr/bin/env sh
# Smoke test for a running accounts stack: health, JWKS shape, session.js
# headers, sign up with a cookie jar → GET /api/session → log out → 401.
#   BASE_URL=http://localhost:8085 sh deploy/smoke.sh
# Creates a throwaway user, so it needs signups ON. Mail is not checked here
# (see e2e/ for the verification and magic-link flows through Mailpit).
set -eu
BASE_URL="${BASE_URL:-http://localhost:8085}"
API="$BASE_URL/api"
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36 smoke"
JAR="$(mktemp)"
trap 'rm -f "$JAR"' EXIT

say() { printf '\033[36m▸ %s\033[0m\n' "$1"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 1; }; }
need curl; need python3

say "health"
curl -fsS "$API/healthz" | grep -q '"ok"' && echo "  api ok"
curl -fsS "$BASE_URL/healthz" | grep -q '"ok"' && echo "  api ok at the host root"

say "jwks"
curl -fsS "$BASE_URL/.well-known/jwks.json" | python3 -c '
import json, sys
keys = json.load(sys.stdin)["keys"]
assert keys, "no keys"
k = keys[0]
assert k["kty"] == "OKP" and k["crv"] == "Ed25519" and k["alg"] == "EdDSA" and k["kid"] and k["x"], k
print("  %d key(s), active kid %s" % (len(keys), k["kid"]))'
curl -fsS -o /dev/null -D - "$BASE_URL/.well-known/jwks.json" | tr -d '\r' | grep -iE '^cache-control:' | sed 's/^/  /'

say "session.js headers"
curl -fsS -o /dev/null -D - "$BASE_URL/session.js" | tr -d '\r' | grep -iE '^(content-type|cache-control|access-control-allow-origin):' | sed 's/^/  /'

say "sign up (cookie jar)"
STAMP=$(date +%s)
EMAIL="smoke-$STAMP@example.com"
curl -fsS -c "$JAR" -b "$JAR" -X POST "$API/auth/signup" -H 'Content-Type: application/json' -H "User-Agent: $UA" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Smoke-Passw0rd!\",\"handle\":\"smoke-$STAMP\"}" \
  | python3 -c 'import json,sys; u=json.load(sys.stdin)["user"]; print("  user %s handle %s verified=%s" % (u["id"], u["handle"], u["email_verified"]))'
grep -q '3m4_session' "$JAR" && echo "  3m4_session cookie set"
grep -q '3m4_refresh' "$JAR" && echo "  3m4_refresh cookie set"

say "session from the cookie"
USER_ID=$(curl -fsS -b "$JAR" "$API/session" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["user"]["id"])')
echo "  user $USER_ID"

say "default avatar"
curl -fsS -o /dev/null -w "  %{http_code} %{content_type}\n" "$BASE_URL/avatars/$USER_ID"

say "refresh rotates the cookies"
curl -fsS -c "$JAR" -b "$JAR" -X POST "$API/session/refresh" -H 'Content-Type: application/json' -d '{}' >/dev/null && echo "  refreshed"

say "log out"
curl -fsS -c "$JAR" -b "$JAR" -X POST "$API/session/logout" -H 'Content-Type: application/json' -d '{}' -o /dev/null -w "  %{http_code}\n"
CODE=$(curl -sS -b "$JAR" -o /dev/null -w '%{http_code}' "$API/session")
[ "$CODE" = "401" ] && echo "  session gone (401)" || { echo "  expected 401 after logout, got $CODE" >&2; exit 1; }
echo "smoke ok"
