"""Transactional outbox: queue a side effect inside the caller's transaction.

The API and the webhook handlers call :func:`enqueue_mail` /
:func:`enqueue_webhook` from inside ``session_scope``; the row commits
together with the payment / subscription it belongs to, so a crash between
the business write and the side effect is impossible. ``dbcore.worker``
delivers later.

Webhook payloads carry the destination app only by ``app_id``: the URL and
the signing secret are read from ``apps`` at send time, so rotating them
with ``cli app-key`` applies to queued jobs too and no secret sits in the
queue.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from .models import App, Outbox


def enqueue_mail(session, *, template: str, to: str, lang: str = "en", params: dict | None = None,
                 app_id: uuid.UUID | None = None) -> Outbox:
    job = Outbox(
        kind="email",
        app_id=app_id,
        payload={"template": template, "to": to, "lang": lang or "en", "params": dict(params or {})},
    )
    session.add(job)
    return job


def enqueue_webhook(session, *, app: App, event: dict) -> Outbox | None:
    """Queue a push event for ``app`` (CONTRACT.md §6). ``event`` must carry
    ``type``, ``identity_id``, ``email`` and ``data``; ``id``, ``created`` and
    ``app`` are filled in here. No-op when the app has no webhook URL."""
    if not app.webhook_url:
        return None
    body = {
        "id": str(uuid.uuid4()),
        "type": event["type"],
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "app": app.slug,
        "identity_id": event.get("identity_id"),
        "email": event.get("email"),
        "data": event.get("data") or {},
    }
    job = Outbox(kind="webhook", app_id=app.id, payload={"app": app.slug, "event": body})
    session.add(job)
    return job
