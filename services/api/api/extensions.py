"""Flask extensions instantiated once and wired up in the app factory.

The rate limiter (Flask-Limiter, Redis-backed; ``memory://`` under tests via
``RATE_LIMIT_STORAGE_URI``, or disabled with ``RATE_LIMITS_ENABLED=false``)
and the Authlib OAuth registry.
"""
from __future__ import annotations

from authlib.integrations.flask_client import OAuth
from flask import request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from dbcore.config import config


def client_ip() -> str:
    """First hop of ``X-Forwarded-For`` (Caddy sets it) or the socket address."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address()


def email_key() -> str:
    """Rate-limit bucket by the e-mail in the JSON body (magic links)."""
    data = request.get_json(silent=True) or {}
    email = data.get("email") if isinstance(data, dict) else None
    return f"email:{str(email).strip().lower()}" if email else client_ip()


def user_key() -> str:
    """Rate-limit bucket by the signed-in user (falls back to the IP)."""
    from flask import g

    user = getattr(g, "user", None)
    return f"user:{user.id}" if user is not None else client_ip()


limiter = Limiter(
    key_func=client_ip,
    default_limits=[config.rate_limit_default],
    storage_uri=config.rate_limit_storage_uri,
    strategy="fixed-window",
    enabled=config.rate_limits_enabled,
)

oauth = OAuth()
