#!/usr/bin/env sh
# Smoke test for a running payments stack: health, catalog, pay.js headers,
# the grey badge, geo and the fee hint. Read-only: creates nothing.
#   BASE_URL=http://localhost:8086 sh deploy/smoke.sh
set -eu
BASE_URL="${BASE_URL:-http://localhost:8086}"
API="$BASE_URL/api"

say() { printf '\033[36m▸ %s\033[0m\n' "$1"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 1; }; }
need curl; need python3

say "health"
curl -fsS "$API/healthz" | grep -q '"ok"' && echo "  api ok"
curl -fsS "$BASE_URL/healthz" | grep -q '"ok"' && echo "  api ok at the host root"

say "catalog (retro)"
curl -fsS "$API/catalog?app=retro" | python3 -c '
import json, sys
c = json.load(sys.stdin)
assert c["app"]["slug"] == "retro", c
assert c["currencies"] and c["default_currency"] in c["currencies"], c
assert all(c["donation"]["min"][cur] > 0 for cur in c["currencies"]), c
print("  %s · currencies %s · min %s · %d product(s)" % (c["app"]["name"], ",".join(c["currencies"]), c["donation"]["min"], len(c["products"])))'
curl -fsS -o /dev/null -D - "$API/catalog?app=retro" | tr -d '\r' | grep -iE '^(cache-control|access-control-allow-origin):' | sed 's/^/  /'
CODE=$(curl -sS -o /dev/null -w '%{http_code}' "$API/catalog?app=nope")
[ "$CODE" = "400" ] && echo "  unknown app → 400" || { echo "  expected 400 for unknown app, got $CODE" >&2; exit 1; }

say "geo + fees"
curl -fsS "$API/geo" | sed 's/^/  /'; echo
curl -fsS "$API/fees?amount=500&currency=usd" | python3 -c 'import json,sys; f=json.load(sys.stdin); print("  retention %.1f%% · min %d" % (f["retention"]*100, f["min_amount"]))'

say "pay.js headers"
curl -fsS -o /dev/null -D - "$BASE_URL/pay.js" | tr -d '\r' | grep -iE '^(content-type|cache-control|access-control-allow-origin):' | sed 's/^/  /'

say "badge (unknown handle → grey, 200)"
curl -fsS -o /dev/null -D - "$BASE_URL/badge/nobody.svg" | tr -d '\r' | grep -iE '^(HTTP|content-type|cache-control|etag|access-control-allow-origin)' | sed 's/^/  /'
curl -fsS "$BASE_URL/badge/nobody.json" | grep -q '"not a supporter"' && echo "  shields json ok"

say "session required"
CODE=$(curl -sS -o /dev/null -w '%{http_code}' "$API/me")
[ "$CODE" = "401" ] && echo "  /api/me without session → 401" || { echo "  expected 401, got $CODE" >&2; exit 1; }
echo "smoke ok"
