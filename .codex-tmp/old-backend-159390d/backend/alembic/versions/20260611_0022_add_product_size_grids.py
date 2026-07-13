"""Add product size grids

Revision ID: 20260611_0022
Revises: 20260609_0021
Create Date: 2026-06-11 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260611_0022"
down_revision: str | None = "20260609_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRODUCT_SIZE_GRID_ENUM = postgresql.ENUM(
    "clothing_alpha",
    "shoes_ru",
    name="product_size_grid",
    create_type=False,
)


def upgrade() -> None:
    PRODUCT_SIZE_GRID_ENUM.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "products",
        sa.Column(
            "size_grid",
            PRODUCT_SIZE_GRID_ENUM,
            server_default="clothing_alpha",
            nullable=False,
        ),
    )
    op.add_column(
        "order_items",
        sa.Column(
            "variant_size_grid",
            PRODUCT_SIZE_GRID_ENUM,
            server_default="clothing_alpha",
            nullable=False,
        ),
    )
    op.create_index(
        "ix_product_variants_size_active_product",
        "product_variants",
        ["size", "is_active", "product_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_product_variants_size_active_product", table_name="product_variants")
    op.drop_column("order_items", "variant_size_grid")
    op.drop_column("products", "size_grid")
    PRODUCT_SIZE_GRID_ENUM.drop(op.get_bind(), checkfirst=True)
