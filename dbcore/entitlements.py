"""Entitlements derived from the ``subscriptions`` mirror.

A subscription grants its ``entitlement`` while Stripe's ``status`` is
``active``, ``trialing`` or ``past_due``; ``cancel_at_period_end`` keeps the
grant until ``current_period_end``. ``entitlements_for`` is what the session
endpoint, the service endpoint and every push webhook return, so receivers
always see the full current set.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from .models import App, Subscription

ENTITLED_STATUSES = ("active", "trialing", "past_due")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def iso(dt: datetime | None) -> str | None:
    dt = _aware(dt)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def is_entitled(sub: Subscription, now: datetime | None = None) -> bool:
    """True while the subscription grants its entitlement."""
    # ``cancel_at_period_end`` keeps Stripe's status ``active`` until the period
    # ends, so it is covered by ENTITLED_STATUSES. A ``canceled`` status means
    # the subscription has ended (immediate cancel or period over): no grant,
    # whatever ``current_period_end`` still says.
    return sub.status in ENTITLED_STATUSES


def serialize_subscription(sub: Subscription | None, *, label: str | None = None) -> dict | None:
    if sub is None:
        return None
    out = {
        "id": str(sub.id),
        "entitlement": sub.entitlement,
        "status": sub.status,
        "current_period_end": iso(sub.current_period_end),
        "cancel_at_period_end": bool(sub.cancel_at_period_end),
    }
    if label is not None:
        out["label"] = label
    return out


def entitlements_for(session, identity_id: uuid.UUID, app: App | str) -> dict:
    """``{app, entitlements, subscription, updated_at}`` for (identity, app).

    ``subscription`` is the most relevant row (an entitled one first, then the
    latest), serialised with status / period end / cancel flag.
    """
    if isinstance(app, str):
        app_row = session.scalar(select(App).where(App.slug == app))
        slug = app
        app_id = app_row.id if app_row else None
    else:
        app_row, slug, app_id = app, app.slug, app.id
    subs: list[Subscription] = []
    if app_id is not None:
        subs = session.scalars(
            select(Subscription)
            .where(Subscription.identity_id == identity_id, Subscription.app_id == app_id)
            .order_by(Subscription.updated_at.desc())
        ).all()
    now = _now()
    entitled = [s for s in subs if is_entitled(s, now)]
    names = sorted({s.entitlement for s in entitled if s.entitlement})
    chosen = entitled[0] if entitled else (subs[0] if subs else None)
    updated = max((s.updated_at for s in subs if s.updated_at), default=None)
    return {
        "app": slug,
        "entitlements": names,
        "subscription": serialize_subscription(chosen),
        "updated_at": iso(updated or now),
    }


def active_subscription(session, identity_id: uuid.UUID, app_id: uuid.UUID) -> Subscription | None:
    """The entitled subscription of (identity, app), if any (409 guard)."""
    subs = session.scalars(
        select(Subscription).where(Subscription.identity_id == identity_id, Subscription.app_id == app_id)
    ).all()
    now = _now()
    for sub in subs:
        if is_entitled(sub, now):
            return sub
    return None
