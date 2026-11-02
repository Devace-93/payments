"""ORM rows → the JSON shapes in CONTRACT.md, plus the JSON-body reader that
enforces ``Content-Type: application/json`` on state-changing endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote

from flask import request

from dbcore.config import config
from dbcore.entitlements import serialize_subscription as _serialize_subscription

from .errors import ApiError


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def json_body() -> dict:
    """The request's JSON object. Non-JSON content types are a 415 (CSRF
    defence: HTML forms cannot send ``application/json``); an empty JSON
    body is ``{}``; a JSON value that is not an object is a 400."""
    if not request.is_json:
        raise ApiError(415, "unsupported_media_type", "Send a JSON body with Content-Type: application/json.")
    data = request.get_json(silent=True)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ApiError(400, "invalid_body", "Request body must be a JSON object.")
    return data


def serialize_identity(claims: dict) -> dict:
    return {
        "id": claims.get("sub"),
        "email": claims.get("email"),
        "handle": claims.get("handle"),
        "name": claims.get("name"),
    }


def serialize_customer(customer) -> dict:
    return {
        "has_stripe_customer": bool(customer.stripe_customer_id),
        "public_supporter": bool(customer.public_supporter),
        "display_name": customer.display_name,
        "preferred_currency": customer.preferred_currency,
    }


def serialize_payment(payment, app_slug: str | None) -> dict:
    return {
        "id": str(payment.id),
        "app": app_slug,
        "kind": payment.kind,
        "amount": payment.amount,
        "currency": payment.currency,
        "amount_refunded": payment.amount_refunded,
        "status": payment.status,
        "created_at": iso(payment.created_at),
        "claimed_at": iso(payment.claimed_at),
        "public": bool(payment.public),
        "display_name": payment.display_name,
        "message": payment.message,
    }


def serialize_subscription(sub, app_slug: str | None, label: str | None) -> dict:
    out = _serialize_subscription(sub, label=label or "") or {}
    out["app"] = app_slug
    return out


def badge_links(identity_id: str, handle: str | None) -> dict:
    base = config.payments_url
    slug = handle or f"u/{identity_id}"
    svg_url = f"{base}/badge/{slug}.svg"
    json_url = f"{base}/badge/{slug}.json"
    stable_svg_url = f"{base}/badge/u/{identity_id}.svg"
    link = f"{base}/?ref=badge"
    return {
        "svg_url": svg_url,
        "json_url": json_url,
        "stable_svg_url": stable_svg_url,
        "markdown": f"[![3m4 supporter]({svg_url})]({link})",
        "html": f'<a href="{link}"><img src="{svg_url}" alt="3m4 supporter" height="20"></a>',
        "shields_url": f"https://img.shields.io/endpoint?url={quote(json_url, safe='')}",
    }
