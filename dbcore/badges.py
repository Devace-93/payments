"""Supporter badges: tier computation and a flat shields-style SVG.

Tiers (highest wins): ``team`` > ``pro`` > ``supporter`` > ``none``. An
active subscription whose entitlement is ``team`` or ``pro`` sets that tier;
any paid, non-refunded payment or any other active subscription makes a
``supporter``. The rendered SVG is 20 px high, label "3m4", amber for every
real tier and grey for "not a supporter".
"""
from __future__ import annotations

import hashlib
import uuid
from html import escape

from sqlalchemy import select

from .entitlements import is_entitled
from .models import Customer, Payment, Subscription

TIERS = ("none", "supporter", "pro", "team")
AMBER = "f59e0b"
GREY = "9f9f9f"
LABEL = "3m4"
MESSAGES = {"none": "not a supporter", "supporter": "supporter", "pro": "pro", "team": "team"}


def tier_for(session, identity_id: uuid.UUID | None) -> str:
    """Highest tier the identity qualifies for (``none`` for unknown ids)."""
    if identity_id is None:
        return "none"
    best = 0
    subs = session.scalars(select(Subscription).where(Subscription.identity_id == identity_id)).all()
    for sub in subs:
        if not is_entitled(sub):
            continue
        ent = (sub.entitlement or "").lower()
        rank = TIERS.index(ent) if ent in ("pro", "team") else 1
        best = max(best, rank)
    if best == 0:
        paid = session.scalar(
            select(Payment.id)
            .where(Payment.identity_id == identity_id, Payment.status.in_(("paid", "partially_refunded")))
            .limit(1)
        )
        if paid is not None:
            best = 1
    return TIERS[best]


def resolve_identity(session, *, handle: str | None = None, identity_id: str | None = None) -> uuid.UUID | None:
    """The identity behind a badge URL, or None when unknown."""
    if identity_id:
        try:
            uid = uuid.UUID(identity_id)
        except ValueError:
            return None
        return uid if session.get(Customer, uid) is not None else None
    if handle:
        row = session.scalar(select(Customer.identity_id).where(Customer.handle == handle.lower()))
        return row
    return None


def color(tier: str) -> str:
    return GREY if tier == "none" else AMBER


def shields_json(tier: str) -> dict:
    """shields.io endpoint schema (https://shields.io/badges/endpoint-badge)."""
    return {"schemaVersion": 1, "label": LABEL, "message": MESSAGES[tier], "color": color(tier)}


def _text_width(text: str) -> int:
    """Approximate Verdana 11px width (shields uses 110 px font units / 10)."""
    return int(round(len(text) * 6.6 + 10))


def svg(tier: str) -> str:
    """Flat 20 px badge: grey label block + coloured message block."""
    message = MESSAGES[tier]
    left = _text_width(LABEL)
    right = _text_width(message)
    width = left + right
    fill = f"#{color(tier)}"
    label_x = left * 5
    msg_x = left * 10 + right * 5
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="20" role="img" '
        f'aria-label="{escape(LABEL)}: {escape(message)}">'
        f"<title>{escape(LABEL)}: {escape(message)}</title>"
        f'<clipPath id="r"><rect width="{width}" height="20" rx="3" fill="#fff"/></clipPath>'
        f'<g clip-path="url(#r)"><rect width="{left}" height="20" fill="#555"/>'
        f'<rect x="{left}" width="{right}" height="20" fill="{fill}"/></g>'
        f'<g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" '
        f'text-rendering="geometricPrecision" font-size="110">'
        f'<text x="{label_x}" y="140" transform="scale(.1)" fill="#fff" textLength="{(left - 10) * 10}">{escape(LABEL)}</text>'
        f'<text x="{msg_x}" y="140" transform="scale(.1)" fill="#fff" textLength="{(right - 10) * 10}">{escape(message)}</text>'
        f"</g></svg>"
    )


def etag(tier: str, kind: str) -> str:
    return '"' + hashlib.sha1(f"{kind}:{tier}".encode()).hexdigest()[:16] + '"'
