"""Add category images

Revision ID: 20260613_0026
Revises: 20260613_0025
Create Date: 2026-06-13 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260613_0026"
down_revision: str | None = "20260613_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "categories",
        sa.Column("image_path", sa.String(length=1024), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("categories", "image_path")
