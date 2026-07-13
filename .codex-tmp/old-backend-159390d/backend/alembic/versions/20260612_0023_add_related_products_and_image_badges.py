"""Add related products and product image badges

Revision ID: 20260612_0023
Revises: 20260611_0022
Create Date: 2026-06-12 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260612_0023"
down_revision: str | None = "20260611_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRODUCT_IMAGE_BADGE_TYPE_ENUM = postgresql.ENUM(
    "none",
    "new",
    "sale",
    "hit",
    "exclusive",
    "custom",
    name="product_image_badge_type",
    create_type=False,
)


def upgrade() -> None:
    PRODUCT_IMAGE_BADGE_TYPE_ENUM.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "products",
        sa.Column(
            "image_badge_type",
            PRODUCT_IMAGE_BADGE_TYPE_ENUM,
            server_default="none",
            nullable=False,
        ),
    )
    op.add_column(
        "products",
        sa.Column("image_badge_text", sa.String(length=20), nullable=True),
    )

    op.create_table(
        "product_related_products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("related_product_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
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
            "product_id <> related_product_id",
            name="ck_product_related_products_not_self",
        ),
        sa.CheckConstraint(
            "position >= 0",
            name="ck_product_related_products_position_non_negative",
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["related_product_id"],
            ["products.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product_id",
            "related_product_id",
            name="uq_product_related_products_pair",
        ),
        sa.UniqueConstraint(
            "product_id",
            "position",
            name="uq_product_related_products_position",
        ),
    )
    op.create_index(
        op.f("ix_product_related_products_product_id"),
        "product_related_products",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_product_related_products_related_product_id"),
        "product_related_products",
        ["related_product_id"],
        unique=False,
    )
    op.create_index(
        "ix_product_related_products_product_position",
        "product_related_products",
        ["product_id", "position"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_product_related_products_product_position",
        table_name="product_related_products",
    )
    op.drop_index(
        op.f("ix_product_related_products_related_product_id"),
        table_name="product_related_products",
    )
    op.drop_index(
        op.f("ix_product_related_products_product_id"),
        table_name="product_related_products",
    )
    op.drop_table("product_related_products")
    op.drop_column("products", "image_badge_text")
    op.drop_column("products", "image_badge_type")
    PRODUCT_IMAGE_BADGE_TYPE_ENUM.drop(op.get_bind(), checkfirst=True)
