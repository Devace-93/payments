"""Application factory.

``create_app()`` builds and returns the Flask app. Gunicorn runs it directly::

    gunicorn -b 0.0.0.0:5000 -w 2 'api.app:create_app()'

Responsibilities here: credentialed CORS against ``ALLOWED_ORIGINS`` (checked
per request, so wildcard patterns work; public endpoints set ``*``
themselves), the request size cap, rate limiting, blueprint registration,
health checks and the error handlers that always emit the ``{"error": {...}}``
envelope.
"""
from __future__ import annotations

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from dbcore.config import config
from dbcore.origins import matcher

from .errors import ApiError
from .extensions import limiter

ALLOW_HEADERS = "Content-Type, Authorization, X-Requested-With"
ALLOW_METHODS = "GET, POST, PUT, PATCH, DELETE, OPTIONS"


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024
    app.config["SECRET_KEY"] = config.secret_key

    limiter.init_app(app)

    from .blueprints.catalog import bp as catalog_bp
    from .blueprints.checkout import bp as checkout_bp
    from .blueprints.me import bp as me_bp
    from .blueprints.public import bp as public_bp
    from .blueprints.service import bp as service_bp
    from .blueprints.stripe_webhook import bp as stripe_bp
    from .features import bp as features_bp

    app.register_blueprint(catalog_bp, url_prefix="/api")
    app.register_blueprint(checkout_bp, url_prefix="/api/checkout")
    app.register_blueprint(me_bp, url_prefix="/api")
    app.register_blueprint(service_bp, url_prefix="/api/v1")
    app.register_blueprint(stripe_bp, url_prefix="/api/stripe")
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
