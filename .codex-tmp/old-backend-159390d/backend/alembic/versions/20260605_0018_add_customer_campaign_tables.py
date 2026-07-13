"""Add customer campaign notification tables

Revision ID: 20260605_0018
Revises: 20260605_0017
Create Date: 2026-06-05 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260605_0018"
down_revision: str | None = "20260605_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOTIFICATION_CHANNEL_ENUM = postgresql.ENUM(
    "telegram",
    "internal",
    name="notification_channel",
    create_type=False,
)
NOTIFICATION_TEMPLATE_CATEGORY_ENUM = postgresql.ENUM(
    "service",
    "marketing",
    name="notification_template_category",
    create_type=False,
)
BROADCAST_CAMPAIGN_TYPE_ENUM = postgresql.ENUM(
    "service",
    "marketing",
    name="broadcast_campaign_type",
    create_type=False,
)
BROADCAST_CAMPAIGN_STATUS_ENUM = postgresql.ENUM(
    "draft",
    "scheduled",
    "sending",
    "paused",
    "completed",
    "cancelled",
    "failed",
    name="broadcast_campaign_status",
    create_type=False,
)
BROADCAST_DELIVERY_STATUS_ENUM = postgresql.ENUM(
    "pending",
    "sending",
    "sent",
    "failed",
    "skipped",
    "blocked",
    "rate_limited",
    name="broadcast_delivery_status",
    create_type=False,
)


def upgrade() -> None:
    NOTIFICATION_TEMPLATE_CATEGORY_ENUM.create(op.get_bind(), checkfirst=True)
    BROADCAST_CAMPAIGN_TYPE_ENUM.create(op.get_bind(), checkfirst=True)
    BROADCAST_CAMPAIGN_STATUS_ENUM.create(op.get_bind(), checkfirst=True)
    BROADCAST_DELIVERY_STATUS_ENUM.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "notification_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=150), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", NOTIFICATION_TEMPLATE_CATEGORY_ENUM, nullable=False),
        sa.Column(
            "channel",
            NOTIFICATION_CHANNEL_ENUM,
            server_default="telegram",
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("body_template", sa.Text(), nullable=False),
        sa.Column("parse_mode", sa.String(length=32), nullable=True),
        sa.Column(
            "allowed_variables",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_notification_templates_key"),
        "notification_templates",
        ["key"],
        unique=True,
    )
    op.create_index(
        op.f("ix_notification_templates_category"),
        "notification_templates",
        ["category"],
    )
    op.create_index(
        op.f("ix_notification_templates_channel"),
        "notification_templates",
        ["channel"],
    )
    op.create_index(
        op.f("ix_notification_templates_is_active"),
        "notification_templates",
        ["is_active"],
    )
    op.create_index(
        op.f("ix_notification_templates_created_by_user_id"),
        "notification_templates",
        ["created_by_user_id"],
    )
    op.create_index(
        op.f("ix_notification_templates_updated_by_user_id"),
        "notification_templates",
        ["updated_by_user_id"],
    )

    op.create_table(
        "broadcast_campaigns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("type", BROADCAST_CAMPAIGN_TYPE_ENUM, nullable=False),
        sa.Column(
            "status",
            BROADCAST_CAMPAIGN_STATUS_ENUM,
            server_default="draft",
            nullable=False,
        ),
        sa.Column(
            "audience_filter",
            sa.JSON(),
            server_default=sa.text("'{}'::json"),
            nullable=False,
        ),
        sa.Column(
            "recipient_count_estimate",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("recipient_count_final", sa.Integer(), nullable=True),
        sa.Column("message_title", sa.String(length=255), nullable=True),
        sa.Column("message_body", sa.Text(), nullable=False),
        sa.Column("parse_mode", sa.String(length=32), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("approved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("cancelled_by_user_id", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cancelled_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["notification_templates.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_broadcast_campaigns_template_id"),
        "broadcast_campaigns",
        ["template_id"],
    )
    op.create_index(op.f("ix_broadcast_campaigns_type"), "broadcast_campaigns", ["type"])
    op.create_index(op.f("ix_broadcast_campaigns_status"), "broadcast_campaigns", ["status"])
    op.create_index(
        "ix_broadcast_campaigns_status_type",
        "broadcast_campaigns",
        ["status", "type"],
    )
    op.create_index(
        "ix_broadcast_campaigns_scheduled_at",
        "broadcast_campaigns",
        ["scheduled_at"],
    )
    op.create_index(
        op.f("ix_broadcast_campaigns_created_by_user_id"),
        "broadcast_campaigns",
        ["created_by_user_id"],
    )
    op.create_index(
        op.f("ix_broadcast_campaigns_approved_by_user_id"),
        "broadcast_campaigns",
        ["approved_by_user_id"],
    )
    op.create_index(
        op.f("ix_broadcast_campaigns_cancelled_by_user_id"),
        "broadcast_campaigns",
        ["cancelled_by_user_id"],
    )

    op.create_table(
        "broadcast_deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            BROADCAST_DELIVERY_STATUS_ENUM,
            server_default="pending",
            nullable=False,
        ),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("telegram_message_id", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_after_seconds", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(["campaign_id"], ["broadcast_campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["customer_telegram_subscriptions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_id",
            "subscription_id",
            name="uq_broadcast_deliveries_campaign_subscription",
        ),
    )
    op.create_index(
        op.f("ix_broadcast_deliveries_campaign_id"),
        "broadcast_deliveries",
        ["campaign_id"],
    )
    op.create_index(op.f("ix_broadcast_deliveries_user_id"), "broadcast_deliveries", ["user_id"])
    op.create_index(
        op.f("ix_broadcast_deliveries_subscription_id"),
        "broadcast_deliveries",
        ["subscription_id"],
    )
    op.create_index(op.f("ix_broadcast_deliveries_status"), "broadcast_deliveries", ["status"])
    op.create_index(
        "ix_broadcast_deliveries_campaign_status",
        "broadcast_deliveries",
        ["campaign_id", "status"],
    )
    op.create_index(
        "ix_broadcast_deliveries_status_next_attempt_at",
        "broadcast_deliveries",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_broadcast_deliveries_status_next_attempt_at",
        table_name="broadcast_deliveries",
    )
    op.drop_index("ix_broadcast_deliveries_campaign_status", table_name="broadcast_deliveries")
    op.drop_index(op.f("ix_broadcast_deliveries_status"), table_name="broadcast_deliveries")
    op.drop_index(
        op.f("ix_broadcast_deliveries_subscription_id"),
        table_name="broadcast_deliveries",
    )
    op.drop_index(op.f("ix_broadcast_deliveries_user_id"), table_name="broadcast_deliveries")
    op.drop_index(op.f("ix_broadcast_deliveries_campaign_id"), table_name="broadcast_deliveries")
    op.drop_table("broadcast_deliveries")

    op.drop_index(
        op.f("ix_broadcast_campaigns_cancelled_by_user_id"),
        table_name="broadcast_campaigns",
    )
    op.drop_index(
        op.f("ix_broadcast_campaigns_approved_by_user_id"),
        table_name="broadcast_campaigns",
    )
    op.drop_index(
        op.f("ix_broadcast_campaigns_created_by_user_id"),
        table_name="broadcast_campaigns",
    )
    op.drop_index("ix_broadcast_campaigns_scheduled_at", table_name="broadcast_campaigns")
    op.drop_index("ix_broadcast_campaigns_status_type", table_name="broadcast_campaigns")
    op.drop_index(op.f("ix_broadcast_campaigns_status"), table_name="broadcast_campaigns")
    op.drop_index(op.f("ix_broadcast_campaigns_type"), table_name="broadcast_campaigns")
    op.drop_index(op.f("ix_broadcast_campaigns_template_id"), table_name="broadcast_campaigns")
    op.drop_table("broadcast_campaigns")

    op.drop_index(
        op.f("ix_notification_templates_updated_by_user_id"),
        table_name="notification_templates",
    )
    op.drop_index(
        op.f("ix_notification_templates_created_by_user_id"),
        table_name="notification_templates",
    )
    op.drop_index(op.f("ix_notification_templates_is_active"), table_name="notification_templates")
    op.drop_index(op.f("ix_notification_templates_channel"), table_name="notification_templates")
    op.drop_index(op.f("ix_notification_templates_category"), table_name="notification_templates")
    op.drop_index(op.f("ix_notification_templates_key"), table_name="notification_templates")
    op.drop_table("notification_templates")

    BROADCAST_DELIVERY_STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
    BROADCAST_CAMPAIGN_STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
    BROADCAST_CAMPAIGN_TYPE_ENUM.drop(op.get_bind(), checkfirst=True)
    NOTIFICATION_TEMPLATE_CATEGORY_ENUM.drop(op.get_bind(), checkfirst=True)
