"""Add product brand

Revision ID: 20260618_0030
Revises: 20260615_0029
Create Date: 2026-06-18 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260618_0030"
down_revision: str | None = "20260615_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("brand", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "brand")
