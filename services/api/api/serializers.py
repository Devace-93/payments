"""ORM rows → the JSON shapes in CONTRACT.md, plus the JSON-body reader that
enforces ``Content-Type: application/json`` on state-changing endpoints."""
from __future__ import annotations

from datetime import datetime, timezone

from flask import request

from dbcore.tokens import avatar_url

from .errors import ApiError


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def json_body() -> dict:
    """The request's JSON object. Non-JSON content types are a 415 (CSRF
    defence: HTML forms cannot send ``application/json``); an empty JSON
    body is ``{}``; a JSON value that is not an object is a 400."""
    if not request.is_json:
        raise ApiError(415, "unsupported_media_type", "Send a JSON body with Content-Type: application/json.")
    data = request.get_json(silent=True)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ApiError(400, "invalid_body", "Request body must be a JSON object.")
    return data


def serialize_user(user) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "email_verified": user.email_verified_at is not None,
        "handle": user.handle,
        "name": user.name,
        "avatar_url": avatar_url(user.id, user.avatar_version),
        "created_at": iso(user.created_at),
    }


def serialize_identity(identity) -> dict:
    return {
        "provider": identity.provider,
        "provider_email": identity.provider_email,
        "created_at": iso(identity.created_at),
    }


def serialize_session_row(row, current_sid) -> dict:
    return {
        "id": str(row.id),
        "current": str(row.id) == str(current_sid),
        "user_agent": row.user_agent,
        "created_at": iso(row.created_at),
        "last_seen_at": iso(row.last_seen_at),
    }
