"""Add customer service notification deliveries

Revision ID: 20260605_0017
Revises: 20260604_0016
Create Date: 2026-06-05 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260605_0017"
down_revision: str | None = "20260604_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOTIFICATION_CHANNEL_ENUM = postgresql.ENUM(
    "telegram",
    "internal",
    name="notification_channel",
    create_type=False,
)
CUSTOMER_SERVICE_DELIVERY_STATUS_ENUM = postgresql.ENUM(
    "pending",
    "sent",
    "failed",
    "blocked",
    "skipped",
    name="customer_service_notification_delivery_status",
    create_type=False,
)


def upgrade() -> None:
    CUSTOMER_SERVICE_DELIVERY_STATUS_ENUM.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "customer_service_notification_deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("subscription_id", sa.Integer(), nullable=True),
        sa.Column("event_name", sa.String(length=100), nullable=False),
        sa.Column(
            "channel",
            NOTIFICATION_CHANNEL_ENUM,
            server_default="telegram",
            nullable=False,
        ),
        sa.Column(
            "status",
            CUSTOMER_SERVICE_DELIVERY_STATUS_ENUM,
            server_default="pending",
            nullable=False,
        ),
        sa.Column("telegram_message_id", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_after_seconds", sa.Integer(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["customer_telegram_subscriptions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_customer_service_notification_deliveries_user_id"),
        "customer_service_notification_deliveries",
        ["user_id"],
    )
    op.create_index(
        op.f("ix_customer_service_notification_deliveries_order_id"),
        "customer_service_notification_deliveries",
        ["order_id"],
    )
    op.create_index(
        op.f("ix_customer_service_notification_deliveries_subscription_id"),
        "customer_service_notification_deliveries",
        ["subscription_id"],
    )
    op.create_index(
        op.f("ix_customer_service_notification_deliveries_event_name"),
        "customer_service_notification_deliveries",
        ["event_name"],
    )
    op.create_index(
        op.f("ix_customer_service_notification_deliveries_channel"),
        "customer_service_notification_deliveries",
        ["channel"],
    )
    op.create_index(
        op.f("ix_customer_service_notification_deliveries_status"),
        "customer_service_notification_deliveries",
        ["status"],
    )
    op.create_index(
        op.f("ix_customer_service_notification_deliveries_created_at"),
        "customer_service_notification_deliveries",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_customer_service_notification_deliveries_created_at"),
        table_name="customer_service_notification_deliveries",
    )
    op.drop_index(
        op.f("ix_customer_service_notification_deliveries_status"),
        table_name="customer_service_notification_deliveries",
    )
    op.drop_index(
        op.f("ix_customer_service_notification_deliveries_channel"),
        table_name="customer_service_notification_deliveries",
    )
    op.drop_index(
        op.f("ix_customer_service_notification_deliveries_event_name"),
        table_name="customer_service_notification_deliveries",
    )
    op.drop_index(
        op.f("ix_customer_service_notification_deliveries_subscription_id"),
        table_name="customer_service_notification_deliveries",
    )
    op.drop_index(
        op.f("ix_customer_service_notification_deliveries_order_id"),
        table_name="customer_service_notification_deliveries",
    )
    op.drop_index(
        op.f("ix_customer_service_notification_deliveries_user_id"),
        table_name="customer_service_notification_deliveries",
    )
    op.drop_table("customer_service_notification_deliveries")
    CUSTOMER_SERVICE_DELIVERY_STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
