"""Application factory.

``create_app()`` builds and returns the Flask app. Gunicorn runs it directly::

    gunicorn -b 0.0.0.0:5000 -w 2 'api.app:create_app()'

Responsibilities here: credentialed CORS against ``ALLOWED_ORIGINS`` (checked
per request, so wildcard patterns work), the request size cap (avatars up to
2 MB), rate limiting, the OAuth client registry, the signed cookie that
carries OAuth state, blueprint registration, health checks and the error
handlers that always emit the ``{"error": {...}}`` envelope.
"""
from __future__ import annotations

from datetime import timedelta

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from dbcore.config import config
from dbcore.origins import matcher

from .errors import ApiError
from .extensions import limiter, oauth

ALLOW_HEADERS = "Content-Type, Authorization, X-Requested-With"
ALLOW_METHODS = "GET, POST, PUT, PATCH, DELETE, OPTIONS"


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 3 * 1024 * 1024
    app.config["SECRET_KEY"] = config.secret_key
    # Flask's signed cookie session is used ONLY to carry OAuth state between
    # /start and /callback (Authlib stores state + nonce + PKCE verifier in
    # it). Scoped to the OAuth routes and short-lived; see CONTRACT.md.
    app.config.update(
        SESSION_COOKIE_NAME="3m4_oauth",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=config.cookie_secure,
        SESSION_COOKIE_PATH="/api/auth/oauth",
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=10),
    )

    limiter.init_app(app)
    oauth.init_app(app)

    from .blueprints.auth import bp as auth_bp
    from .blueprints.me import bp as me_bp
    from .blueprints.oauth import bp as oauth_bp, register_providers
    from .blueprints.public import bp as public_bp
    from .blueprints.session import bp as session_bp
    from .features import bp as features_bp

    register_providers(oauth)
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(oauth_bp, url_prefix="/api/auth/oauth")
    app.register_blueprint(session_bp, url_prefix="/api/session")
    app.register_blueprint(me_bp, url_prefix="/api/me")
    app.register_blueprint(features_bp, url_prefix="/api/features")
    app.register_blueprint(public_bp)

    @app.get("/healthz")
    @app.get("/api/healthz")
    @limiter.exempt
    def healthz():
        return jsonify({"status": "ok"})

    _register_cors(app)
    _register_error_handlers(app)
    return app


def _register_cors(app: Flask) -> None:
    @app.before_request
    def _preflight():
        if request.method == "OPTIONS":
            return app.make_default_options_response()
        return None

    @app.after_request
    def _cors(resp):
        origin = request.headers.get("Origin")
        if origin and matcher.allows(origin) and resp.headers.get("Access-Control-Allow-Origin") != "*":
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Credentials"] = "true"
            resp.headers.add("Vary", "Origin")
        if request.method == "OPTIONS" and "Access-Control-Allow-Origin" in resp.headers:
            resp.headers["Access-Control-Allow-Methods"] = ALLOW_METHODS
            resp.headers["Access-Control-Allow-Headers"] = request.headers.get("Access-Control-Request-Headers") or ALLOW_HEADERS
            resp.headers["Access-Control-Max-Age"] = "600"
        return resp


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def _handle_api_error(err: ApiError):
        return jsonify(err.to_dict()), err.status

    @app.errorhandler(429)
    def _handle_rate_limit(err):
        return jsonify({"error": {"code": "rate_limited", "message": "Too many requests."}}), 429

    @app.errorhandler(413)
    def _handle_too_large(err):
        return jsonify({"error": {"code": "payload_too_large", "message": "Request body is too large."}}), 413

    @app.errorhandler(HTTPException)
    def _handle_http_exception(err: HTTPException):
        code = (err.name or "error").lower().replace(" ", "_")
        return jsonify({"error": {"code": code, "message": err.description or err.name}}), err.code or 500

    @app.errorhandler(Exception)
    def _handle_unexpected(err: Exception):  # pragma: no cover
        app.logger.exception("Unhandled exception")
        return jsonify({"error": {"code": "internal_error", "message": "An unexpected error occurred."}}), 500
