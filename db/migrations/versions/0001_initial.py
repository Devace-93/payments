"""Initial schema: the whole payments data model (plan → Data model).

Idempotent on purpose: `python -m dbcore.cli upgrade` runs `create_all` first,
so every table/index is skipped when it already exists (fresh installs) and
created otherwise (databases that only ever ran Alembic).

Revision ID: 0001
Revises:
Create Date: 2026-11-01 12:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return sa.inspect(op.get_bind())


def _create_table(name: str, *args, **kwargs) -> None:
    if not _inspector().has_table(name):
        op.create_table(name, *args, **kwargs)


def _create_index(index_name: str, table_name: str, *args, **kwargs) -> None:
    existing = {ix["name"] for ix in _inspector().get_indexes(table_name)}
    existing |= {uc["name"] for uc in _inspector().get_unique_constraints(table_name)}
    if index_name not in existing:
        op.create_index(index_name, table_name, *args, **kwargs)


def _ts(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=nullable)


def _jsonb(name: str, default: str) -> sa.Column:
    return sa.Column(name, postgresql.JSONB(astext_type=sa.Text()), server_default=default, nullable=False)


def upgrade() -> None:
    _create_table(
        "apps",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        _jsonb("origins", "[]"),
        sa.Column("webhook_url", sa.String(length=2000), nullable=True),
        sa.Column("webhook_secret", sa.String(length=128), nullable=True),
        sa.Column("service_key_hash", sa.String(length=64), nullable=True),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_key_hash"),
    )
    _create_index(op.f("ix_apps_slug"), "apps", ["slug"], unique=True)

    _create_table(
        "products",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("app_id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(length=60), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("entitlement", sa.String(length=40), nullable=True),
        sa.Column("lookup_key", sa.String(length=120), nullable=False),
        sa.Column("stripe_product_id", sa.String(length=255), nullable=True),
        sa.Column("stripe_price_id", sa.String(length=255), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("unit_amount", sa.Integer(), nullable=True),
        _jsonb("amounts", "{}"),
        sa.Column("interval", sa.String(length=10), nullable=True),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("sort", sa.Integer(), server_default="0", nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.ForeignKeyConstraint(["app_id"], ["apps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("app_id", "key", name="uq_products_app_key"),
        sa.UniqueConstraint("lookup_key"),
        sa.UniqueConstraint("stripe_price_id"),
    )
    _create_index(op.f("ix_products_app_id"), "products", ["app_id"], unique=False)

    _create_table(
        "customers",
        sa.Column("identity_id", sa.UUID(), nullable=False),
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("handle", sa.String(length=32), nullable=True),
        sa.Column("name", sa.String(length=80), nullable=True),
        sa.Column("preferred_currency", sa.String(length=3), nullable=True),
        sa.Column("lang", sa.String(length=5), nullable=True),
        sa.Column("public_supporter", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("identity_id"),
        sa.UniqueConstraint("stripe_customer_id"),
    )
    _create_index(op.f("ix_customers_email"), "customers", ["email"], unique=False)
    _create_index(op.f("ix_customers_handle"), "customers", ["handle"], unique=False)

    _create_table(
        "subscriptions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("stripe_subscription_id", sa.String(length=255), nullable=False),
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=True),
        sa.Column("identity_id", sa.UUID(), nullable=False),
        sa.Column("app_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=True),
        sa.Column("entitlement", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stripe_updated", sa.Integer(), server_default="0", nullable=False),
        _jsonb("raw", "{}"),
        _ts("created_at"),
        _ts("updated_at"),
        sa.ForeignKeyConstraint(["app_id"], ["apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stripe_subscription_id"),
    )
    _create_index(op.f("ix_subscriptions_stripe_customer_id"), "subscriptions", ["stripe_customer_id"], unique=False)
    _create_index("ix_subscriptions_identity_app", "subscriptions", ["identity_id", "app_id"], unique=False)
    _create_index("ix_subscriptions_app_updated", "subscriptions", ["app_id", "updated_at"], unique=False)

    _create_table(
        "checkout_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("stripe_session_id", sa.String(length=255), nullable=True),
        sa.Column("app_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("identity_id", sa.UUID(), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("return_to", sa.String(length=2000), nullable=True),
        sa.Column("opener_origin", sa.String(length=255), nullable=True),
        sa.Column("public", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=True),
        sa.Column("message", sa.String(length=280), nullable=True),
        sa.Column("lang", sa.String(length=5), server_default="en", nullable=False),
        sa.Column("status", sa.String(length=12), server_default="created", nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.ForeignKeyConstraint(["app_id"], ["apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stripe_session_id"),
    )
    _create_index(op.f("ix_checkout_sessions_app_id"), "checkout_sessions", ["app_id"], unique=False)
    _create_index("ix_checkout_sessions_identity", "checkout_sessions", ["identity_id", "created_at"], unique=False)

    _create_table(
        "payments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("stripe_payment_intent_id", sa.String(length=255), nullable=True),
        sa.Column("stripe_checkout_session_id", sa.String(length=255), nullable=True),
        sa.Column("stripe_charge_id", sa.String(length=255), nullable=True),
        sa.Column("stripe_invoice_id", sa.String(length=255), nullable=True),
        sa.Column("app_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=True),
        sa.Column("subscription_id", sa.UUID(), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("amount_refunded", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="paid", nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("identity_id", sa.UUID(), nullable=True),
        sa.Column("display_name", sa.String(length=80), nullable=True),
        sa.Column("message", sa.String(length=280), nullable=True),
        sa.Column("public", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=10), server_default="stripe", nullable=False),
        _jsonb("raw", "{}"),
        _ts("created_at"),
        _ts("updated_at"),
        sa.ForeignKeyConstraint(["app_id"], ["apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stripe_payment_intent_id"),
        sa.UniqueConstraint("stripe_invoice_id"),
    )
    _create_index(op.f("ix_payments_stripe_checkout_session_id"), "payments", ["stripe_checkout_session_id"], unique=False)
    _create_index(op.f("ix_payments_stripe_charge_id"), "payments", ["stripe_charge_id"], unique=False)
    _create_index("ix_payments_identity_created", "payments", ["identity_id", "created_at"], unique=False)
    _create_index("ix_payments_app_public_status", "payments", ["app_id", "public", "status"], unique=False)

    _create_table(
        "claim_codes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("payment_id", sa.UUID(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_by", sa.UUID(), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        _ts("created_at"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash"),
        sa.UniqueConstraint("payment_id"),
    )

    _create_table(
        "stripe_events",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=80), nullable=False),
        sa.Column("stripe_created", sa.Integer(), nullable=True),
        _ts("received_at"),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=12), server_default="received", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    _create_table(
        "outbox",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("app_id", sa.UUID(), nullable=True),
        _jsonb("payload", "{}"),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="pending", nullable=False),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        _ts("created_at"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["app_id"], ["apps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_index("ix_outbox_status_due", "outbox", ["status", "next_attempt_at"], unique=False)
    _create_index("ix_outbox_kind_app", "outbox", ["kind", "app_id"], unique=False)


def downgrade() -> None:
    for table in (
        "outbox",
        "stripe_events",
        "claim_codes",
        "payments",
        "checkout_sessions",
        "subscriptions",
        "customers",
        "products",
        "apps",
    ):
        op.drop_table(table)
