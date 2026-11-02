"""Public catalog endpoints: ``GET /api/catalog``, ``GET /api/geo``,
``GET /api/fees``. All CORS ``*`` (the pages and pay.js call them from any
app origin)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from sqlalchemy import select

from dbcore import catalog, fees, geo
from dbcore.config import config
from dbcore.db import session_scope
from dbcore.feature_flags import is_enabled
from dbcore.models import App, Product

from ..errors import ApiError
from ..extensions import client_ip, limiter

bp = Blueprint("catalog", __name__)


def _public(resp, max_age: int | None = None):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    if max_age is not None:
        resp.headers["Cache-Control"] = f"public, max-age={max_age}"
    else:
        resp.headers["Cache-Control"] = "no-store"
    return resp


def _app_or_400(session, slug: str | None) -> App:
    app = session.scalar(select(App).where(App.slug == (slug or "").strip().lower())) if slug else None
    if app is None or not app.active:
        raise ApiError(400, "unknown_app", "Unknown app.")
    return app


def serialize_product(product: Product) -> dict:
    return {
        "key": product.key,
        "kind": product.kind,
        "entitlement": product.entitlement,
        "interval": product.interval,
        "label": product.label,
        "amounts": {k: v for k, v in (product.amounts or {}).items() if k in config.currencies},
    }


@bp.get("/catalog")
def get_catalog():
    with session_scope() as session:
        app = _app_or_400(session, request.args.get("app"))
        products = session.scalars(
            select(Product)
            .where(Product.app_id == app.id, Product.active.is_(True), Product.kind != "donation")
            .order_by(Product.sort, Product.key)
        ).all()
        presets = catalog.donation_presets()
        body = {
            "app": {"slug": app.slug, "name": app.name, "icon": app.icon},
            "currencies": list(config.currencies),
            "default_currency": config.fallback_currency(),
            "donation": {
                "presets": {cur: fees.presets(presets, cur) for cur in config.currencies},
                "min": {cur: fees.min_amount(cur) for cur in config.currencies},
                "max": {cur: fees.max_amount(cur) for cur in config.currencies},
            },
            "products": [serialize_product(p) for p in products],
            "github_sponsors_url": config.github_sponsors_url or None,
            "fee_hint": is_enabled("fee-hint"),
        }
    return _public(jsonify(body), max_age=300)


@bp.get("/geo")
@limiter.exempt
def get_geo():
    return _public(jsonify(geo.lookup(client_ip())))


@bp.get("/fees")
def get_fees():
    try:
        amount = int(request.args.get("amount", ""))
    except ValueError:
        raise ApiError(400, "validation_error", "amount must be an integer (minor units).") from None
    currency = (request.args.get("currency") or config.fallback_currency()).lower()
    if currency not in config.currencies:
        raise ApiError(400, "unsupported_currency", "Unsupported currency.")
    kind = request.args.get("kind") or "donation"
    if kind not in ("donation", "subscription"):
        raise ApiError(400, "validation_error", "kind must be donation or subscription.")
    if amount <= 0:
        raise ApiError(400, "validation_error", "amount must be positive.")
    est = fees.estimate(amount, currency, kind)
    body = {
        "amount": amount,
        "currency": currency,
        "fee": round(est["fee_mxn"] + est["tax_mxn"], 2),
        "fee_mxn": est["fee_mxn"],
        "tax_mxn": est["tax_mxn"],
        "isr_mxn": est["isr_mxn"],
        "gross_mxn": est["gross_mxn"],
        "net_mxn": est["net_mxn"],
        "retention": est["retention"],
        "min_amount": fees.min_amount(currency, kind),
    }
    return _public(jsonify(body), max_age=300)
