"""Add product category assignments

Revision ID: 20260609_0021
Revises: 20260608_0020
Create Date: 2026-06-09 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260609_0021"
down_revision: str | None = "20260608_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
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
            "priority IN (1, 2, 3)",
            name="ck_product_categories_priority_range",
        ),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product_id",
            "category_id",
            name="uq_product_categories_product_category",
        ),
        sa.UniqueConstraint(
            "product_id",
            "priority",
            name="uq_product_categories_product_priority",
        ),
    )
    op.create_index(
        op.f("ix_product_categories_product_id"),
        "product_categories",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_product_categories_category_id"),
        "product_categories",
        ["category_id"],
        unique=False,
    )
    op.create_index(
        "ix_product_categories_category_priority",
        "product_categories",
        ["category_id", "priority"],
        unique=False,
    )
    op.execute(
        """
        INSERT INTO product_categories (product_id, category_id, priority, created_at, updated_at)
        SELECT id, category_id, 1, now(), now()
        FROM products
        WHERE category_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_product_categories_category_priority", table_name="product_categories")
    op.drop_index(op.f("ix_product_categories_category_id"), table_name="product_categories")
    op.drop_index(op.f("ix_product_categories_product_id"), table_name="product_categories")
    op.drop_table("product_categories")
