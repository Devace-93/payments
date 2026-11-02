"""SQLAlchemy models — the canonical data model for payments (see the plan's
"Data model" and CONTRACT.md).

There is no local users table: ``customers.identity_id`` is the accounts JWT
``sub`` and the profile columns are mirrored from the claims on each session
call. ``apps`` and ``products`` mirror ``packages/shared/catalog.json``
(``cli sync-catalog``); their secrets (service key hash, webhook secret) are
set by ``cli app-key``. ``checkout_sessions`` are created before the Stripe
session (their id is the idempotency key). ``payments`` and ``subscriptions``
are what the Stripe webhooks maintain; ``claim_codes`` attach guest donations
to an identity later; ``stripe_events`` dedupes webhooks; ``outbox`` is the
transactional queue for mail and app push webhooks.

Secrets (claim codes, service keys) are stored as sha256 hashes only; the
webhook secret must be stored in clear because we sign with it.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)


def _ts(**kwargs) -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, **kwargs)


class App(Base):
    """One relying app (``retro``, ``3m4``…). Mirrors ``catalog.json``."""

    __tablename__ = "apps"

    id: Mapped[uuid.UUID] = _pk()
    slug: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    origins: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    icon: Mapped[str | None] = mapped_column(String(500))
    # Donation wording on the portal: "coffee" (default) or "beer".
    treat: Mapped[str] = mapped_column(String(16), nullable=False, default="coffee", server_default="coffee")
    # Per-app "Support <app>" Stripe product, created lazily on the first donation.
    stripe_donation_product_id: Mapped[str | None] = mapped_column(String(64))
    webhook_url: Mapped[str | None] = mapped_column(String(2000))
    webhook_secret: Mapped[str | None] = mapped_column(String(128))
    service_key_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts(onupdate=func.now())

    products: Mapped[list[Product]] = relationship(back_populates="app", cascade="all, delete-orphan")


class Product(Base):
    """A purchasable thing: a subscription plan of an app, or the global
    donation price of one currency (``kind=donation``, app ``3m4``)."""

    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("app_id", "key", name="uq_products_app_key"),)

    id: Mapped[uuid.UUID] = _pk()
    app_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(60), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # subscription | donation | one_time
    entitlement: Mapped[str | None] = mapped_column(String(40))
    lookup_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    stripe_product_id: Mapped[str | None] = mapped_column(String(255))
    stripe_price_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    currency: Mapped[str | None] = mapped_column(String(3))  # donation prices only
    unit_amount: Mapped[int | None] = mapped_column(Integer)  # null = custom amount
    amounts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    interval: Mapped[str | None] = mapped_column(String(10))  # month | year
    label: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    sort: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts(onupdate=func.now())

    app: Mapped[App] = relationship(back_populates="products")


class Customer(Base):
    """One row per accounts identity that touched payments. ``identity_id``
    is the JWT ``sub``; the profile is a mirror of the claims."""

    __tablename__ = "customers"

    identity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    handle: Mapped[str | None] = mapped_column(String(32), index=True)
    name: Mapped[str | None] = mapped_column(String(80))
    preferred_currency: Mapped[str | None] = mapped_column(String(3))
    lang: Mapped[str | None] = mapped_column(String(5))
    public_supporter: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    display_name: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts(onupdate=func.now())


class CheckoutSession(Base):
    """Our side of a Stripe Checkout Session. Created BEFORE the Stripe call;
    ``id`` is the idempotency key, ``client_reference_id`` and
    ``metadata.checkout_id``."""

    __tablename__ = "checkout_sessions"
    __table_args__ = (Index("ix_checkout_sessions_identity", "identity_id", "created_at"),)

    id: Mapped[uuid.UUID] = _pk()
    stripe_session_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    app_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # donation | subscription
    identity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    email: Mapped[str | None] = mapped_column(String(255))
    amount: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    return_to: Mapped[str | None] = mapped_column(String(2000))
    opener_origin: Mapped[str | None] = mapped_column(String(255))
    public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    display_name: Mapped[str | None] = mapped_column(String(80))
    message: Mapped[str | None] = mapped_column(String(280))
    lang: Mapped[str] = mapped_column(String(5), nullable=False, default="en", server_default="en")
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="created", server_default="created")
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts(onupdate=func.now())


class Payment(Base):
    """One money movement: a donation, a one-off purchase or a subscription
    invoice. Maintained by the Stripe webhook handlers."""

    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_identity_created", "identity_id", "created_at"),
        Index("ix_payments_app_public_status", "app_id", "public", "status"),
    )

    id: Mapped[uuid.UUID] = _pk()
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String(255), index=True)
    stripe_charge_id: Mapped[str | None] = mapped_column(String(255), index=True)
    stripe_invoice_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    app_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"))
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("subscriptions.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # donation | one_time | invoice
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount_refunded: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="paid", server_default="paid")
    email: Mapped[str | None] = mapped_column(String(255))
    identity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    display_name: Mapped[str | None] = mapped_column(String(80))
    message: Mapped[str | None] = mapped_column(String(280))
    public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(10), nullable=False, default="stripe", server_default="stripe")
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts(onupdate=func.now())


class Subscription(Base):
    """Mirror of a Stripe subscription. ``status`` is Stripe's; entitlement is
    derived from it in ``dbcore.entitlements``."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("ix_subscriptions_identity_app", "identity_id", "app_id"),
        Index("ix_subscriptions_app_updated", "app_id", "updated_at"),
    )

    id: Mapped[uuid.UUID] = _pk()
    stripe_subscription_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), index=True)
    identity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    app_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"))
    entitlement: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stripe_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts(onupdate=func.now())


class ClaimCode(Base):
    """Single-use code that attaches a guest donation to an identity.
    Only the sha256 of the normalised code is stored."""

    __tablename__ = "claim_codes"

    id: Mapped[uuid.UUID] = _pk()
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    payment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    used_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _ts()


class StripeEvent(Base):
    """Insert-first dedupe of Stripe webhook deliveries."""

    __tablename__ = "stripe_events"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    type: Mapped[str] = mapped_column(String(80), nullable=False)
    stripe_created: Mapped[int | None] = mapped_column(Integer)
    received_at: Mapped[datetime] = _ts()
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="received", server_default="received")
    error: Mapped[str | None] = mapped_column(Text)


class Outbox(Base):
    """Transactional outbox: side effects written in the same transaction as
    the change that caused them, delivered by ``dbcore.worker``.

    ``kind``: ``email`` (payload ``template, to, lang, params``) or ``webhook``
    (payload ``app, event``; the signing secret is read from ``apps`` at send
    time). ``status``: pending (due at ``next_attempt_at``) | sending (claimed
    by a worker) | sent | failed (gave up) | skipped (mail disabled / no URL).
    """

    __tablename__ = "outbox"
    __table_args__ = (
        Index("ix_outbox_status_due", "status", "next_attempt_at"),
        Index("ix_outbox_kind_app", "kind", "app_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="email")
    app_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="pending", server_default="pending")
    last_error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = _ts()
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
