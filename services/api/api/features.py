"""Enforcement of payments' own feature switches in the API.

``@require_feature("key")`` rejects requests when a switch is OFF for the
requester. Backend enforcement is the source of truth — the frontend only
mirrors these switches (``GET /api/features``). The Stripe webhook and every
entitlement read are never gated.
"""
from __future__ import annotations

from functools import wraps

from flask import Blueprint, g, jsonify

from dbcore.feature_flags import is_enabled, resolve_all

from .errors import ApiError


def distinct_id() -> str:
    identity = getattr(g, "identity", None)
    return str(identity.get("sub")) if identity else "anonymous"


def require_feature(key: str, status: int = 403, code: str = "feature_disabled"):
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            check_feature(key, status=status, code=code)
            return view(*args, **kwargs)

        return wrapper

    return decorator


def check_feature(key: str, status: int = 403, code: str = "feature_disabled") -> None:
    if not is_enabled(key, distinct_id()):
        raise ApiError(status, code, f"'{key}' is not available.")


bp = Blueprint("features", __name__)


@bp.get("")
def features():
    """Resolved switches for the requester. Public: the pages need them
    before any session exists; a valid session upgrades resolution to the
    user's targeting bucket, but a bad/expired one is simply ignored."""
    from .auth import optional_session

    optional_session()
    resp = jsonify({"features": resolve_all(distinct_id())})
    resp.headers["Cache-Control"] = "no-store"
    return resp
