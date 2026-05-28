"""Add promo code tables

Revision ID: 20260527_0007
Revises: 20260527_0006
Create Date: 2026-05-27 00:00:06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260527_0007"
down_revision: str | None = "20260527_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DISCOUNT_TYPE_ENUM = postgresql.ENUM(
    "PERCENT",
    "FIXED",
    name="discount_type",
    create_type=False,
)


def upgrade() -> None:
    DISCOUNT_TYPE_ENUM.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "promo_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("discount_type", DISCOUNT_TYPE_ENUM, nullable=False),
        sa.Column("discount_value", sa.Numeric(12, 2), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("usage_limit", sa.Integer(), nullable=True),
        sa.Column("per_user_limit", sa.Integer(), nullable=True),
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
            "discount_value > 0",
            name="ck_promo_codes_discount_value_positive",
        ),
        sa.CheckConstraint(
            "usage_limit IS NULL OR usage_limit > 0",
            name="ck_promo_codes_usage_limit_positive",
        ),
        sa.CheckConstraint(
            "per_user_limit IS NULL OR per_user_limit > 0",
            name="ck_promo_codes_per_user_limit_positive",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_promo_codes_code"), "promo_codes", ["code"], unique=True)

    op.add_column("orders", sa.Column("promo_code_id", sa.Integer(), nullable=True))
    op.add_column("orders", sa.Column("promo_code_code", sa.String(length=64), nullable=True))
    op.create_index(
        op.f("ix_orders_promo_code_id"),
        "orders",
        ["promo_code_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_orders_promo_code_id_promo_codes"),
        "orders",
        "promo_codes",
        ["promo_code_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "coupon_usages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("promo_code_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column(
            "used_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["promo_code_id"], ["promo_codes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("promo_code_id", "order_id", name="uq_coupon_usages_promo_order"),
    )
    op.create_index(
        op.f("ix_coupon_usages_promo_code_id"),
        "coupon_usages",
        ["promo_code_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_coupon_usages_user_id"),
        "coupon_usages",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_coupon_usages_order_id"),
        "coupon_usages",
        ["order_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_coupon_usages_order_id"), table_name="coupon_usages")
    op.drop_index(op.f("ix_coupon_usages_user_id"), table_name="coupon_usages")
    op.drop_index(op.f("ix_coupon_usages_promo_code_id"), table_name="coupon_usages")
    op.drop_table("coupon_usages")
    op.drop_constraint(op.f("fk_orders_promo_code_id_promo_codes"), "orders", type_="foreignkey")
    op.drop_index(op.f("ix_orders_promo_code_id"), table_name="orders")
    op.drop_column("orders", "promo_code_code")
    op.drop_column("orders", "promo_code_id")
    op.drop_index(op.f("ix_promo_codes_code"), table_name="promo_codes")
    op.drop_table("promo_codes")
    DISCOUNT_TYPE_ENUM.drop(op.get_bind(), checkfirst=True)
