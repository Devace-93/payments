"""Authentication helpers.

Two ways to authenticate against this API:

1. **Session** — the accounts.3m4.net JWT in the ``3m4_session`` cookie or,
   for non-browser clients, as ``Authorization: Bearer``. Verified locally
   against the accounts JWKS (``dbcore.m4session``); the bearer header beats
   the cookie. Identity is *only* what the claims say: there is no local
   users table, ``customers.identity_id`` is the JWT ``sub``.
2. **Service key** — ``Authorization: Bearer m4pay_sk_…`` of a relying app,
   matched by sha256 against ``apps.service_key_hash``. The app may only act
   on its own slug (checked in the views).

``require_session`` / ``optional_session`` / ``require_service_key`` put the
resolved identity on ``flask.g``; :func:`ensure_customer` upserts the
``customers`` mirror from the claims inside the caller's transaction.
"""
from __future__ import annotations

import hashlib
import uuid
from functools import wraps

from flask import g, request
from sqlalchemy import select

from dbcore.config import config
from dbcore.m4session import COOKIE_NAME, SessionError, verify
from dbcore.models import App, Customer

from .errors import ApiError

SERVICE_KEY_PREFIX = "m4pay_sk_"
JWKS_URL = f"{config.accounts_internal_url}/.well-known/jwks.json"


def _bearer_token() -> str:
    header = request.headers.get("Authorization", "")
    return header[len("Bearer ") :].strip() if header.startswith("Bearer ") else ""


def session_token() -> str | None:
    """An explicit bearer (that is not a service key) wins over the cookie."""
    bearer = _bearer_token()
    if bearer and not bearer.startswith(SERVICE_KEY_PREFIX):
        return bearer
    return request.cookies.get(COOKIE_NAME) or None


def verify_session(token: str) -> dict:
    """Verify an accounts JWT; raises :class:`ApiError` 401 with the contract codes."""
    try:
        return verify(token, jwks_url=JWKS_URL, issuer=config.accounts_url, audience=config.jwt_audience)
    except SessionError as err:
        raise ApiError(401, err.code, str(err)) from err


def _set_identity(claims: dict | None) -> None:
    g.identity = claims
    g.identity_id = uuid.UUID(claims["sub"]) if claims else None


def require_session(view):
    """401 ``no_session`` / ``session_expired`` / ``invalid_session``; sets
    ``g.identity`` (claims) and ``g.identity_id`` (uuid)."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        token = session_token()
        if not token:
            raise ApiError(401, "no_session", "Not signed in.")
        claims = verify_session(token)
        try:
            _set_identity(claims)
        except ValueError as err:
            raise ApiError(401, "invalid_session", "Invalid session.") from err
        return view(*args, **kwargs)

    return wrapper


def optional_session() -> dict | None:
    """Resolve the session if one is presented. A missing token is simply no
    identity; an expired or invalid one is ignored too, but remembered in
    ``g.session_error`` so a view that *needs* a session can answer
    ``session_expired`` (the client refreshes and retries) instead of
    ``no_session``."""
    g.session_error = None
    token = session_token()
    if not token:
        _set_identity(None)
        return None
    try:
        claims = verify(token, jwks_url=JWKS_URL, issuer=config.accounts_url, audience=config.jwt_audience)
        _set_identity(claims)
        return claims
    except (SessionError, ValueError) as err:
        g.session_error = getattr(err, "code", "invalid_session")
        _set_identity(None)
        return None


def hash_service_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def require_service_key(view):
    """401 ``unauthorized`` unless a valid ``m4pay_sk_`` bearer is presented;
    sets ``g.app`` (detached ``App``) and clears any session identity."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        bearer = _bearer_token()
        if not bearer.startswith(SERVICE_KEY_PREFIX):
            raise ApiError(401, "unauthorized", "Missing or invalid service key.")
        key_hash = hash_service_key(bearer)
        from dbcore.db import SessionLocal

        with SessionLocal() as session:
            app = session.scalar(select(App).where(App.service_key_hash == key_hash, App.active.is_(True)))
            if app is None:
                raise ApiError(401, "unauthorized", "Missing or invalid service key.")
            session.expunge(app)
        g.app = app
        _set_identity(None)
        return view(*args, **kwargs)

    return wrapper


def ensure_customer(session, claims: dict) -> Customer:
    """Upsert the ``customers`` mirror for the claims' ``sub``."""
    identity_id = uuid.UUID(claims["sub"])
    customer = session.get(Customer, identity_id)
    if customer is None:
        customer = Customer(identity_id=identity_id)
        session.add(customer)
    email = claims.get("email")
    if email:
        customer.email = email.lower()
    handle = claims.get("handle")
    if handle:
        customer.handle = handle.lower()
    if claims.get("name") is not None:
        customer.name = claims.get("name")
    currency = (claims.get("currency") or "").lower()
    if currency in config.currencies:
        customer.preferred_currency = currency
    session.flush()
    return customer
