"""``POST /api/checkout`` (optional session) and ``GET /api/checkout/<id>``
(public): the only place that creates Stripe Checkout Sessions.

A ``checkout_sessions`` row is written first; its id is the Stripe
idempotency key, ``client_reference_id`` and ``metadata.checkout_id``, so a
retried POST cannot create two Stripe sessions and the success page reads
our row instead of trusting query params.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from flask import Blueprint, g, jsonify, request
from sqlalchemy import select

from dbcore import catalog, fees
from dbcore.config import config
from dbcore.db import session_scope
from dbcore.entitlements import active_subscription, entitlements_for
from dbcore.feature_flags import is_enabled
from dbcore.mail_templates import pick_lang
from dbcore.models import App, CheckoutSession, Customer, Payment, Product
from dbcore.origins import matcher as global_matcher
from dbcore.stripe_client import as_dict, client, is_fake

from ..auth import ensure_customer, optional_session
from ..errors import ApiError
from ..extensions import limiter
from ..returns import is_safe_return_to
from ..serializers import json_body
from ..stripe_events import handle_checkout_completed

log = logging.getLogger("payments.checkout")

bp = Blueprint("checkout", __name__)

RETRIEVE_AFTER_SECONDS = 20
STRIPE_LOCALES = {
    "auto", "bg", "cs", "da", "de", "el", "en", "en-GB", "es", "es-419", "et", "fi", "fil", "fr", "fr-CA", "hr",
    "hu", "id", "it", "ja", "ko", "lt", "lv", "ms", "mt", "nb", "nl", "pl", "pt", "pt-BR", "ro", "ru", "sk", "sl",
    "sv", "th", "tr", "vi", "zh", "zh-HK", "zh-TW",
}


def _str(data: dict, key: str, max_len: int) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ApiError(400, "validation_error", f"{key} must be a string.")
    value = value.strip()
    if len(value) > max_len:
        raise ApiError(400, "validation_error", f"{key} is too long (max {max_len}).")
    return value or None


def _stripe_locale(lang: str | None) -> str:
    if not lang:
        return "auto"
    base = lang.split("-")[0].lower()
    if base == "es":
        # Latin-American Spanish unless Spain is explicit (the account is in Mexico).
        return "es" if lang.lower() == "es-es" else "es-419"
    if lang in STRIPE_LOCALES:
        return lang
    return base if base in STRIPE_LOCALES else "auto"


@bp.post("")
@limiter.limit("10/minute")
def create_checkout():
    data = json_body()
    claims = optional_session()
    kind = data.get("kind")
    if kind not in ("donation", "subscription"):
        raise ApiError(400, "validation_error", "kind must be donation or subscription.")
    if not is_enabled("donations" if kind == "donation" else "subscriptions", (claims or {}).get("sub", "anonymous")):
        raise ApiError(403, "feature_disabled", f"'{kind}s' are not available right now.")
    currency = (data.get("currency") or config.fallback_currency())
    if not isinstance(currency, str) or currency.lower() not in config.currencies:
        raise ApiError(400, "unsupported_currency", "Unsupported currency.")
    currency = currency.lower()
    return_to = _str(data, "return_to", 2000)
    origin = _str(data, "origin", 255)
    display_name = _str(data, "display_name", 80)
    message = _str(data, "message", 280)
    public = bool(data.get("public", False))
    lang = pick_lang(_str(data, "lang", 10), request.headers.get("Accept-Language"))
    raw_lang = _str(data, "lang", 10) or lang

    with session_scope() as session:
        app = session.scalar(select(App).where(App.slug == str(data.get("app") or "").strip().lower()))
        if app is None or not app.active:
            raise ApiError(400, "unknown_app", "Unknown app.")
        app_matcher = catalog.origin_matcher(app)
        if return_to is not None and not (is_safe_return_to(return_to) and app_matcher.allows_url(return_to)):
            raise ApiError(400, "bad_origin", "return_to is not on this app's origins.")
        if origin is not None and not (global_matcher.allows(origin) and app_matcher.allows(origin)):
            raise ApiError(400, "bad_origin", "origin is not one of this app's origins.")

        identity_id = g.identity_id
        customer: Customer | None = None
        if claims is not None:
            customer = ensure_customer(session, claims)
            customer.lang = lang

        product: Product | None = None
        amount: int | None = None
        if kind == "donation":
            try:
                amount = int(data.get("amount"))
            except (TypeError, ValueError):
                raise ApiError(400, "validation_error", "amount must be an integer (minor units).") from None
            minimum = fees.min_amount(currency)
            if amount < minimum:
                raise ApiError(400, "amount_too_small", "Amount is below the minimum.", {"min": minimum})
            maximum = fees.max_amount(currency)
            if maximum is not None and amount > maximum:
                raise ApiError(400, "amount_too_large", "Amount is above the maximum.", {"max": maximum})
            product = session.scalar(select(Product).where(Product.kind == "donation", Product.currency == currency))
            if product is None or not product.stripe_product_id:
                raise ApiError(400, "unsupported_currency", "No donation price for this currency (run sync-catalog).")
        else:
            if claims is None:
                code = g.session_error or "no_session"
                raise ApiError(401, code, "Sign in to subscribe." if code == "no_session" else "Session expired.")
            key = _str(data, "price", 60)
            product = (
                session.scalar(
                    select(Product).where(
                        Product.app_id == app.id, Product.key == key, Product.kind == "subscription", Product.active.is_(True)
                    )
                )
                if key
                else None
            )
            if product is None or not product.stripe_price_id:
                raise ApiError(400, "unknown_price", "Unknown price for this app.")
            if currency not in (product.amounts or {}):
                raise ApiError(400, "unsupported_currency", "This plan is not sold in that currency.")
            amount = int(product.amounts[currency])
            if active_subscription(session, identity_id, app.id) is not None:
                raise ApiError(409, "already_subscribed", "You already have an active subscription for this app.")

        row = CheckoutSession(
            app_id=app.id,
            product_id=product.id if product else None,
            kind=kind,
            identity_id=identity_id,
            email=(claims or {}).get("email"),
            amount=amount,
            currency=currency,
            return_to=return_to,
            opener_origin=origin,
            public=public,
            display_name=display_name,
            message=message,
            lang=lang,
        )
        session.add(row)
        session.flush()

        params = _session_params(row, app, product, customer, claims, raw_lang)
        stripe = client()
        try:
            created = as_dict(stripe.v1.checkout.sessions.create(params=params, options={"idempotency_key": str(row.id)}))
        except Exception as err:
            log.warning("stripe checkout create failed for %s: %s", row.id, err)
            raise ApiError(502, "stripe_error", "Could not start the checkout. Try again in a moment.") from err
        row.stripe_session_id = created["id"]
        row.status = "open"
        body = {"id": str(row.id), "url": created["url"]}
    return jsonify(body), 201


def _session_params(row: CheckoutSession, app: App, product: Product | None, customer: Customer | None,
                    claims: dict | None, lang: str) -> dict:
    metadata = {"app": app.slug, "kind": row.kind, "checkout_id": str(row.id)}
    if row.identity_id is not None:
        metadata["identity_id"] = str(row.identity_id)
    params: dict = {
        "success_url": f"{config.payments_url}/success?cs={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{config.payments_url}/cancel?id={row.id}",
        "client_reference_id": str(row.id),
        "metadata": metadata,
        "locale": _stripe_locale(lang),
        "automatic_tax": {"enabled": config.stripe_automatic_tax},
    }
    if config.stripe_integration_identifier:
        params["integration_identifier"] = config.stripe_integration_identifier
    if customer is not None and customer.stripe_customer_id:
        params["customer"] = customer.stripe_customer_id
        if config.stripe_automatic_tax:
            params["customer_update"] = {"address": "auto"}
    elif claims is not None and claims.get("email"):
        params["customer_email"] = claims["email"]
    if row.kind == "donation":
        params["mode"] = "payment"
        params["submit_type"] = "donate"
        params["line_items"] = [
            {
                "quantity": 1,
                "price_data": {"currency": row.currency, "unit_amount": row.amount, "product": product.stripe_product_id},
            }
        ]
        params["payment_intent_data"] = {"metadata": metadata}
        if "customer" not in params:
            params["customer_creation"] = "always"
    else:
        params["mode"] = "subscription"
        params["line_items"] = [{"price": product.stripe_price_id, "quantity": 1}]
        params["currency"] = row.currency
        params["subscription_data"] = {"metadata": metadata}
        params["allow_promotion_codes"] = True
    return params


def _find_row(session, raw_id: str) -> CheckoutSession | None:
    if raw_id.startswith("cs_"):
        return session.scalar(select(CheckoutSession).where(CheckoutSession.stripe_session_id == raw_id))
    try:
        return session.get(CheckoutSession, uuid.UUID(raw_id))
    except ValueError:
        return None


@bp.get("/<raw_id>")
def get_checkout(raw_id: str):
    with session_scope() as session:
        row = _find_row(session, raw_id)
        if row is None:
            raise ApiError(404, "not_found", "No such checkout.")
        if row.status == "open" and row.stripe_session_id:
            _maybe_reconcile(session, row)
        app = session.get(App, row.app_id)
        product = session.get(Product, row.product_id) if row.product_id else None
        payment = session.scalar(
            select(Payment).where(Payment.stripe_checkout_session_id == row.stripe_session_id)
        ) if row.stripe_session_id else None
        entitlements: list[str] = []
        if row.identity_id is not None and row.kind == "subscription":
            entitlements = entitlements_for(session, row.identity_id, app)["entitlements"]
        body = {
            "id": str(row.id),
            "status": row.status,
            "kind": row.kind,
            "price": product.key if product else None,
            "app": {"slug": app.slug, "name": app.name},
            "amount": row.amount,
            "currency": row.currency,
            "return_to": row.return_to,
            "opener_origin": row.opener_origin,
            "needs_claim": row.kind == "donation" and row.identity_id is None and row.status == "completed",
            "claimed": bool(payment and payment.claimed_at),
            "entitlements": entitlements,
            "email": payment.email if payment else None,
        }
    resp = jsonify(body)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


def _maybe_reconcile(session, row: CheckoutSession) -> None:
    """After the webhook has had 20 s, ask Stripe directly (real mode only)."""
    stripe = client()
    if is_fake(stripe):
        return
    created = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - created < timedelta(seconds=RETRIEVE_AFTER_SECONDS):
        return
    try:
        cs = as_dict(stripe.v1.checkout.sessions.retrieve(row.stripe_session_id, params={"expand": ["subscription"]}))
    except Exception as err:  # pragma: no cover - network
        log.warning("retrieve %s failed: %s", row.stripe_session_id, err)
        return
    if cs.get("status") == "expired":
        row.status = "expired"
    elif cs.get("status") == "complete":
        handle_checkout_completed(session, stripe, cs)
