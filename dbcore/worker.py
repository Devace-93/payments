"""Outbox worker: delivers the mails and app webhooks the API queued.

    python -m dbcore.worker          # loop forever (compose `worker` service)
    python -m dbcore.worker --once   # drain every due job, then exit (tests)

Claiming is ``SELECT … FOR UPDATE SKIP LOCKED`` on one due row, so several
workers can run side by side without double delivery. A job is processed
outside the claiming transaction (SMTP / HTTP must not hold a row lock); its
outcome is written in a second short transaction.

Retry policy: exponential backoff 1 min → 2 min → 4 min … capped at 2 h, at
most 8 attempts, then ``failed`` (kept 7 days with the last error, like
``sent`` rows, for inspection).

Webhooks are signed per CONTRACT.md §6: ``X-M4Pay-Signature: v1=<hex
hmac_sha256(secret, f"{timestamp}.{body}")>``; :func:`sign` is the reference
signer the relying-party package round-trips against.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
from sqlalchemy import delete, select, text

from . import models  # noqa: F401  (register models)
from .config import config
from .db import session_scope
from .mail import MailError
from .mail import is_enabled as mail_is_enabled
from .mail import send as send_mail
from .mail_templates import render
from .models import App, Outbox

log = logging.getLogger("payments.worker")

MAX_ATTEMPTS = 8
BACKOFF_BASE_SECONDS = 60
BACKOFF_CAP_SECONDS = 2 * 60 * 60
RETENTION_DAYS = 7
WEBHOOK_TIMEOUT_SECONDS = 10


class JobFailed(Exception):
    """Transient failure: retry later (unless attempts are exhausted)."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(BACKOFF_BASE_SECONDS * (2 ** max(attempts - 1, 0)), BACKOFF_CAP_SECONDS))


def claim_one() -> dict | None:
    """Mark one due job ``sending`` and return a detached copy of it."""
    with session_scope() as session:
        job = session.scalar(
            select(Outbox)
            .where(Outbox.status == "pending", Outbox.next_attempt_at <= _now())
            .order_by(Outbox.next_attempt_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if job is None:
            return None
        job.status = "sending"
        job.attempts = (job.attempts or 0) + 1
        session.flush()
        return {
            "id": job.id,
            "kind": job.kind,
            "app_id": job.app_id,
            "payload": dict(job.payload or {}),
            "attempts": job.attempts,
        }


def finish(job_id, *, status: str, error_text: str | None = None, attempts: int = 0) -> None:
    with session_scope() as session:
        job = session.get(Outbox, job_id)
        if job is None:
            return
        job.status = status
        job.last_error = (error_text or None) and error_text[:500]
        if status in ("sent", "skipped"):
            job.sent_at = _now()
        elif status == "pending":
            job.next_attempt_at = _now() + backoff(attempts)


# --------------------------------------------------------------------------- #
# email
# --------------------------------------------------------------------------- #
def process_email(job: dict) -> str:
    payload = job["payload"]
    to = payload.get("to")
    template = payload.get("template")
    if not to or not template:
        return "skipped"
    if not mail_is_enabled():
        return "skipped"
    subject, text_body, html_body = render(template, lang=payload.get("lang") or "en", to=to, params=payload.get("params") or {})
    try:
        return send_mail(to=[to], subject=subject, text=text_body, html=html_body)
    except MailError as err:
        raise JobFailed(str(err)) from err


# --------------------------------------------------------------------------- #
# webhook
# --------------------------------------------------------------------------- #
def encode_body(event: dict) -> bytes:
    """Canonical JSON bytes of the event (what gets signed and sent)."""
    return json.dumps(event, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode()


def sign(secret: str, timestamp: int, body: bytes) -> str:
    """``v1=<hex hmac_sha256(secret, f"{timestamp}.{body}")>``."""
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"v1={mac}"


def webhook_headers(secret: str, event_id: str, body: bytes, timestamp: int | None = None) -> dict[str, str]:
    ts = int(time.time()) if timestamp is None else timestamp
    return {
        "Content-Type": "application/json",
        "X-M4Pay-Event-Id": event_id,
        "X-M4Pay-Timestamp": str(ts),
        "X-M4Pay-Signature": sign(secret, ts, body),
        "User-Agent": "m4pay-webhook/1",
    }


def _webhook_target(app_id) -> tuple[str | None, str | None]:
    with session_scope() as session:
        app = session.get(App, app_id) if app_id else None
        if app is None:
            return None, None
        return app.webhook_url, app.webhook_secret


def process_webhook(job: dict) -> str:
    event = (job["payload"] or {}).get("event") or {}
    if not event.get("id"):
        return "skipped"
    url, secret = _webhook_target(job.get("app_id"))
    if not url or not secret:
        log.info("webhook %s skipped: app has no webhook_url/secret", event.get("id"))
        return "skipped"
    body = encode_body(event)
    headers = webhook_headers(secret, event["id"], body)
    try:
        resp = requests.post(url, data=body, headers=headers, timeout=WEBHOOK_TIMEOUT_SECONDS)
    except requests.RequestException as err:
        raise JobFailed(f"{type(err).__name__}: {err}") from err
    if not 200 <= resp.status_code < 300:
        raise JobFailed(f"HTTP {resp.status_code}: {resp.text[:200]}")
    return "sent"


# --------------------------------------------------------------------------- #
# loop
# --------------------------------------------------------------------------- #
def process(job: dict) -> str:
    if job["kind"] == "email":
        return process_email(job)
    if job["kind"] == "webhook":
        return process_webhook(job)
    return "skipped"


def run_job(job: dict) -> str:
    try:
        result = process(job)
    except JobFailed as err:
        if job["attempts"] >= MAX_ATTEMPTS:
            log.error("job %s failed permanently after %d attempts: %s", job["id"], job["attempts"], err)
            finish(job["id"], status="failed", error_text=str(err), attempts=job["attempts"])
            return "failed"
        log.warning("job %s attempt %d failed, retrying: %s", job["id"], job["attempts"], err)
        finish(job["id"], status="pending", error_text=str(err), attempts=job["attempts"])
        return "retry"
    except Exception as err:  # pragma: no cover - programming error: do not retry forever
        log.exception("job %s crashed", job["id"])
        finish(job["id"], status="failed", error_text=f"{type(err).__name__}: {err}", attempts=job["attempts"])
        return "failed"
    finish(job["id"], status=result, attempts=job["attempts"])
    return result


def cleanup() -> int:
    """Drop sent/skipped/failed rows older than the retention window and
    release jobs stuck in ``sending`` for over an hour."""
    cutoff = _now() - timedelta(days=RETENTION_DAYS)
    with session_scope() as session:
        result = session.execute(
            delete(Outbox).where(Outbox.status.in_(("sent", "skipped", "failed")), Outbox.created_at < cutoff)
        )
        session.execute(
            text(
                "UPDATE outbox SET status = 'pending', next_attempt_at = now() "
                "WHERE status = 'sending' AND next_attempt_at < now() - interval '1 hour'"
            )
        )
        return result.rowcount or 0


def drain(limit: int = 1000) -> dict:
    """Process every due job once (used by ``--once`` and tests)."""
    counts: dict[str, int] = {}
    for _ in range(limit):
        job = claim_one()
        if job is None:
            break
        outcome = run_job(job)
        counts[outcome] = counts.get(outcome, 0) + 1
    return counts


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    once = "--once" in argv
    log.info("payments outbox worker starting (mail %s, poll %.0fs)", "on" if mail_is_enabled() else "off", config.worker_poll_seconds)
    if once:
        counts = drain()
        log.info("drained: %s", counts or "nothing due")
        return 0
    last_cleanup = 0.0
    while True:
        try:
            counts = drain(limit=100)
            if counts:
                log.info("processed: %s", counts)
            if time.time() - last_cleanup > 3600:
                cleanup()
                last_cleanup = time.time()
        except Exception:  # pragma: no cover - keep the loop alive
            log.exception("worker loop error")
        time.sleep(config.worker_poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
