"""Enforcement of accounts' own feature switches in the API.

``@require_feature("key")`` rejects requests when a switch is OFF for the
requester. Backend enforcement is the source of truth — the frontend only
mirrors these switches (``GET /api/features``). Login and logout are never
gated.
"""
from __future__ import annotations

from functools import wraps

from flask import Blueprint, g, jsonify

from dbcore.feature_flags import is_enabled, resolve_all

from .errors import ApiError


def _distinct_id() -> str:
    user = getattr(g, "user", None)
    return str(user.id) if user is not None else "anonymous"


def require_feature(key: str, status: int = 403, code: str = "feature_disabled"):
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not is_enabled(key, _distinct_id()):
                raise ApiError(status, code, f"'{key}' is not available.")
            return view(*args, **kwargs)

        return wrapper

    return decorator


bp = Blueprint("features", __name__)


@bp.get("")
def features():
    """Resolved switches for the requester. Public: the signup page needs them
    before any session exists; a valid session upgrades resolution to the
    user's targeting bucket, but a bad/expired one is simply ignored."""
    from .auth_utils import optional_user

    optional_user()
    return jsonify({"features": resolve_all(_distinct_id())})
