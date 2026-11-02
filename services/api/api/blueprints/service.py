"""Service endpoints for app backends (``Authorization: Bearer m4pay_sk_…``):
the pull API behind ``m4pay.M4PayClient``. An app may only read its own slug
(403 ``forbidden`` otherwise). Never feature-gated."""
from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request
from sqlalchemy import and_, or_, select

from dbcore.db import session_scope
from dbcore.entitlements import entitlements_for, serialize_subscription
from dbcore.models import Customer, Product, Subscription

from ..auth import require_service_key
from ..errors import ApiError
from ..serializers import iso

bp = Blueprint("service", __name__)

PAGE_SIZE = 100


def _own_app() -> str:
    slug = (request.args.get("app") or "").strip().lower()
    if not slug:
        raise ApiError(400, "validation_error", "app is required.")
    if slug != g.app.slug:
        raise ApiError(403, "forbidden", "This key may only read its own app.")
    return slug


@bp.get("/entitlements/<identity_id>")
@require_service_key
def get_entitlements(identity_id: str):
    _own_app()
    try:
        uid = uuid.UUID(identity_id)
    except ValueError:
        raise ApiError(400, "validation_error", "identity_id must be a UUID.") from None
    with session_scope() as session:
        body = entitlements_for(session, uid, g.app)
    resp = jsonify(body)
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ApiError(400, "validation_error", "updated_since must be an ISO-8601 timestamp.") from None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _decode_cursor(raw: str | None) -> tuple[datetime, uuid.UUID] | None:
    if not raw:
        return None
    try:
        ts, uid = base64.urlsafe_b64decode(raw.encode()).decode().split("|", 1)
        return datetime.fromisoformat(ts), uuid.UUID(uid)
    except Exception:
        raise ApiError(400, "validation_error", "Bad cursor.") from None


def _encode_cursor(row: Subscription) -> str:
    return base64.urlsafe_b64encode(f"{row.updated_at.isoformat()}|{row.id}".encode()).decode()


@bp.get("/subscriptions")
@require_service_key
def list_subscriptions():
    _own_app()
    since = _parse_iso(request.args.get("updated_since"))
    cursor = _decode_cursor(request.args.get("cursor"))
    with session_scope() as session:
        query = select(Subscription).where(Subscription.app_id == g.app.id)
        if since is not None:
            query = query.where(Subscription.updated_at >= since)
        if cursor is not None:
            ts, uid = cursor
            query = query.where(
                or_(Subscription.updated_at > ts, and_(Subscription.updated_at == ts, Subscription.id > uid))
            )
        rows = session.scalars(query.order_by(Subscription.updated_at, Subscription.id).limit(PAGE_SIZE + 1)).all()
        has_more = len(rows) > PAGE_SIZE
        rows = rows[:PAGE_SIZE]
        customers = {
            c.identity_id: c
            for c in session.scalars(select(Customer).where(Customer.identity_id.in_({r.identity_id for r in rows} or {uuid.uuid4()}))).all()
        }
        labels = {
            p.id: p.label
            for p in session.scalars(select(Product).where(Product.id.in_({r.product_id for r in rows if r.product_id} or {uuid.uuid4()}))).all()
        }
        items = []
        for row in rows:
            ents = entitlements_for(session, row.identity_id, g.app)
            customer = customers.get(row.identity_id)
            item = serialize_subscription(row, label=labels.get(row.product_id))
            item.update(
                {
                    "app": g.app.slug,
                    "identity_id": str(row.identity_id),
                    "email": customer.email if customer else None,
                    "entitlements": ents["entitlements"],
                    "updated_at": iso(row.updated_at),
                }
            )
            items.append(item)
        body = {"items": items, "next_cursor": _encode_cursor(rows[-1]) if has_more and rows else None}
    resp = jsonify(body)
    resp.headers["Cache-Control"] = "no-store"
    return resp
