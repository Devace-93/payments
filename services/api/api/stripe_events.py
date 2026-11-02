"""Stripe webhook handlers (CONTRACT.md §5 "Stripe", plan "Stripe handlers").

Pure functions over a DB session, a Stripe client and the *plain dict* of the
Stripe object (``dbcore.stripe_client.as_dict``), so the webhook route,
``cli seed-completed`` and the tests share one code path. Every handler is
idempotent (upsert by Stripe id) and writes its outbox rows in the caller's
transaction.

Entry point: :func:`handle_event(session, stripe, event_type, obj,
event_created=None)` → a short outcome string.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from dbcore import claims as claim_codes
from dbcore.entitlements import entitlements_for, serialize_subscription
from dbcore.models import App, CheckoutSession, Customer, Payment, Product, Subscription
from dbcore.outbox import enqueue_mail, enqueue_webhook
from dbcore.stripe_client import as_dict, is_fake

from .serializers import serialize_payment

log = logging.getLogger("payments.stripe")

PAID_STATUSES = ("paid", "no_payment_required")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _id(value) -> str | None:
    """Stripe expands some fields to objects; we only ever need the id."""
    if isinstance(value, dict):
        return value.get("id")
    return value or None


def _ts(value) -> datetime | None:
    if value in (None, "", 0):
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid(value) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def _app_by_slug(session, slug: str | None) -> App | None:
    return session.scalar(select(App).where(App.slug == slug)) if slug else None


def _customer_lang(session, identity_id: uuid.UUID | None, fallback: str = "en") -> str:
    if identity_id is None:
        return fallback
    customer = session.get(Customer, identity_id)
    return (customer.lang if customer and customer.lang else None) or fallback


def _ensure_customer(session, identity_id: uuid.UUID, *, email: str | None, stripe_customer_id: str | None,
                     lang: str | None = None) -> Customer:
    customer = session.get(Customer, identity_id)
    if customer is None:
        customer = Customer(identity_id=identity_id)
        session.add(customer)
    if email and not customer.email:
        customer.email = email.lower()
    if stripe_customer_id and not customer.stripe_customer_id:
        customer.stripe_customer_id = stripe_customer_id
    if lang:
        customer.lang = lang
    session.flush()
    return customer


def _push(session, app: App, *, type: str, identity_id: uuid.UUID | None, email: str | None,
          payment: Payment | None = None, subscription: Subscription | None = None) -> None:
    """Queue a push event carrying the full entitlement set (no-op for guests)."""
    if identity_id is None:
        return
    ents = entitlements_for(session, identity_id, app)
    data = {
        "entitlements": ents["entitlements"],
        "subscription": serialize_subscription(subscription) if subscription is not None else ents["subscription"],
        "payment": serialize_payment(payment, app.slug) if payment is not None else None,
        "updated_at": ents["updated_at"],
    }
    enqueue_webhook(session, app=app, event={"type": type, "identity_id": str(identity_id), "email": email, "data": data})


def _donation_product(session, currency: str) -> Product | None:
    return session.scalar(select(Product).where(Product.kind == "donation", Product.currency == currency.lower()))


def _product_for_price(session, app: App | None, price: dict | str | None) -> Product | None:
    if price is None:
        return None
    if isinstance(price, dict):
        price_id, lookup_key = price.get("id"), price.get("lookup_key")
    else:
        price_id, lookup_key = price, None
    product = session.scalar(select(Product).where(Product.stripe_price_id == price_id)) if price_id else None
    if product is None and lookup_key:
        product = session.scalar(select(Product).where(Product.lookup_key == lookup_key))
    return product


# --------------------------------------------------------------------------- #
# checkout sessions
# --------------------------------------------------------------------------- #
def _checkout_row(session, cs: dict) -> CheckoutSession | None:
    row = session.scalar(select(CheckoutSession).where(CheckoutSession.stripe_session_id == cs.get("id")))
    if row is None:
        ref = _uuid((cs.get("metadata") or {}).get("checkout_id") or cs.get("client_reference_id"))
        if ref is not None:
            row = session.get(CheckoutSession, ref)
            if row is not None and not row.stripe_session_id:
                row.stripe_session_id = cs.get("id")
    return row


def handle_checkout_completed(session, stripe, cs: dict) -> str:
    """``checkout.session.completed`` / ``checkout.session.async_payment_succeeded``."""
    row = _checkout_row(session, cs)
    if row is None:
        log.warning("checkout %s has no local row; ignored", cs.get("id"))
        return "no_row"
    if cs.get("payment_status") not in PAID_STATUSES:
        row.status = "open"
        return "pending_payment"
    app = session.get(App, row.app_id)
    email = ((cs.get("customer_details") or {}).get("email") or cs.get("customer_email") or row.email or "").lower() or None
    stripe_customer_id = _id(cs.get("customer"))
    if row.identity_id is not None:
        _ensure_customer(session, row.identity_id, email=email, stripe_customer_id=stripe_customer_id, lang=row.lang)

    if cs.get("mode") == "subscription" or row.kind == "subscription":
        sub = cs.get("subscription")
        if isinstance(sub, str):
            sub = _retrieve_subscription(stripe, sub)
        if not isinstance(sub, dict) or not sub.get("id"):
            row.status = "completed"
            return "no_subscription"
        if row.identity_id is None:
            log.warning("subscription checkout %s without identity; ignored", cs.get("id"))
            row.status = "completed"
            return "no_identity"
        product = session.get(Product, row.product_id) if row.product_id else None
        subscription, _created = upsert_subscription(session, sub, app=app, product=product, identity_id=row.identity_id)
        first_completion = row.status != "completed"
        row.status = "completed"
        if first_completion:
            enqueue_mail(
                session,
                template="subscription_started",
                to=email or "",
                lang=row.lang,
                app_id=app.id,
                params={
                    "app_name": app.name,
                    "label": product.label if product else subscription.entitlement or "",
                    "amount": (product.amounts or {}).get(row.currency) if product else None,
                    "currency": row.currency,
                    "interval": product.interval if product else None,
                    "period_end": _date(subscription.current_period_end),
                },
            )
        _push(session, app, type="subscription.updated", identity_id=row.identity_id, email=email, subscription=subscription)
        return "subscription"

    # payment mode (donation / one_time)
    pi_id = _id(cs.get("payment_intent"))
    existing = None
    if pi_id:
        existing = session.scalar(select(Payment).where(Payment.stripe_payment_intent_id == pi_id))
    if existing is None:
        existing = session.scalar(select(Payment).where(Payment.stripe_checkout_session_id == cs.get("id")))
    if existing is not None:
        row.status = "completed"
        return "duplicate"
    currency = (cs.get("currency") or row.currency or "").lower()
    amount = int(cs.get("amount_total") if cs.get("amount_total") is not None else (row.amount or 0))
    product = session.get(Product, row.product_id) if row.product_id else _donation_product(session, currency)
    charge_id = _latest_charge(stripe, pi_id)
    payment = Payment(
        stripe_payment_intent_id=pi_id,
        stripe_checkout_session_id=cs.get("id"),
        stripe_charge_id=charge_id,
        app_id=app.id,
        product_id=product.id if product else None,
        kind="donation" if row.kind == "donation" else "one_time",
        amount=amount,
        currency=currency,
        status="paid",
        email=email,
        identity_id=row.identity_id,
        display_name=row.display_name,
        message=row.message,
        public=bool(row.public),
        raw={"checkout_session": cs.get("id"), "payment_intent": pi_id, "customer": stripe_customer_id},
    )
    session.add(payment)
    session.flush()
    row.status = "completed"
    params = {"amount": amount, "currency": currency, "app_name": app.name}
    if row.identity_id is None:
        params["code"] = claim_codes.issue(session, payment)
    if email:
        enqueue_mail(session, template="donation_receipt", to=email, lang=row.lang, app_id=app.id, params=params)
    _push(session, app, type="payment.succeeded", identity_id=row.identity_id, email=email, payment=payment)
    return "guest_donation" if row.identity_id is None else "donation"


def handle_checkout_expired(session, cs: dict) -> str:
    row = _checkout_row(session, cs)
    if row is None:
        return "no_row"
    if row.status != "completed":
        row.status = "expired"
    return "expired"


def _latest_charge(stripe, pi_id: str | None) -> str | None:
    if not pi_id or is_fake(stripe):
        return None
    try:
        pi = as_dict(stripe.v1.payment_intents.retrieve(pi_id))
    except Exception as err:  # pragma: no cover - network
        log.warning("could not retrieve %s: %s", pi_id, err)
        return None
    return _id(pi.get("latest_charge"))


def _retrieve_subscription(stripe, sub_id: str) -> dict | None:
    try:
        return as_dict(stripe.v1.subscriptions.retrieve(sub_id))
    except Exception as err:  # pragma: no cover - network
        log.warning("could not retrieve %s: %s", sub_id, err)
        return None


def _date(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m-%d") if dt else None


# --------------------------------------------------------------------------- #
# subscriptions
# --------------------------------------------------------------------------- #
def _period(sub: dict) -> tuple[datetime | None, datetime | None]:
    """Current period from the first item (2025+ API) or the top level."""
    items = ((sub.get("items") or {}).get("data") or [])
    first = items[0] if items else {}
    start = first.get("current_period_start") or sub.get("current_period_start")
    end = first.get("current_period_end") or sub.get("current_period_end")
    return _ts(start), _ts(end)


def upsert_subscription(session, sub: dict, *, app: App | None = None, product: Product | None = None,
                        identity_id: uuid.UUID | None = None, event_created: int | None = None,
                        force_status: str | None = None) -> tuple[Subscription, bool]:
    """Create or refresh the mirror row for a Stripe subscription object.
    Returns ``(row, created)``. Older events (by ``event_created``) do not
    overwrite newer state."""
    meta = sub.get("metadata") or {}
    row = session.scalar(select(Subscription).where(Subscription.stripe_subscription_id == sub["id"]))
    items = ((sub.get("items") or {}).get("data") or [])
    price = (items[0].get("price") if items else None)
    if app is None:
        app = _app_by_slug(session, meta.get("app"))
    if product is None:
        product = _product_for_price(session, app, price)
    if app is None and product is not None:
        app = session.get(App, product.app_id)
    if identity_id is None:
        identity_id = _uuid(meta.get("identity_id"))
    if row is None:
        if app is None or identity_id is None:
            raise ValueError("subscription without app/identity")
        row = Subscription(stripe_subscription_id=sub["id"], identity_id=identity_id, app_id=app.id, status="incomplete")
        session.add(row)
        created = True
    else:
        created = False
        if event_created is not None and row.stripe_updated and event_created < row.stripe_updated:
            return row, False
    start, end = _period(sub)
    row.stripe_customer_id = _id(sub.get("customer")) or row.stripe_customer_id
    if product is not None:
        row.product_id = product.id
        row.entitlement = product.entitlement
    row.status = force_status or sub.get("status") or row.status
    row.current_period_start = start or row.current_period_start
    row.current_period_end = end or row.current_period_end
    row.cancel_at_period_end = bool(sub.get("cancel_at_period_end"))
    row.canceled_at = _ts(sub.get("canceled_at"))
    if event_created is not None:
        row.stripe_updated = max(row.stripe_updated or 0, int(event_created))
    row.raw = {
        "id": sub["id"],
        "status": row.status,
        "price": _id(price) if price else None,
        "lookup_key": price.get("lookup_key") if isinstance(price, dict) else None,
    }
    session.flush()
    return row, created


def handle_subscription_event(session, stripe, sub: dict, *, deleted: bool = False, event_created: int | None = None) -> str:
    """``customer.subscription.created|updated|deleted``."""
    existing = session.scalar(select(Subscription).where(Subscription.stripe_subscription_id == sub.get("id")))
    was_cancelling = bool(existing and (existing.cancel_at_period_end or existing.status == "canceled"))
    try:
        row, created = upsert_subscription(
            session, sub, event_created=event_created, force_status="canceled" if deleted else None
        )
    except ValueError:
        log.warning("subscription %s without app/identity metadata; ignored", sub.get("id"))
        return "no_identity"
    if existing is not None and not created and event_created is not None and row.stripe_updated and event_created < row.stripe_updated and not deleted:
        return "stale"
    app = session.get(App, row.app_id)
    customer = session.get(Customer, row.identity_id)
    email = customer.email if customer else None
    lang = customer.lang if customer and customer.lang else "en"
    product = session.get(Product, row.product_id) if row.product_id else None
    now_cancelling = deleted or row.cancel_at_period_end or row.status == "canceled"
    if now_cancelling and not was_cancelling and email:
        enqueue_mail(
            session,
            template="subscription_cancelled",
            to=email,
            lang=lang,
            app_id=app.id,
            params={"app_name": app.name, "label": product.label if product else row.entitlement or "", "period_end": _date(row.current_period_end)},
        )
    _push(session, app, type="subscription.updated", identity_id=row.identity_id, email=email, subscription=row)
    return "deleted" if deleted else ("created" if created else "updated")


# --------------------------------------------------------------------------- #
# invoices
# --------------------------------------------------------------------------- #
def _invoice_subscription_id(invoice: dict) -> str | None:
    parent = invoice.get("parent") or {}
    details = parent.get("subscription_details") or {}
    return _id(details.get("subscription")) or _id(invoice.get("subscription"))


def handle_invoice_paid(session, stripe, invoice: dict) -> str:
    sub_id = _invoice_subscription_id(invoice)
    if not sub_id:
        return "no_subscription"
    row = session.scalar(select(Subscription).where(Subscription.stripe_subscription_id == sub_id))
    fresh = _retrieve_subscription(stripe, sub_id) if not is_fake(stripe) else None
    if row is None:
        # ``invoice.paid`` often arrives before ``customer.subscription.created``:
        # build the mirror row from Stripe's current object instead of dropping
        # the invoice (the later subscription event still sends mail + push).
        if not fresh:
            return "unknown_subscription"
        identity_id = _uuid((fresh.get("metadata") or {}).get("identity_id"))
        if identity_id is None:
            return "unknown_subscription"
        _ensure_customer(session, identity_id, email=invoice.get("customer_email"),
                         stripe_customer_id=_id(fresh.get("customer")))
        try:
            row, _ = upsert_subscription(session, fresh, identity_id=identity_id)
        except ValueError:
            return "unknown_subscription"
    elif fresh:
        upsert_subscription(session, fresh)
    amount = int(invoice.get("amount_paid") or 0)
    if amount <= 0:
        return "zero_invoice"
    existing = session.scalar(select(Payment).where(Payment.stripe_invoice_id == invoice.get("id")))
    if existing is not None:
        return "duplicate"
    app = session.get(App, row.app_id)
    pi_id = _id(invoice.get("payment_intent"))
    payment = Payment(
        stripe_invoice_id=invoice.get("id"),
        stripe_payment_intent_id=pi_id,
        stripe_charge_id=_id(invoice.get("charge")),
        app_id=app.id,
        product_id=row.product_id,
        subscription_id=row.id,
        kind="invoice",
        amount=amount,
        currency=(invoice.get("currency") or "").lower(),
        status="paid",
        email=(invoice.get("customer_email") or "").lower() or None,
        identity_id=row.identity_id,
        public=False,
        raw={"invoice": invoice.get("id"), "billing_reason": invoice.get("billing_reason")},
    )
    session.add(payment)
    session.flush()
    return "invoice"


def handle_invoice_failed(session, invoice: dict) -> str:
    sub_id = _invoice_subscription_id(invoice)
    row = session.scalar(select(Subscription).where(Subscription.stripe_subscription_id == sub_id)) if sub_id else None
    if row is None:
        return "unknown_subscription"
    app = session.get(App, row.app_id)
    customer = session.get(Customer, row.identity_id)
    email = (invoice.get("customer_email") or (customer.email if customer else None) or "").lower()
    if not email:
        return "no_email"
    product = session.get(Product, row.product_id) if row.product_id else None
    enqueue_mail(
        session,
        template="payment_failed",
        to=email,
        lang=customer.lang if customer and customer.lang else "en",
        app_id=app.id,
        params={"app_name": app.name, "label": product.label if product else row.entitlement or ""},
    )
    return "payment_failed"


# --------------------------------------------------------------------------- #
# refunds / disputes
# --------------------------------------------------------------------------- #
def _payment_for_charge(session, charge: dict) -> Payment | None:
    pi_id = _id(charge.get("payment_intent"))
    payment = None
    if pi_id:
        payment = session.scalar(select(Payment).where(Payment.stripe_payment_intent_id == pi_id))
    if payment is None and charge.get("id"):
        payment = session.scalar(select(Payment).where(Payment.stripe_charge_id == charge.get("id")))
    return payment


def _mark_refunded(session, payment: Payment, status: str, amount_refunded: int | None = None) -> None:
    payment.status = status
    if amount_refunded is not None:
        payment.amount_refunded = amount_refunded
    payment.public = False
    claim_codes.void(session, payment.id)
    app = session.get(App, payment.app_id)
    _push(session, app, type="payment.refunded", identity_id=payment.identity_id, email=payment.email, payment=payment)


def handle_charge_refunded(session, charge: dict) -> str:
    payment = _payment_for_charge(session, charge)
    if payment is None:
        return "unknown_payment"
    refunded = int(charge.get("amount_refunded") or 0)
    full = bool(charge.get("refunded")) or refunded >= payment.amount
    _mark_refunded(session, payment, "refunded" if full else "partially_refunded", refunded)
    if charge.get("id") and not payment.stripe_charge_id:
        payment.stripe_charge_id = charge.get("id")
    return "refunded"


def handle_dispute_created(session, dispute: dict) -> str:
    charge = {"id": _id(dispute.get("charge")), "payment_intent": _id(dispute.get("payment_intent"))}
    payment = _payment_for_charge(session, charge)
    if payment is None:
        return "unknown_payment"
    _mark_refunded(session, payment, "disputed")
    return "disputed"


# --------------------------------------------------------------------------- #
# dispatch
# --------------------------------------------------------------------------- #
HANDLED = (
    "checkout.session.completed",
    "checkout.session.async_payment_succeeded",
    "checkout.session.expired",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.paid",
    "invoice.payment_failed",
    "charge.refunded",
    "charge.dispute.created",
)


def fetch_current(stripe, event_type: str, obj: dict) -> dict:
    """Re-``retrieve`` the object so handlers never act on stale payloads
    (webhooks can arrive out of order). The fake has nothing fresher than the
    payload, so it is returned as is."""
    if is_fake(stripe) or not obj.get("id"):
        return obj
    try:
        if event_type.startswith("checkout.session."):
            return as_dict(stripe.v1.checkout.sessions.retrieve(obj["id"], params={"expand": ["subscription"]}))
        if event_type.startswith("customer.subscription.") and event_type != "customer.subscription.deleted":
            return as_dict(stripe.v1.subscriptions.retrieve(obj["id"]))
        if event_type.startswith("invoice."):
            return as_dict(stripe.v1.invoices.retrieve(obj["id"]))
        if event_type == "charge.refunded":
            return as_dict(stripe.v1.charges.retrieve(obj["id"]))
    except Exception as err:  # pragma: no cover - network
        log.warning("retrieve for %s %s failed, using the payload: %s", event_type, obj.get("id"), err)
    return obj


def handle_event(session, stripe, event_type: str, obj, event_created: int | None = None) -> str:
    """Dispatch one Stripe event; unknown types are ``ignored``."""
    obj = as_dict(obj)
    if event_type not in HANDLED:
        return "ignored"
    obj = fetch_current(stripe, event_type, obj)
    if event_type in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        return handle_checkout_completed(session, stripe, obj)
    if event_type == "checkout.session.expired":
        return handle_checkout_expired(session, obj)
    if event_type.startswith("customer.subscription."):
        return handle_subscription_event(session, stripe, obj, deleted=event_type.endswith(".deleted"), event_created=event_created)
    if event_type == "invoice.paid":
        return handle_invoice_paid(session, stripe, obj)
    if event_type == "invoice.payment_failed":
        return handle_invoice_failed(session, obj)
    if event_type == "charge.refunded":
        return handle_charge_refunded(session, obj)
    if event_type == "charge.dispute.created":
        return handle_dispute_created(session, obj)
    return "ignored"  # pragma: no cover
