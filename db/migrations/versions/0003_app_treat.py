"""apps.treat (coffee|beer wording for donations)

Revision ID: 0003
Revises: 0002
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    if not _has_column("apps", "treat"):
        op.add_column("apps", sa.Column("treat", sa.String(16), nullable=False, server_default="coffee"))


def downgrade() -> None:
    if _has_column("apps", "treat"):
        op.drop_column("apps", "treat")
