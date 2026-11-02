"""``POST /api/github/sponsors``: the GitHub Sponsors ``sponsorship`` webhook
(CONTRACT.md §5). Verifies ``X-Hub-Signature-256`` (HMAC-SHA256 of the raw
body with ``GITHUB_WEBHOOK_SECRET``), dedupes on ``X-GitHub-Delivery``
(insert-first, like the Stripe webhook) and upserts ``github_sponsors`` by
login. ``ping`` answers 200; any other event is ignored with 200.

Actions: ``created`` → active row; ``cancelled`` → ``status=cancelled`` +
``ended_at``; ``edited`` / ``tier_changed`` / ``pending_cancellation`` /
``pending_tier_change`` → refresh the profile/tier/privacy (a pending
cancellation stays active until GitHub sends ``cancelled``). One-time tiers
set ``one_time=true`` and are never cancelled (they are donations).

Never rate-limited and never feature-gated. A handler failure answers 500 so
GitHub's redelivery can retry (the ``github_events`` row keeps
``status=error``; only ``processed``/``ignored`` rows count as duplicates).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from dbcore.config import config
from dbcore.db import session_scope
from dbcore.models import GithubEvent, GithubSponsor

from ..errors import ApiError
from ..extensions import limiter

log = logging.getLogger("payments.github")

bp = Blueprint("github_webhook", __name__)

PROFILE_ACTIONS = {"created", "edited", "tier_changed", "pending_cancellation", "pending_tier_change"}


def _verify() -> dict:
    secret = config.github_webhook_secret
    if not secret:
        raise ApiError(503, "webhook_not_configured", "GITHUB_WEBHOOK_SECRET is not set.")
    payload = request.get_data()
    signature = request.headers.get("X-Hub-Signature-256") or ""
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise ApiError(400, "invalid_signature", "Bad GitHub signature.")
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError(400, "validation_error", "Malformed payload.")
    return data


def _ts(value) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def apply_sponsorship(session, action: str, sponsorship: dict, *, event_at: datetime | None = None) -> str:
    """Upsert the ``github_sponsors`` row for ``sponsorship``; returns the outcome."""
    sponsor = sponsorship.get("sponsor") or {}
    login = (sponsor.get("login") or "").strip()
    if not login:
        return "ignored"
    tier = sponsorship.get("tier") or {}
    now = event_at or datetime.now(timezone.utc)
    row = session.scalar(select(GithubSponsor).where(GithubSponsor.login == login))
    if row is None:
        if action == "cancelled":
            return "ignored"  # never seen: nothing to cancel
        row = GithubSponsor(login=login, started_at=_ts(sponsorship.get("created_at")) or now)
        session.add(row)
    # Profile, tier and privacy always reflect the latest payload.
    row.node_id = sponsor.get("node_id") or row.node_id
    row.name = (sponsor.get("name") or None) if "name" in sponsor else row.name
    row.avatar_url = sponsor.get("avatar_url") or row.avatar_url
    row.html_url = sponsor.get("html_url") or row.html_url or f"https://github.com/{login}"
    if tier:
        row.tier_name = tier.get("name") or row.tier_name
        row.monthly_cents = int(tier.get("monthly_price_in_cents") or 0)
        row.one_time = bool(tier.get("is_one_time"))
    privacy = (sponsorship.get("privacy_level") or "public").lower()
    row.privacy_level = "private" if privacy == "private" else "public"
    row.last_event_at = now
    row.raw = {"action": action, "sponsorship": sponsorship}
    if action == "cancelled" and not row.one_time:
        row.status = "cancelled"
        row.ended_at = now
    elif action == "created" or row.status == "cancelled":
        # A returning sponsor (created again after a cancellation) is active again.
        row.status = "active"
        row.ended_at = None
        if action == "created":
            row.started_at = _ts(sponsorship.get("created_at")) or now
    return "processed"


@bp.post("/sponsors")
@limiter.exempt
def sponsors_webhook():
    data = _verify()
    event = (request.headers.get("X-GitHub-Event") or "").strip().lower()
    delivery = (request.headers.get("X-GitHub-Delivery") or "").strip()
    if event == "ping":
        return jsonify({"status": "pong"}), 200
    if event != "sponsorship":
        return jsonify({"status": "ignored", "event": event}), 200
    action = (data.get("action") or "").strip().lower()
    sponsorship = data.get("sponsorship") or {}
    if not delivery:
        raise ApiError(400, "validation_error", "Missing X-GitHub-Delivery.")

    # 1. insert-first dedupe in its own transaction
    try:
        with session_scope() as session:
            session.add(GithubEvent(id=delivery, event=event, action=action, status="received"))
    except IntegrityError:
        with session_scope() as session:
            existing = session.get(GithubEvent, delivery)
            if existing is None or existing.status != "error":
                return jsonify({"status": "duplicate"}), 200
            existing.status = "received"

    # 2. handle + mark
    try:
        with session_scope() as session:
            outcome = apply_sponsorship(session, action, sponsorship) if action in PROFILE_ACTIONS | {"cancelled"} else "ignored"
            row = session.get(GithubEvent, delivery)
            if row is not None:
                row.status = "ignored" if outcome == "ignored" else "processed"
    except Exception as err:  # noqa: BLE001 — answer 500 so GitHub can redeliver
        log.exception("github sponsorship %s failed", delivery)
        with session_scope() as session:
            row = session.get(GithubEvent, delivery)
            if row is not None:
                row.status = "error"
                row.error = str(err)[:2000]
        raise ApiError(500, "handler_error", "Sponsorship handling failed; GitHub may redeliver.") from err
    return jsonify({"status": outcome}), 200
