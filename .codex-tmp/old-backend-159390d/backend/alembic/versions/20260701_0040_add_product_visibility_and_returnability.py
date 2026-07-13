"""Add product visibility and returnability

Revision ID: 20260701_0040
Revises: 20260628_0039
Create Date: 2026-07-01 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260701_0040"
down_revision: str | None = "20260628_0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("is_listed", sa.Boolean(), server_default="true", nullable=False),
    )
    op.add_column(
        "products",
        sa.Column("is_returnable", sa.Boolean(), server_default="true", nullable=False),
    )
    op.create_index("ix_products_is_listed", "products", ["is_listed"])

    op.add_column(
        "order_items",
        sa.Column("is_returnable", sa.Boolean(), server_default="true", nullable=False),
    )
    op.add_column(
        "orders",
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.execute(sa.text("UPDATE products SET is_listed = TRUE WHERE is_listed IS NULL"))
    op.execute(sa.text("UPDATE products SET is_returnable = TRUE WHERE is_returnable IS NULL"))
    op.execute(sa.text("UPDATE order_items SET is_returnable = TRUE WHERE is_returnable IS NULL"))


def downgrade() -> None:
    op.drop_column("orders", "delivered_at")
    op.drop_column("order_items", "is_returnable")
    op.drop_index("ix_products_is_listed", table_name="products")
    op.drop_column("products", "is_returnable")
    op.drop_column("products", "is_listed")
