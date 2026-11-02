# m4pay (Python)

Reference client for apps that consume `payments.3m4.net`. One file, no
framework dependency beyond `requests` (Flask helpers import Flask lazily).
Vendor it as `dbcore/m4pay.py` next to `dbcore/m4session.py`.

```python
import os
from m4pay import M4PayClient, verify_webhook, WebhookError, flask_webhook_view, flask_require_entitlement

client = M4PayClient(
    os.environ.get("PAYMENTS_INTERNAL_URL", "https://payments.3m4.net"),
    app="retro",
    service_key=os.environ["PAYMENTS_SERVICE_KEY"],   # from `python -m dbcore.cli app-key retro <webhook_url>`
)
```

## Pull

| Call | Returns |
|---|---|
| `client.entitlements(identity_id)` | `{"app", "entitlements": ["pro"], "subscription": {status, current_period_end, cancel_at_period_end, …} \| null, "updated_at"}` |
| `client.subscriptions(updated_since=None)` | iterator over every subscription row of the app (`identity_id`, `email`, `entitlements`, `status`, …), following `next_cursor` |

Errors raise `M4PayError(status, code, message)`; `403 forbidden` means the key
belongs to another app.

## Push (webhooks)

payments POSTs `{"id", "type", "created", "app", "identity_id", "email", "data": {"entitlements", "subscription", "payment", "updated_at"}}`
with `X-M4Pay-Event-Id`, `X-M4Pay-Timestamp` and
`X-M4Pay-Signature: v1=hex_hmac_sha256(secret, f"{timestamp}.{body}")`.

```python
event = verify_webhook(secret, request.get_data(), request.headers, tolerance=300)   # raises WebhookError
```

Types: `subscription.updated`, `payment.succeeded`, `payment.refunded`,
`payment.claimed`. **Every** event carries the full current entitlement set, so
upsert from `data.entitlements` and ignore ordering; dedupe on `id`.

Flask:

```python
def on_event(event):
    with session_scope() as s:
        if s.get(WebhookEvent, event["id"]): return "duplicate"
        s.add(WebhookEvent(id=event["id"], type=event["type"]))
        account = account_for_identity(s, event["identity_id"])
        account.plan = resolve_plan_from_entitlements(event["data"]["entitlements"])

app.add_url_rule("/api/billing/webhook", view_func=flask_webhook_view(os.environ["PAYMENTS_WEBHOOK_SECRET"], on_event), methods=["POST"])
```

## Gating a route

```python
require_pro = flask_require_entitlement("pro", client=client, cache_ttl=60,
                                        on_error=lambda s, c, m: ApiError(s, c, m))

@app.get("/api/export")
@require_session      # m4session: sets g.identity
@require_pro          # 402 entitlement_required
def export(): ...
```

The decorator caches per identity for `cache_ttl` seconds and keeps serving
the cache when payments is unreachable (503 `payments_unavailable` only when
there is nothing cached).

## Buttons

Static pages and dashboards use `pay.js` / `m4pay.ts` (see `packages/pay-js`
and `packages/relying-party/ts`); the backend never creates checkouts.
