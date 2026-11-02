"""m4pay — consume payments.3m4.net from any Python app.

Zero framework dependency (``requests`` only). Drop this file into your
project (or vendor it as ``dbcore/m4pay.py``) and:

    from m4pay import M4PayClient, verify_webhook, WebhookError, flask_webhook_view, flask_require_entitlement

    # 1. Pull: what does this identity (accounts `sub`) have in my app?
    client = M4PayClient("https://payments.3m4.net", app="retro", service_key=os.environ["PAYMENTS_SERVICE_KEY"])
    client.entitlements(identity_id)          # {"app", "entitlements": ["pro"], "subscription": {...}|None, "updated_at"}
    for row in client.subscriptions(updated_since="2026-11-01T00:00:00Z"):   # nightly reconcile
        ...

    # 2. Push: verify a webhook delivered to your backend (CONTRACT.md §6).
    event = verify_webhook(secret, request.get_data(), request.headers)      # raises WebhookError
    # event = {"id", "type": "subscription.updated|payment.succeeded|payment.refunded|payment.claimed",
    #          "created", "app", "identity_id", "email", "data": {"entitlements", "subscription", "payment", "updated_at"}}

    # 3. Flask helpers
    app.add_url_rule("/api/billing/webhook", view_func=flask_webhook_view(secret, handler), methods=["POST"])
    require_pro = flask_require_entitlement("pro", client=client, cache_ttl=60)

    @app.get("/api/export")
    @require_session          # from m4session: sets g.identity
    @require_pro              # 402 entitlement_required otherwise
    def export(): ...

Every event carries the FULL current entitlement set for (identity, app):
upsert from ``data.entitlements`` and ignore ordering; dedupe on ``id``.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from functools import wraps
from typing import Any

import requests

__all__ = [
    "M4PayClient",
    "M4PayError",
    "WebhookError",
    "flask_require_entitlement",
    "flask_webhook_view",
    "sign",
    "verify_webhook",
]

SIGNATURE_HEADER = "X-M4Pay-Signature"
TIMESTAMP_HEADER = "X-M4Pay-Timestamp"
EVENT_ID_HEADER = "X-M4Pay-Event-Id"


class WebhookError(Exception):
    """The delivery is not authentic (bad signature, stale timestamp, bad body)."""


class M4PayError(Exception):
    """The payments API answered an error. ``status`` / ``code`` / ``message``."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message


def sign(secret: str, timestamp: int, body: bytes) -> str:
    """``v1=<hex hmac_sha256(secret, f"{timestamp}.{body}")>`` — the reference
    signer, identical to the payments worker."""
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"v1={mac}"


def _header(headers: Mapping[str, str], name: str) -> str | None:
    value = headers.get(name)
    if value is not None:
        return value
    lowered = name.lower()
    for key, val in headers.items():
        if key.lower() == lowered:
            return val
    return None


def verify_webhook(secret: str, body: bytes | str, headers: Mapping[str, str], tolerance: int = 300) -> dict:
    """Verify a push delivery and return the parsed event. Raises
    :class:`WebhookError` on a bad signature, a timestamp outside
    ``tolerance`` seconds, or a body that is not a JSON object."""
    if not secret:
        raise WebhookError("no webhook secret configured")
    raw = body.encode() if isinstance(body, str) else bytes(body)
    ts_header = _header(headers, TIMESTAMP_HEADER)
    sig_header = _header(headers, SIGNATURE_HEADER) or ""
    try:
        timestamp = int(ts_header or "")
    except ValueError as err:
        raise WebhookError("missing or malformed timestamp") from err
    if abs(time.time() - timestamp) > tolerance:
        raise WebhookError("timestamp outside tolerance")
    presented = [part.strip() for part in sig_header.split(",") if part.strip().startswith("v1=")]
    expected = sign(secret, timestamp, raw)
    if not any(hmac.compare_digest(candidate, expected) for candidate in presented):
        raise WebhookError("signature mismatch")
    try:
        event = json.loads(raw)
    except ValueError as err:
        raise WebhookError("body is not JSON") from err
    if not isinstance(event, dict) or not event.get("id"):
        raise WebhookError("body is not an event")
    return event


class M4PayClient:
    """Pull API client (``Authorization: Bearer m4pay_sk_…``)."""

    def __init__(self, base_url: str, *, app: str, service_key: str, timeout: float = 5.0, session: requests.Session | None = None):
        self.base_url = base_url.rstrip("/")
        self.app = app
        self._key = service_key
        self.timeout = timeout
        self._http = session or requests.Session()

    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = self._http.get(
            f"{self.base_url}{path}",
            params={"app": self.app, **(params or {})},
            headers={"Authorization": f"Bearer {self._key}", "Accept": "application/json"},
            timeout=self.timeout,
        )
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if resp.status_code >= 400:
            err = (data.get("error") or {}) if isinstance(data, dict) else {}
            raise M4PayError(resp.status_code, err.get("code", "error"), err.get("message", resp.text[:200]))
        return data

    def entitlements(self, identity_id: str) -> dict:
        """``{"app", "entitlements": [...], "subscription": {...}|None, "updated_at"}``."""
        return self._get(f"/api/v1/entitlements/{identity_id}")

    def subscriptions(self, updated_since: str | None = None) -> Iterator[dict]:
        """Every subscription row of the app (optionally changed since an ISO
        timestamp), following ``next_cursor`` pages."""
        cursor: str | None = None
        while True:
            params: dict[str, str] = {}
            if updated_since:
                params["updated_since"] = updated_since
            if cursor:
                params["cursor"] = cursor
            page = self._get("/api/v1/subscriptions", params)
            yield from page.get("items", [])
            cursor = page.get("next_cursor")
            if not cursor:
                return


def flask_webhook_view(secret: str, handler: Callable[[dict], Any]):
    """A Flask view that verifies the delivery and calls ``handler(event)``.
    Answers ``400`` on a bad signature and ``200 {"status": "ok"}`` after
    the handler returns (raise inside it to make payments retry)."""
    from flask import jsonify, request

    def view():
        try:
            event = verify_webhook(secret, request.get_data(), request.headers)
        except WebhookError as err:
            return jsonify({"error": {"code": "invalid_signature", "message": str(err)}}), 400
        result = handler(event)
        return jsonify({"status": "ok", "result": result if isinstance(result, (str, int, dict, list)) else None})

    view.__name__ = "m4pay_webhook"
    return view


def _default_on_error(status: int, code: str, message: str) -> Exception:
    err = M4PayError(status, code, message)
    return err


def flask_require_entitlement(
    entitlement: str,
    *,
    client: M4PayClient,
    cache_ttl: int = 60,
    identity_getter: Callable[[], str | None] | None = None,
    on_error: Callable[[int, str, str], Exception] = _default_on_error,
):
    """Decorator: 402 ``entitlement_required`` unless the current identity
    (``g.identity["sub"]`` from m4session, or ``identity_getter()``) holds
    ``entitlement`` in this app. Results are cached per identity for
    ``cache_ttl`` seconds; a payments outage keeps serving the cache."""
    cache: dict[str, tuple[float, set[str]]] = {}
    lock = threading.Lock()

    def _entitlements(identity_id: str) -> set[str]:
        now = time.time()
        with lock:
            hit = cache.get(identity_id)
            if hit and now - hit[0] < cache_ttl:
                return hit[1]
        try:
            names = set(client.entitlements(identity_id).get("entitlements") or [])
        except (M4PayError, requests.RequestException):
            with lock:
                hit = cache.get(identity_id)
            if hit:
                return hit[1]
            raise
        with lock:
            cache[identity_id] = (now, names)
        return names

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if identity_getter is not None:
                identity_id = identity_getter()
            else:
                from flask import g

                identity = getattr(g, "identity", None) or {}
                identity_id = identity.get("sub")
            if not identity_id:
                raise on_error(401, "no_session", "Not signed in.")
            try:
                names = _entitlements(str(identity_id))
            except (M4PayError, requests.RequestException):
                raise on_error(503, "payments_unavailable", "Could not check the subscription.") from None
            if entitlement not in names:
                raise on_error(402, "entitlement_required", f"'{entitlement}' is required.")
            return view(*args, **kwargs)

        return wrapper

    return decorator
