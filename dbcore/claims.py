"""Claim codes (CONTRACT.md §9): attach a guest donation to an identity later.

A code is 16 Crockford-base32 characters (80 bits) displayed as
``XXXX-XXXX-XXXX-XXXX``. Only ``sha256(normalised)`` is stored. Normalising
uppercases, strips spaces and dashes and maps the Crockford ambiguities
(``I``/``L`` → ``1``, ``O`` → ``0``). Codes expire after
``CLAIM_CODE_TTL_DAYS``, are single-use (``UPDATE … WHERE used_at IS NULL``)
and are voided by refunds and disputes.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from .config import config
from .models import ClaimCode, Payment

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
CODE_LENGTH = 16
_TRANSLATE = str.maketrans({"I": "1", "L": "1", "O": "0"})


class ClaimError(Exception):
    """``code`` is ``invalid_code`` (400) / ``expired_code`` (410) / ``used_code`` (409)."""

    STATUS = {"invalid_code": 400, "expired_code": 410, "used_code": 409}

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.status = self.STATUS[code]


def generate() -> str:
    """A fresh code, formatted for display (``XXXX-XXXX-XXXX-XXXX``)."""
    raw = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
    return format_code(raw)


def format_code(raw: str) -> str:
    return "-".join(raw[i : i + 4] for i in range(0, CODE_LENGTH, 4))


def normalise(code: str) -> str | None:
    """Canonical 16-char form, or None when the input cannot be a code."""
    if not isinstance(code, str):
        return None
    cleaned = code.upper().replace(" ", "").replace("-", "").translate(_TRANSLATE)
    if len(cleaned) != CODE_LENGTH or any(ch not in ALPHABET for ch in cleaned):
        return None
    return cleaned


def hash_code(normalised: str) -> str:
    return hashlib.sha256(normalised.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def issue(session, payment: Payment) -> str:
    """Create the claim code for ``payment`` and return the display form.
    The plaintext exists only in the receipt mail payload."""
    code = generate()
    session.add(
        ClaimCode(
            code_hash=hash_code(normalise(code)),
            payment_id=payment.id,
            expires_at=_now() + timedelta(days=config.claim_code_ttl_days),
        )
    )
    session.flush()
    return code


def void(session, payment_id: uuid.UUID) -> None:
    """Make the payment's code unusable (refund / dispute). Idempotent."""
    session.execute(
        update(ClaimCode)
        .where(ClaimCode.payment_id == payment_id, ClaimCode.voided_at.is_(None))
        .values(voided_at=_now())
    )


def redeem(session, code: str, identity_id: uuid.UUID) -> Payment:
    """Attach the payment behind ``code`` to ``identity_id`` atomically.

    Raises :class:`ClaimError` with ``invalid_code`` (unknown or voided),
    ``expired_code`` or ``used_code``. The single-use guarantee is the
    conditional UPDATE, so two concurrent redeems cannot both win.
    """
    normalised = normalise(code)
    if normalised is None:
        raise ClaimError("invalid_code", "That code is not valid.")
    row = session.scalar(select(ClaimCode).where(ClaimCode.code_hash == hash_code(normalised)))
    if row is None or row.voided_at is not None:
        raise ClaimError("invalid_code", "That code is not valid.")
    if row.used_at is not None:
        raise ClaimError("used_code", "That code was already used.")
    now = _now()
    if row.expires_at <= now:
        raise ClaimError("expired_code", "That code has expired.")
    won = session.execute(
        update(ClaimCode)
        .where(ClaimCode.id == row.id, ClaimCode.used_at.is_(None))
        .values(used_at=now, used_by=identity_id)
    ).rowcount
    if not won:
        raise ClaimError("used_code", "That code was already used.")
    payment = session.get(Payment, row.payment_id)
    if payment is None:  # pragma: no cover - FK cascade makes this unreachable
        raise ClaimError("invalid_code", "That code is not valid.")
    payment.identity_id = identity_id
    payment.claimed_at = now
    session.flush()
    return payment
