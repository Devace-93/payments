"""``POST /api/stripe/webhook``: verify the signature, dedupe on the event id
(insert-first), then run the handler in ``api.stripe_events``.

Never rate-limited and never feature-gated. A handler failure answers 500 so
Stripe retries; the ``stripe_events`` row keeps ``status=error`` and the
retry is allowed through (only ``processed`` rows are duplicates).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError

from dbcore.config import config
from dbcore.db import session_scope
from dbcore.models import StripeEvent
from dbcore.stripe_client import as_dict, client, is_fake

from ..errors import ApiError
from ..extensions import limiter
from ..stripe_events import handle_event

log = logging.getLogger("payments.stripe")

bp = Blueprint("stripe_webhook", __name__)


def _construct_event() -> dict:
    """Verified event as a plain dict (signature per CONTRACT.md §5)."""
    import stripe

    payload = request.get_data()
    signature = request.headers.get("Stripe-Signature")
    secret = config.stripe_webhook_secret
    if not secret:
        if is_fake(client()):
            # Local/CI without a secret: accept the JSON as is (fake Stripe only).
            data = request.get_json(silent=True)
            if not isinstance(data, dict) or not data.get("id"):
                raise ApiError(400, "validation_error", "Malformed event.")
            return data
        raise ApiError(503, "webhook_not_configured", "STRIPE_WEBHOOK_SECRET is not set.")
    try:
        event = stripe.Webhook.construct_event(payload, signature, secret)
    except stripe.SignatureVerificationError as err:
        raise ApiError(400, "invalid_signature", "Bad Stripe signature.") from err
    except ValueError as err:
        raise ApiError(400, "validation_error", "Malformed event.") from err
    return as_dict(event)


@bp.post("/webhook")
@limiter.exempt
def webhook():
    event = _construct_event()
    event_id = event.get("id")
    event_type = event.get("type") or ""
    obj = (event.get("data") or {}).get("object") or {}
    created = event.get("created")

    # 1. insert-first dedupe in its own transaction
    try:
        with session_scope() as session:
            session.add(StripeEvent(id=event_id, type=event_type, stripe_created=created, status="received"))
    except IntegrityError:
        with session_scope() as session:
            existing = session.get(StripeEvent, event_id)
            if existing is None or existing.status != "error":
                return jsonify({"status": "duplicate"}), 200
            existing.status = "received"

    # 2. handle + mark
    try:
        with session_scope() as session:
            outcome = handle_event(session, client(), event_type, obj, event_created=created)
            row = session.get(StripeEvent, event_id)
            if row is not None:
                row.status = "ignored" if outcome == "ignored" else "processed"
                row.processed_at = datetime.now(timezone.utc)
    except Exception as err:
        log.exception("stripe event %s (%s) failed", event_id, event_type)
        with session_scope() as session:
            row = session.get(StripeEvent, event_id)
            if row is not None:
                row.status = "error"
                row.error = f"{type(err).__name__}: {err}"[:2000]
        return jsonify({"error": {"code": "handler_failed", "message": "Event handling failed; Stripe will retry."}}), 500
    return jsonify({"status": outcome}), 200
