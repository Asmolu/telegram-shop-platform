"""Add Look source grouping to cart and order items

Revision ID: 20260703_0045
Revises: 20260702_0044
Create Date: 2026-07-03 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260703_0045"
down_revision: str | None = "20260702_0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_cart_items_cart_variant", "cart_items", type_="unique")
    op.add_column("cart_items", sa.Column("source_type", sa.String(length=32), nullable=True))
    op.add_column("cart_items", sa.Column("source_look_id", sa.Integer(), nullable=True))
    op.add_column("cart_items", sa.Column("source_look_slug", sa.String(length=255), nullable=True))
    op.add_column(
        "cart_items",
        sa.Column("source_look_title", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "cart_items",
        sa.Column("source_look_image_url", sa.String(length=1024), nullable=True),
    )
    op.add_column("cart_items", sa.Column("source_group_id", sa.String(length=64), nullable=True))
    op.create_foreign_key(
        "fk_cart_items_source_look_id_looks",
        "cart_items",
        "looks",
        ["source_look_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_cart_items_source_group_id", "cart_items", ["source_group_id"])
    op.create_index("ix_cart_items_source_look_id", "cart_items", ["source_look_id"])
    op.create_index(
        "uq_cart_items_normal_cart_variant",
        "cart_items",
        ["cart_id", "product_variant_id"],
        unique=True,
        postgresql_where=sa.text("source_type IS NULL AND source_group_id IS NULL"),
        sqlite_where=sa.text("source_type IS NULL AND source_group_id IS NULL"),
    )

    op.add_column("order_items", sa.Column("source_type", sa.String(length=32), nullable=True))
    op.add_column("order_items", sa.Column("source_look_id", sa.Integer(), nullable=True))
    op.add_column(
        "order_items",
        sa.Column("source_look_slug", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "order_items",
        sa.Column("source_look_title", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "order_items",
        sa.Column("source_look_image_url", sa.String(length=1024), nullable=True),
    )
    op.add_column("order_items", sa.Column("source_group_id", sa.String(length=64), nullable=True))
    op.create_foreign_key(
        "fk_order_items_source_look_id_looks",
        "order_items",
        "looks",
        ["source_look_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_order_items_source_group_id", "order_items", ["source_group_id"])
    op.create_index("ix_order_items_source_look_id", "order_items", ["source_look_id"])


def downgrade() -> None:
    op.drop_index("ix_order_items_source_look_id", table_name="order_items")
    op.drop_index("ix_order_items_source_group_id", table_name="order_items")
    op.drop_constraint(
        "fk_order_items_source_look_id_looks",
        "order_items",
        type_="foreignkey",
    )
    op.drop_column("order_items", "source_group_id")
    op.drop_column("order_items", "source_look_image_url")
    op.drop_column("order_items", "source_look_title")
    op.drop_column("order_items", "source_look_slug")
    op.drop_column("order_items", "source_look_id")
    op.drop_column("order_items", "source_type")

    op.drop_index("uq_cart_items_normal_cart_variant", table_name="cart_items")
    op.drop_index("ix_cart_items_source_look_id", table_name="cart_items")
    op.drop_index("ix_cart_items_source_group_id", table_name="cart_items")
    op.drop_constraint(
        "fk_cart_items_source_look_id_looks",
        "cart_items",
        type_="foreignkey",
    )
    op.drop_column("cart_items", "source_group_id")
    op.drop_column("cart_items", "source_look_image_url")
    op.drop_column("cart_items", "source_look_title")
    op.drop_column("cart_items", "source_look_slug")
    op.drop_column("cart_items", "source_look_id")
    op.drop_column("cart_items", "source_type")
    op.create_unique_constraint(
        "uq_cart_items_cart_variant",
        "cart_items",
        ["cart_id", "product_variant_id"],
    )
