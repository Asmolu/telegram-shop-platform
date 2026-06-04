"""Add customer Telegram subscriptions

Revision ID: 20260604_0016
Revises: 20260602_0015
Create Date: 2026-06-04 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260604_0016"
down_revision: str | None = "20260602_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customer_telegram_subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_username", sa.String(length=255), nullable=True),
        sa.Column("telegram_first_name", sa.String(length=255), nullable=True),
        sa.Column("telegram_last_name", sa.String(length=255), nullable=True),
        sa.Column("chat_type", sa.String(length=32), server_default="unknown", nullable=False),
        sa.Column("has_chat", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("service_opt_in", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("marketing_opt_in", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("opt_in_source", sa.String(length=100), nullable=True),
        sa.Column("marketing_opted_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("marketing_opted_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("service_opted_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_stop_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_settings_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_delivery_error", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_customer_telegram_subscriptions_user_id"),
        sa.UniqueConstraint(
            "telegram_user_id",
            name="uq_customer_telegram_subscriptions_telegram_user_id",
        ),
    )
    op.create_index(
        "ix_customer_telegram_subscriptions_blocked_at",
        "customer_telegram_subscriptions",
        ["blocked_at"],
    )
    op.create_index(
        "ix_customer_telegram_subscriptions_consent",
        "customer_telegram_subscriptions",
        ["has_chat", "service_opt_in", "marketing_opt_in"],
    )
    op.create_index(
        "ix_customer_telegram_subscriptions_telegram_chat_id",
        "customer_telegram_subscriptions",
        ["telegram_chat_id"],
    )
    op.create_index(
        "ix_customer_telegram_subscriptions_telegram_user_id",
        "customer_telegram_subscriptions",
        ["telegram_user_id"],
    )
    op.create_index(
        "ix_customer_telegram_subscriptions_user_id",
        "customer_telegram_subscriptions",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_customer_telegram_subscriptions_user_id",
        table_name="customer_telegram_subscriptions",
    )
    op.drop_index(
        "ix_customer_telegram_subscriptions_telegram_user_id",
        table_name="customer_telegram_subscriptions",
    )
    op.drop_index(
        "ix_customer_telegram_subscriptions_telegram_chat_id",
        table_name="customer_telegram_subscriptions",
    )
    op.drop_index(
        "ix_customer_telegram_subscriptions_consent",
        table_name="customer_telegram_subscriptions",
    )
    op.drop_index(
        "ix_customer_telegram_subscriptions_blocked_at",
        table_name="customer_telegram_subscriptions",
    )
    op.drop_table("customer_telegram_subscriptions")
