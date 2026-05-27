"""Add product variants

Revision ID: 20260527_0004
Revises: 20260527_0003
Create Date: 2026-05-27 00:00:03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260527_0004"
down_revision: str | None = "20260527_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_variants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("size", sa.String(length=64), nullable=False),
        sa.Column("color", sa.String(length=64), nullable=True),
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("stock_quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reserved_quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "stock_quantity >= 0",
            name="ck_product_variants_stock_non_negative",
        ),
        sa.CheckConstraint(
            "reserved_quantity >= 0",
            name="ck_product_variants_reserved_non_negative",
        ),
        sa.CheckConstraint(
            "reserved_quantity <= stock_quantity",
            name="ck_product_variants_reserved_not_above_stock",
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_product_variants_product_id"),
        "product_variants",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_product_variants_sku"),
        "product_variants",
        ["sku"],
        unique=True,
    )
    op.create_index(
        "ix_product_variants_product_id_is_active",
        "product_variants",
        ["product_id", "is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_product_variants_product_id_is_active", table_name="product_variants")
    op.drop_index(op.f("ix_product_variants_sku"), table_name="product_variants")
    op.drop_index(op.f("ix_product_variants_product_id"), table_name="product_variants")
    op.drop_table("product_variants")
