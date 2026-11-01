"""m4session — verify 3m4 accounts sessions in any Python app.

Zero framework dependency (PyJWT with the ``cryptography`` extra, and
``requests``). Drop this file into your project (or vendor it under
``dbcore/``) and:

    from m4session import verify, SessionError, flask_require_session, require_verified

    # 1. Anywhere: verify a token you got from the `3m4_session` cookie or a
    #    bearer header. Returns the claims (sub, sid, email, email_verified,
    #    handle, name, avatar_url, iat, exp) or raises SessionError(code).
    claims = verify(token, jwks_url="https://accounts.3m4.net/.well-known/jwks.json",
                    issuer="https://accounts.3m4.net", audience="3m4")

    # 2. Flask: a decorator that reads the cookie / bearer, verifies, and puts
    #    the claims on ``g.identity``. Plug your own error type with on_error.
    require_session = flask_require_session(
        accounts_url="https://accounts.3m4.net",
        on_error=lambda status, code, message: ApiError(status, code, message),
    )

    @app.get("/api/me")
    @require_session
    def me():
        return {"user_id": g.identity["sub"]}

    # 3. Routes that need a verified e-mail (403 email_unverified otherwise):
    @app.post("/api/things")
    @require_session
    @require_verified(on_error=...)
    def create_thing(): ...

Error codes: ``no_session`` (nothing presented), ``session_expired`` (the JWT
is past ``exp``: the browser should call ``POST {accounts}/api/session/refresh``
with credentials and retry once), ``invalid_session`` (bad signature, wrong
issuer/audience, unknown key).

The JWKS is cached for ``cache_ttl`` seconds (600) and refetched once when a
token names an unknown ``kid`` (key rotation). Fetch failures keep serving the
cached keys. Keep your clock within a minute of UTC (``leeway=60``).
"""
from __future__ import annotations

import threading
import time
from functools import wraps
from typing import Any, Callable

import jwt
import requests

__all__ = ["SessionError", "verify", "flask_require_session", "require_verified", "COOKIE_NAME"]

COOKIE_NAME = "3m4_session"
ALGORITHMS = ["EdDSA"]
LEEWAY_SECONDS = 60


class SessionError(Exception):
    """``code`` is ``no_session`` / ``session_expired`` / ``invalid_session``."""

    def __init__(self, code: str, message: str | None = None):
        super().__init__(message or code)
        self.code = code
        self.status = 401


class _JwksCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._keys: dict[str, dict[str, Any]] = {}  # jwks_url -> {"fetched": ts, "keys": {kid: key}}

    def get(self, jwks_url: str, kid: str | None, cache_ttl: int):
        with self._lock:
            entry = self._keys.get(jwks_url)
            stale = entry is None or time.time() - entry["fetched"] > cache_ttl
            if stale or (kid and kid not in entry["keys"] and time.time() - entry["fetched"] > 5):
                try:
                    data = requests.get(jwks_url, timeout=5).json()
                    keys = {}
                    for jwk in data.get("keys", []):
                        try:
                            keys[jwk.get("kid")] = jwt.PyJWK(jwk).key
                        except Exception:
                            continue
                    entry = {"fetched": time.time(), "keys": keys}
                    self._keys[jwks_url] = entry
                except Exception:
                    if entry is None:
                        raise
            return entry["keys"].get(kid)


_cache = _JwksCache()


def verify(token: str, *, jwks_url: str, issuer: str, audience: str = "3m4", cache_ttl: int = 600) -> dict:
    """Verify a 3m4 session JWT and return its claims."""
    if not token:
        raise SessionError("no_session", "Not signed in.")
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as err:
        raise SessionError("invalid_session", "Invalid session.") from err
    try:
        key = _cache.get(jwks_url, header.get("kid"), cache_ttl)
    except Exception as err:
        raise SessionError("invalid_session", "Could not fetch the signing keys.") from err
    if key is None:
        raise SessionError("invalid_session", "Unknown signing key.")
    try:
        return jwt.decode(
            token,
            key,
            algorithms=ALGORITHMS,
            audience=audience,
            issuer=issuer.rstrip("/"),
            leeway=LEEWAY_SECONDS,
            options={"require": ["sub", "sid", "exp", "iat"]},
        )
    except jwt.ExpiredSignatureError as err:
        raise SessionError("session_expired", "Session expired.") from err
    except jwt.PyJWTError as err:
        raise SessionError("invalid_session", "Invalid session.") from err


def _token_from_flask_request(request) -> str | None:
    # An explicit bearer header wins over the ambient cookie, so a client that
    # holds a cookie for one identity can still act as another on purpose.
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        bearer = header[len("Bearer ") :].strip()
        if bearer:
            return bearer
    return request.cookies.get(COOKIE_NAME) or None


def _default_on_error(status: int, code: str, message: str) -> Exception:
    err = SessionError(code, message)
    err.status = status
    return err


def flask_require_session(
    accounts_url: str,
    *,
    audience: str = "3m4",
    on_error: Callable[[int, str, str], Exception] = _default_on_error,
    cache_ttl: int = 600,
):
    """Build a Flask decorator that verifies the session and sets ``g.identity``.

    ``on_error(status, code, message)`` must return the exception your app's
    error handler turns into ``{"error": {...}}``.
    """
    from flask import g, request

    accounts_url = accounts_url.rstrip("/")
    jwks_url = f"{accounts_url}/.well-known/jwks.json"

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            token = _token_from_flask_request(request)
            if not token:
                raise on_error(401, "no_session", "Not signed in.")
            try:
                g.identity = verify(token, jwks_url=jwks_url, issuer=accounts_url, audience=audience, cache_ttl=cache_ttl)
            except SessionError as err:
                raise on_error(401, err.code, str(err)) from err
            return view(*args, **kwargs)

        return wrapper

    return decorator


def require_verified(*, on_error: Callable[[int, str, str], Exception] = _default_on_error):
    """Place below ``require_session``: 403 ``email_unverified`` until the
    user confirms their e-mail."""
    from flask import g

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            identity = getattr(g, "identity", None)
            if not identity or not identity.get("email_verified"):
                raise on_error(403, "email_unverified", "Verify your e-mail address to continue.")
            return view(*args, **kwargs)

        return wrapper

    return decorator
