"""The only place that builds a Stripe client (CONTRACT.md §11).

:func:`client` returns a configured ``stripe.StripeClient`` (restricted key,
pinned API version) or a :class:`FakeStripe` when ``STRIPE_SECRET_KEY`` is
empty (CI, local development without an account). Callers always go through
the ``v1`` namespace — ``client().v1.checkout.sessions.create(params=…,
options=…)`` — which both implementations expose, and never set
``stripe.api_key``.

The fake keeps what it creates in memory and otherwise returns plausible
objects. ``checkout.sessions.retrieve`` of a session it has not seen (another
process created it, e.g. the API vs. ``cli seed-completed``) is synthesised
from our ``checkout_sessions`` row as a *completed* session, so the webhook
code path runs unchanged.
"""
from __future__ import annotations

import uuid
from typing import Any

from .config import config


def as_dict(obj: Any) -> Any:
    """Plain dict/list view of a Stripe object (real SDK or fake)."""
    if isinstance(obj, _Obj):
        return obj.to_dict()
    if isinstance(obj, dict):
        return {k: as_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [as_dict(v) for v in obj]
    if hasattr(obj, "to_dict_recursive"):
        return as_dict(obj.to_dict_recursive())
    if hasattr(obj, "to_dict"):
        return as_dict(obj.to_dict())
    return obj


class _Obj(dict):
    """Dict with attribute access, like ``stripe.StripeObject``."""

    def __getattr__(self, name: str) -> Any:
        try:
            value = self[name]
        except KeyError as err:
            raise AttributeError(name) from err
        return _wrap(value)

    def __getitem__(self, key: str) -> Any:
        return _wrap(super().__getitem__(key))

    def get(self, key: str, default: Any = None) -> Any:
        return _wrap(super().get(key, default))

    def to_dict(self) -> dict:
        return {k: as_dict(v) for k, v in dict.items(self)}

    def to_dict_recursive(self) -> dict:
        return self.to_dict()


def _wrap(value: Any) -> Any:
    if isinstance(value, _Obj):
        return value
    if isinstance(value, dict):
        return _Obj(value)
    if isinstance(value, list):
        return [_wrap(v) for v in value]
    return value


def _fake_id(prefix: str) -> str:
    return f"{prefix}_fake_{uuid.uuid4().hex[:24]}"


class _ListObject(_Obj):
    pass


class _FakeService:
    """One resource of the fake: ``create`` / ``retrieve`` / ``list`` over an
    in-memory store, with a per-resource factory for plausible defaults."""

    def __init__(self, store: FakeStripe, prefix: str, defaults=None):
        self._store = store
        self._prefix = prefix
        self._defaults = defaults or (lambda params: {})
        self.objects: dict[str, dict] = {}
        self.calls: list[dict] = []

    def create(self, params: dict | None = None, options: dict | None = None) -> _Obj:
        params = dict(params or {})
        self.calls.append({"params": params, "options": dict(options or {})})
        obj = {"id": _fake_id(self._prefix), "object": self._prefix, "livemode": False}
        obj.update(self._defaults(params))
        obj.update(params)
        self.objects[obj["id"]] = obj
        return _Obj(obj)

    def retrieve(self, id: str, params: dict | None = None, options: dict | None = None) -> _Obj:
        obj = self.objects.get(id)
        if obj is None:
            obj = self._store.synthesize(self._prefix, id)
        return _Obj(obj)

    def update(self, id: str, params: dict | None = None, options: dict | None = None) -> _Obj:
        obj = self.objects.setdefault(id, {"id": id, "object": self._prefix})
        obj.update(params or {})
        return _Obj(obj)

    def list(self, params: dict | None = None, options: dict | None = None) -> _ListObject:
        params = params or {}
        rows = list(self.objects.values())
        keys = params.get("lookup_keys")
        if keys:
            rows = [r for r in rows if r.get("lookup_key") in set(keys)]
        return _ListObject({"object": "list", "data": rows, "has_more": False})


class _Namespace:
    def __init__(self, **services):
        for name, service in services.items():
            setattr(self, name, service)


class FakeStripe:
    """Stand-in for ``StripeClient`` when no key is configured."""

    is_fake = True

    def __init__(self) -> None:
        self.products = _FakeService(self, "prod")
        self.prices = _FakeService(self, "price", self._price_defaults)
        self.customers = _FakeService(self, "cus", lambda p: {"email": p.get("email")})
        self.subscriptions = _FakeService(self, "sub", self._subscription_defaults)
        self.payment_intents = _FakeService(self, "pi", lambda p: {"status": "succeeded"})
        self.charges = _FakeService(self, "ch", lambda p: {"refunded": False, "amount_refunded": 0})
        self.invoices = _FakeService(self, "in", lambda p: {"status": "paid"})
        self.checkout = _Namespace(sessions=_FakeService(self, "cs", self._session_defaults))
        self.billing_portal = _Namespace(sessions=_FakeService(self, "bps", self._portal_defaults))
        self.v1 = self

    # --- defaults -------------------------------------------------------- #
    @staticmethod
    def _price_defaults(params: dict) -> dict:
        return {"active": True, "currency": params.get("currency", "usd"), "type": "recurring" if params.get("recurring") else "one_time"}

    @staticmethod
    def _subscription_defaults(params: dict) -> dict:
        return {"status": "active", "cancel_at_period_end": False, "items": {"data": []}}

    @staticmethod
    def _session_defaults(params: dict) -> dict:
        sid = _fake_id("cs")
        return {
            "id": sid,
            "status": "open",
            "payment_status": "unpaid",
            "url": f"{config.payments_url}/success?cs={sid}",
            "amount_total": None,
            "currency": params.get("currency"),
            "customer": params.get("customer"),
            "customer_details": {"email": params.get("customer_email")},
            "payment_intent": None,
            "subscription": None,
            "invoice": None,
        }

    @staticmethod
    def _portal_defaults(params: dict) -> dict:
        return {"url": f"{config.payments_url}/me?portal=fake"}

    # --- helpers --------------------------------------------------------- #
    def synthesize(self, prefix: str, id: str) -> dict:
        """A plausible object for an id the fake never created."""
        if prefix == "cs":
            session = synthesize_completed_session(id)
            if session is not None:
                return session
        base = {"id": id, "object": prefix, "livemode": False}
        if prefix == "sub":
            base.update(self._subscription_defaults({}))
        elif prefix == "pi":
            base.update({"status": "succeeded", "amount": 0, "currency": config.fallback_currency()})
        elif prefix == "ch":
            base.update({"refunded": False, "amount_refunded": 0})
        elif prefix == "in":
            base.update({"status": "paid"})
        return base

    def construct_event(self, payload, sig_header, secret, tolerance: int = 300):  # pragma: no cover
        import stripe

        return stripe.Webhook.construct_event(payload, sig_header, secret, tolerance)


def synthesize_completed_session(stripe_session_id: str) -> dict | None:
    """Build a *completed* Checkout Session object from our
    ``checkout_sessions`` row (fake mode only)."""
    from sqlalchemy import select

    from .db import session_scope
    from .models import CheckoutSession, Customer, Product

    with session_scope() as session:
        row = session.scalar(select(CheckoutSession).where(CheckoutSession.stripe_session_id == stripe_session_id))
        if row is None:
            return None
        product = session.get(Product, row.product_id) if row.product_id else None
        customer = session.get(Customer, row.identity_id) if row.identity_id else None
        metadata = {"app": _slug(session, row.app_id), "kind": row.kind, "checkout_id": str(row.id)}
        if row.identity_id:
            metadata["identity_id"] = str(row.identity_id)
        email = row.email or (customer.email if customer else None) or "guest@example.com"
        stripe_customer = (customer.stripe_customer_id if customer else None) or _fake_id("cus")
        amount = row.amount
        if row.kind == "subscription" and product is not None:
            amount = int((product.amounts or {}).get(row.currency, 0))
        obj: dict[str, Any] = {
            "id": stripe_session_id,
            "object": "checkout.session",
            "livemode": False,
            "mode": "payment" if row.kind == "donation" else "subscription",
            "status": "complete",
            "payment_status": "paid",
            "client_reference_id": str(row.id),
            "metadata": metadata,
            "amount_total": amount,
            "currency": row.currency,
            "customer": stripe_customer,
            "customer_details": {"email": email, "name": row.display_name},
            "customer_email": row.email,
            "created": 0,
        }
        if row.kind == "donation":
            obj["payment_intent"] = _fake_id("pi")
            obj["subscription"] = None
        else:
            import time

            now = int(time.time())
            obj["payment_intent"] = None
            obj["invoice"] = _fake_id("in")
            obj["subscription"] = {
                "id": _fake_id("sub"),
                "object": "subscription",
                "status": "active",
                "customer": stripe_customer,
                "cancel_at_period_end": False,
                "canceled_at": None,
                "created": now,
                "current_period_start": now,
                "current_period_end": now + 30 * 86400,
                "metadata": metadata,
                "items": {
                    "data": [
                        {
                            "price": {"id": product.stripe_price_id if product else None, "lookup_key": product.lookup_key if product else None},
                            "current_period_start": now,
                            "current_period_end": now + 30 * 86400,
                        }
                    ]
                },
            }
        return obj


def _slug(session, app_id) -> str | None:
    from .models import App

    app = session.get(App, app_id)
    return app.slug if app else None


_client: Any = None


def client() -> Any:
    """Process-wide Stripe client (or the fake)."""
    global _client
    if _client is None:
        if config.stripe_fake:
            _client = FakeStripe()
        else:
            import stripe

            _client = stripe.StripeClient(config.stripe_secret_key, stripe_version=config.stripe_api_version)
    return _client


def reset() -> None:
    """Drop the cached client (tests)."""
    global _client
    _client = None


def is_fake(stripe: Any) -> bool:
    return bool(getattr(stripe, "is_fake", False))
