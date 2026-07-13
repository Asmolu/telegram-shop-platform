"""Add manual SBP payments

Revision ID: 20260614_0027
Revises: 20260613_0026
Create Date: 2026-06-14 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260614_0027"
down_revision: str | None = "20260613_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MANUAL_PAYMENT_METHOD_ENUM = postgresql.ENUM(
    "SBP_PHONE",
    name="manual_payment_method",
    create_type=False,
)
MANUAL_PAYMENT_CURRENCY_ENUM = postgresql.ENUM(
    "RUB",
    name="manual_payment_currency",
    create_type=False,
)
MANUAL_PAYMENT_STATUS_ENUM = postgresql.ENUM(
    "PENDING",
    "SUBMITTED",
    "APPROVED",
    "REJECTED",
    "EXPIRED",
    "CANCELLED",
    name="manual_payment_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    MANUAL_PAYMENT_METHOD_ENUM.create(bind, checkfirst=True)
    MANUAL_PAYMENT_CURRENCY_ENUM.create(bind, checkfirst=True)
    MANUAL_PAYMENT_STATUS_ENUM.create(bind, checkfirst=True)

    op.create_table(
        "seller_payment_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("seller_phone_e164", sa.String(length=16), nullable=True),
        sa.Column("seller_phone_display", sa.String(length=24), nullable=True),
        sa.Column("seller_bank_name", sa.String(length=100), nullable=True),
        sa.Column("seller_recipient_name", sa.String(length=100), nullable=True),
        sa.Column(
            "is_manual_sbp_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "manual_payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column(
            "method",
            MANUAL_PAYMENT_METHOD_ENUM,
            server_default="SBP_PHONE",
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "currency",
            MANUAL_PAYMENT_CURRENCY_ENUM,
            server_default="RUB",
            nullable=False,
        ),
        sa.Column("seller_phone_e164", sa.String(length=16), nullable=False),
        sa.Column("seller_phone_display", sa.String(length=24), nullable=False),
        sa.Column("seller_bank_name", sa.String(length=100), nullable=True),
        sa.Column("seller_recipient_name", sa.String(length=100), nullable=True),
        sa.Column("payment_comment", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            MANUAL_PAYMENT_STATUS_ENUM,
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("receipt_image_path", sa.String(length=1024), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by_user_id", sa.Integer(), nullable=True),
        sa.Column("reject_reason", sa.String(length=500), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stock_released_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("amount > 0", name="ck_manual_payments_amount_positive"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["rejected_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", name="uq_manual_payments_order_id"),
    )
    op.create_index("ix_manual_payments_order_id", "manual_payments", ["order_id"])
    op.create_index("ix_manual_payments_status", "manual_payments", ["status"])
    op.create_index("ix_manual_payments_expires_at", "manual_payments", ["expires_at"])
    op.create_index(
        "ix_manual_payments_status_expires_at",
        "manual_payments",
        ["status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_manual_payments_status_expires_at", table_name="manual_payments")
    op.drop_index("ix_manual_payments_expires_at", table_name="manual_payments")
    op.drop_index("ix_manual_payments_status", table_name="manual_payments")
    op.drop_index("ix_manual_payments_order_id", table_name="manual_payments")
    op.drop_table("manual_payments")
    op.drop_table("seller_payment_settings")

    bind = op.get_bind()
    MANUAL_PAYMENT_STATUS_ENUM.drop(bind, checkfirst=True)
    MANUAL_PAYMENT_CURRENCY_ENUM.drop(bind, checkfirst=True)
    MANUAL_PAYMENT_METHOD_ENUM.drop(bind, checkfirst=True)
