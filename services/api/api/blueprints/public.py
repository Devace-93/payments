"""Public routes: the supporters list (``/api/public/supporters``) and the
badges served at the host root (``/badge/<handle>.svg|.json``,
``/badge/u/<identity_id>.svg|.json``). Always 200, CORS ``*``."""
from __future__ import annotations

import uuid

from flask import Blueprint, Response, jsonify, request
from sqlalchemy import select

from dbcore import badges
from dbcore.db import session_scope
from dbcore.entitlements import is_entitled
from dbcore.feature_flags import is_enabled
from dbcore.models import App, Customer, Payment, Subscription

from ..errors import ApiError
from ..extensions import limiter

bp = Blueprint("public", __name__)

ENTITLED_TIER = {"pro": "pro", "team": "team"}


def _badge_response(session, *, handle: str | None, identity_id: str | None, fmt: str):
    tier = "none"
    if is_enabled("badges"):
        uid = badges.resolve_identity(session, handle=handle, identity_id=identity_id)
        tier = badges.tier_for(session, uid)
    etag = badges.etag(tier, fmt)
    if request.headers.get("If-None-Match") == etag:
        resp = Response(status=304)
    elif fmt == "json":
        resp = jsonify(badges.shields_json(tier))
    else:
        resp = Response(badges.svg(tier), mimetype="image/svg+xml")
    resp.headers["ETag"] = etag
    resp.headers["Cache-Control"] = "public, max-age=3600"
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@bp.get("/badge/<handle>.svg")
@limiter.exempt
def badge_svg(handle: str):
    with session_scope() as session:
        return _badge_response(session, handle=handle, identity_id=None, fmt="svg")


@bp.get("/badge/<handle>.json")
@limiter.exempt
def badge_json(handle: str):
    with session_scope() as session:
        return _badge_response(session, handle=handle, identity_id=None, fmt="json")


@bp.get("/badge/u/<identity_id>.svg")
@limiter.exempt
def badge_svg_by_id(identity_id: str):
    with session_scope() as session:
        return _badge_response(session, handle=None, identity_id=identity_id, fmt="svg")


@bp.get("/badge/u/<identity_id>.json")
@limiter.exempt
def badge_json_by_id(identity_id: str):
    with session_scope() as session:
        return _badge_response(session, handle=None, identity_id=identity_id, fmt="json")


def _since(dt) -> str | None:
    return dt.strftime("%Y-%m") if dt else None


@bp.get("/api/public/supporters")
def supporters():
    slug = (request.args.get("app") or "").strip().lower()
    try:
        limit = max(1, min(int(request.args.get("limit", 50)), 200))
    except ValueError:
        limit = 50
    with session_scope() as session:
        app = session.scalar(select(App).where(App.slug == slug)) if slug else None
        if app is None:
            raise ApiError(400, "unknown_app", "Unknown app.")
        items: dict[str, dict] = {}
        payments = session.scalars(
            select(Payment)
            .where(Payment.app_id == app.id, Payment.public.is_(True), Payment.status.in_(("paid", "partially_refunded")))
            .order_by(Payment.created_at)
        ).all()
        subs = session.scalars(select(Subscription).where(Subscription.app_id == app.id)).all()
        identity_ids = {p.identity_id for p in payments if p.identity_id} | {s.identity_id for s in subs}
        customers = {
            c.identity_id: c
            for c in session.scalars(select(Customer).where(Customer.identity_id.in_(identity_ids or {uuid.uuid4()}))).all()
        }
        for payment in payments:
            if payment.identity_id is not None:
                customer = customers.get(payment.identity_id)
                if customer is None or not customer.public_supporter:
                    continue
                key = str(payment.identity_id)
                name = customer.display_name or customer.name or customer.handle or "anonymous"
                handle = customer.handle
            else:
                key = f"guest:{payment.id}"
                name = payment.display_name or "anonymous"
                handle = None
            entry = items.setdefault(
                key, {"display_name": name, "handle": handle, "tier": "supporter", "since": _since(payment.created_at), "message": None}
            )
            if payment.message:
                entry["message"] = payment.message
        for sub in subs:
            if not is_entitled(sub):
                continue
            customer = customers.get(sub.identity_id)
            if customer is None or not customer.public_supporter:
                continue
            key = str(sub.identity_id)
            entry = items.setdefault(
                key,
                {
                    "display_name": customer.display_name or customer.name or customer.handle or "anonymous",
                    "handle": customer.handle,
                    "tier": "supporter",
                    "since": _since(sub.created_at),
                    "message": None,
                },
            )
            tier = ENTITLED_TIER.get((sub.entitlement or "").lower(), "supporter")
            if badges.TIERS.index(tier) > badges.TIERS.index(entry["tier"]):
                entry["tier"] = tier
        rows = sorted(items.values(), key=lambda e: (-badges.TIERS.index(e["tier"]), e["since"] or ""))[:limit]
    resp = jsonify({"items": rows})
    resp.headers["Cache-Control"] = "public, max-age=300"
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp
