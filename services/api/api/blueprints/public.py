"""Host-root public routes: the JWKS relying apps verify with, and avatars."""
from __future__ import annotations

import uuid

from flask import Blueprint, Response, jsonify, request

from dbcore import avatars
from dbcore.db import session_scope
from dbcore.keys import keyring
from dbcore.models import Avatar, User

from ..extensions import limiter

bp = Blueprint("public", __name__)


@bp.get("/.well-known/jwks.json")
@limiter.exempt
def jwks():
    resp = jsonify(keyring().jwks())
    resp.headers["Cache-Control"] = "public, max-age=600"
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


@bp.get("/avatars/<user_id>")
@limiter.exempt
def avatar(user_id: str):
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return _not_found()
    with session_scope() as session:
        user = session.get(User, uid)
        if user is None:
            return _not_found()
        row = session.get(Avatar, uid)
        if row is not None:
            data, content_type, kind = bytes(row.data), row.content_type, "u"
        else:
            data, content_type, kind = avatars.default_svg(user.id, user.name, user.handle), "image/svg+xml", "d"
        etag = f'"{str(user.id)[:8]}-{user.avatar_version}-{kind}"'
    if request.headers.get("If-None-Match") == etag:
        resp = Response(status=304)
    else:
        resp = Response(data, mimetype=content_type)
    resp.headers["ETag"] = etag
    resp.headers["Cache-Control"] = "public, max-age=86400"
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


def _not_found() -> Response:
    resp = jsonify({"error": {"code": "not_found", "message": "No such user."}})
    resp.status_code = 404
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp
