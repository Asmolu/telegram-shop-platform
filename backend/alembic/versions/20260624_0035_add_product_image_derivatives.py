"""add product image derivative paths

Revision ID: 20260624_0035
Revises: 20260624_0034
Create Date: 2026-06-24 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260624_0035"
down_revision: str | None = "20260624_0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "product_images",
        sa.Column("thumbnail_path", sa.String(length=1024), nullable=True),
    )
    op.add_column("product_images", sa.Column("card_path", sa.String(length=1024), nullable=True))
    op.add_column(
        "product_images",
        sa.Column("detail_path", sa.String(length=1024), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("product_images", "detail_path")
    op.drop_column("product_images", "card_path")
    op.drop_column("product_images", "thumbnail_path")
