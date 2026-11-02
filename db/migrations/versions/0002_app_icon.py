"""apps.icon + apps.stripe_donation_product_id

Revision ID: 0002
Revises: 0001
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    if not _has_column("apps", "icon"):
        op.add_column("apps", sa.Column("icon", sa.String(500), nullable=True))
    if not _has_column("apps", "stripe_donation_product_id"):
        op.add_column("apps", sa.Column("stripe_donation_product_id", sa.String(64), nullable=True))


def downgrade() -> None:
    if _has_column("apps", "stripe_donation_product_id"):
        op.drop_column("apps", "stripe_donation_product_id")
    if _has_column("apps", "icon"):
        op.drop_column("apps", "icon")
