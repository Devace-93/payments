"""Session endpoints: ``/api/me`` (GET/PATCH), ``/api/claim``, ``/api/portal``,
``/api/entitlements``. Identity comes only from the JWT; ``customers`` is a
mirror upserted from the claims on every call."""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request
from sqlalchemy import select

from dbcore import claims as claim_codes
from dbcore.claims import ClaimError
from dbcore.config import config
from dbcore.db import session_scope
from dbcore.entitlements import entitlements_for
from dbcore.feature_flags import is_enabled
from dbcore.models import App, Customer, Payment, Product, Subscription
from dbcore.stripe_client import as_dict, client

from ..auth import ensure_customer, require_session
from ..errors import ApiError
from ..extensions import identity_key, limiter
from ..features import require_feature
from ..returns import safe_return_to
from ..serializers import (
    badge_links,
    json_body,
    serialize_customer,
    serialize_identity,
    serialize_payment,
    serialize_subscription,
)

bp = Blueprint("me", __name__)


def _app_slugs(session, ids) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {a.id: a.slug for a in session.scalars(select(App).where(App.id.in_(ids))).all()}


@bp.get("/me")
@require_session
def get_me():
    with session_scope() as session:
        customer = ensure_customer(session, g.identity)
        payments = session.scalars(
            select(Payment).where(Payment.identity_id == g.identity_id).order_by(Payment.created_at.desc()).limit(200)
        ).all()
        subs = session.scalars(
            select(Subscription).where(Subscription.identity_id == g.identity_id).order_by(Subscription.created_at.desc())
        ).all()
        slugs = _app_slugs(session, [p.app_id for p in payments] + [s.app_id for s in subs])
        labels = {
            p.id: p.label
            for p in session.scalars(select(Product).where(Product.id.in_({s.product_id for s in subs if s.product_id} or {None}))).all()
        }
        body = {
            "identity": serialize_identity(g.identity),
            "customer": serialize_customer(customer),
            "payments": [serialize_payment(p, slugs.get(p.app_id)) for p in payments],
            "subscriptions": [serialize_subscription(s, slugs.get(s.app_id), labels.get(s.product_id)) for s in subs],
            "badge": badge_links(str(g.identity_id), customer.handle) if is_enabled("badges", g.identity["sub"]) else None,
        }
    resp = jsonify(body)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.patch("/me")
@require_session
def patch_me():
    data = json_body()
    with session_scope() as session:
        customer = ensure_customer(session, g.identity)
        if "public_supporter" in data:
            if not isinstance(data["public_supporter"], bool):
                raise ApiError(400, "validation_error", "public_supporter must be a boolean.")
            customer.public_supporter = data["public_supporter"]
        if "display_name" in data:
            value = data["display_name"]
            if value is not None and not isinstance(value, str):
                raise ApiError(400, "validation_error", "display_name must be a string.")
            value = (value or "").strip()[:80] or None
            customer.display_name = value
        if "preferred_currency" in data:
            value = data["preferred_currency"]
            if value is not None and (not isinstance(value, str) or value.lower() not in config.currencies):
                raise ApiError(400, "unsupported_currency", "Unsupported currency.")
            customer.preferred_currency = value.lower() if value else None
        body = {"customer": serialize_customer(customer)}
    return jsonify(body)


@bp.post("/claim")
@limiter.limit("5/minute", key_func=identity_key)
@limiter.limit("20/hour")
@require_session
def claim():
    data = json_body()
    code = data.get("code")
    if not isinstance(code, str) or not code.strip():
        raise ApiError(400, "invalid_code", "That code is not valid.")
    with session_scope() as session:
        ensure_customer(session, g.identity)
        try:
            payment = claim_codes.redeem(session, code, g.identity_id)
        except ClaimError as err:
            raise ApiError(err.status, err.code, str(err)) from err
        app = session.get(App, payment.app_id)
        from ..stripe_events import _push

        _push(session, app, type="payment.claimed", identity_id=g.identity_id, email=payment.email, payment=payment)
        body = {"payment": serialize_payment(payment, app.slug)}
    return jsonify(body)


@bp.post("/portal")
@require_session
@require_feature("subscriptions")
def portal():
    data = json_body()
    return_url = safe_return_to(data.get("return_to") if isinstance(data.get("return_to"), str) else None)
    with session_scope() as session:
        customer = ensure_customer(session, g.identity)
        if not customer.stripe_customer_id:
            raise ApiError(404, "no_customer", "No billing profile yet.")
        params = {"customer": customer.stripe_customer_id, "return_url": return_url}
        if config.stripe_portal_configuration:
            params["configuration"] = config.stripe_portal_configuration
        try:
            portal_session = as_dict(client().v1.billing_portal.sessions.create(params=params))
        except Exception as err:
            raise ApiError(502, "stripe_error", "Could not open the billing portal.") from err
    return jsonify({"url": portal_session["url"]})


@bp.get("/entitlements")
@require_session
def entitlements():
    slug = (request.args.get("app") or "").strip().lower()
    with session_scope() as session:
        app = session.scalar(select(App).where(App.slug == slug)) if slug else None
        if app is None:
            raise ApiError(400, "unknown_app", "Unknown app.")
        body = entitlements_for(session, g.identity_id, app)
    resp = jsonify(body)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.get("/me/customer")
@require_session
def get_customer():
    """Small helper used by the pages to read the mirror without the history."""
    with session_scope() as session:
        customer = session.get(Customer, g.identity_id) or ensure_customer(session, g.identity)
        body = {"customer": serialize_customer(customer)}
    return jsonify(body)
