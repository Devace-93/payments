"""Flask extensions instantiated once and wired up in the app factory.

The rate limiter (Flask-Limiter, Redis-backed; ``memory://`` under tests via
``RATE_LIMIT_STORAGE_URI``, or disabled with ``RATE_LIMITS_ENABLED=false``)
and its key functions. Limits are evaluated before the view runs, so the
identity bucket reads the JWT ``sub`` *without* verifying it: it only picks
a bucket, the view still verifies the token.
"""
from __future__ import annotations

from flask import request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from dbcore.config import config
from dbcore.m4session import COOKIE_NAME


def client_ip() -> str:
    """First hop of ``X-Forwarded-For`` (Caddy sets it) or the socket address."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address()


def _presented_session_token() -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer ") and not header[7:].strip().startswith("m4pay_sk_"):
        return header[7:].strip() or None
    return request.cookies.get(COOKIE_NAME) or None


def identity_key() -> str:
    """Rate-limit bucket by the session's ``sub`` (falls back to the IP)."""
    token = _presented_session_token()
    if token:
        try:
            import jwt

            sub = jwt.decode(token, options={"verify_signature": False}).get("sub")
            if sub:
                return f"identity:{sub}"
        except Exception:
            pass
    return client_ip()


limiter = Limiter(
    key_func=client_ip,
    default_limits=[config.rate_limit_default],
    storage_uri=config.rate_limit_storage_uri,
    strategy="fixed-window",
    enabled=config.rate_limits_enabled,
)
