"""github_sponsors + github_events (GitHub Sponsors webhook, CONTRACT.md §5)

Revision ID: 0004
Revises: 0003
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has_table("github_sponsors"):
        op.create_table(
            "github_sponsors",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("login", sa.String(64), nullable=False, unique=True),
            sa.Column("node_id", sa.String(64)),
            sa.Column("name", sa.String(80)),
            sa.Column("avatar_url", sa.String(500)),
            sa.Column("html_url", sa.String(500)),
            sa.Column("tier_name", sa.String(120)),
            sa.Column("monthly_cents", sa.Integer, nullable=False, server_default="0"),
            sa.Column("one_time", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("privacy_level", sa.String(10), nullable=False, server_default="public"),
            sa.Column("status", sa.String(24), nullable=False, server_default="active"),
            sa.Column("started_at", sa.DateTime(timezone=True)),
            sa.Column("ended_at", sa.DateTime(timezone=True)),
            sa.Column("last_event_at", sa.DateTime(timezone=True)),
            sa.Column("raw", JSONB, nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_github_sponsors_status_privacy", "github_sponsors", ["status", "privacy_level"])
    if not _has_table("github_events"):
        op.create_table(
            "github_events",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("event", sa.String(40), nullable=False),
            sa.Column("action", sa.String(40)),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("status", sa.String(12), nullable=False, server_default="received"),
            sa.Column("error", sa.Text),
        )


def downgrade() -> None:
    if _has_table("github_events"):
        op.drop_table("github_events")
    if _has_table("github_sponsors"):
        op.drop_index("ix_github_sponsors_status_privacy", table_name="github_sponsors")
        op.drop_table("github_sponsors")
