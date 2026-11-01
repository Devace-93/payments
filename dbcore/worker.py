"""Outbox worker: delivers the mails the API queued.

    python -m dbcore.worker          # loop forever (compose `worker` service)
    python -m dbcore.worker --once   # drain every due job, then exit (tests)

Claiming is ``SELECT … FOR UPDATE SKIP LOCKED`` on one due row, so several
workers can run side by side without double delivery. A job is processed
outside the claiming transaction (SMTP must not hold a row lock); its outcome
is written in a second short transaction.

Retry policy: exponential backoff 1 min → 2 min → 4 min … capped at 2 h, at
most 8 attempts, then ``failed`` (kept 7 days with the last error, like
``sent`` rows, for inspection). Reduced from retro's worker to one job kind.
"""
from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, text

from . import models  # noqa: F401  (register models)
from .config import config
from .db import session_scope
from .mail import MailError, is_enabled as mail_is_enabled, send as send_mail
from .mail_templates import render
from .models import Outbox

log = logging.getLogger("accounts.worker")

MAX_ATTEMPTS = 8
BACKOFF_BASE_SECONDS = 60
BACKOFF_CAP_SECONDS = 2 * 60 * 60
RETENTION_DAYS = 7


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
        return {"id": job.id, "kind": job.kind, "payload": dict(job.payload or {}), "attempts": job.attempts}


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


def process_email(job: dict) -> str:
    payload = job["payload"]
    to = payload.get("to")
    template = payload.get("template")
    if not to or not template:
        return "skipped"
    if not mail_is_enabled():
        return "skipped"
    subject, text_body, html_body = render(
        template,
        lang=payload.get("lang") or "en",
        to=to,
        name=payload.get("name"),
        token=payload.get("token"),
        return_to=payload.get("return_to"),
    )
    try:
        return send_mail(to=[to], subject=subject, text=text_body, html=html_body)
    except MailError as err:
        raise JobFailed(str(err)) from err


def process(job: dict) -> str:
    if job["kind"] == "email":
        return process_email(job)
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
    log.info("accounts outbox worker starting (mail %s, poll %.0fs)", "on" if mail_is_enabled() else "off", config.worker_poll_seconds)
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
