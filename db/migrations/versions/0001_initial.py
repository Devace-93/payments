"""Initial schema: the whole accounts data model (CONTRACT.md → Data model).

Idempotent on purpose: `python -m dbcore.cli upgrade` runs `create_all` first,
so every table/index is skipped when it already exists (fresh installs) and
created otherwise (databases that only ever ran Alembic).

Revision ID: 0001
Revises:
Create Date: 2026-10-16 16:00:00
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


def upgrade() -> None:
    _create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("handle", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=True),
        sa.Column("avatar_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    _create_index(op.f("ix_users_handle"), "users", ["handle"], unique=True)

    _create_table(
        "identities",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("provider_user_id", sa.String(length=255), nullable=False),
        sa.Column("provider_email", sa.String(length=255), nullable=True),
        sa.Column("profile", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_identity_provider_user"),
    )
    _create_index(op.f("ix_identities_user_id"), "identities", ["user_id"], unique=False)

    _create_table(
        "sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("refresh_hash", sa.String(length=64), nullable=False),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)
    _create_index(op.f("ix_sessions_refresh_hash"), "sessions", ["refresh_hash"], unique=True)

    _create_table(
        "email_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("return_to", sa.String(length=2000), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_index(op.f("ix_email_tokens_token_hash"), "email_tokens", ["token_hash"], unique=True)
    _create_index("ix_email_tokens_user_kind", "email_tokens", ["user_id", "kind"], unique=False)

    _create_table(
        "avatars",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("content_type", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    _create_table(
        "outbox",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="pending", nullable=False),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_index(op.f("ix_outbox_user_id"), "outbox", ["user_id"], unique=False)
    _create_index("ix_outbox_status_due", "outbox", ["status", "next_attempt_at"], unique=False)


def downgrade() -> None:
    for table in ("outbox", "avatars", "email_tokens", "sessions", "identities", "users"):
        op.drop_table(table)
