"""Add notifications

Revision ID: 20260527_0010
Revises: 20260527_0009
Create Date: 2026-05-27 00:00:09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260527_0010"
down_revision: str | None = "20260527_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOTIFICATION_CHANNEL_ENUM = postgresql.ENUM(
    "telegram",
    "internal",
    name="notification_channel",
    create_type=False,
)
NOTIFICATION_STATUS_ENUM = postgresql.ENUM(
    "pending",
    "sent",
    "failed",
    name="notification_status",
    create_type=False,
)


def upgrade() -> None:
    NOTIFICATION_CHANNEL_ENUM.create(op.get_bind(), checkfirst=True)
    NOTIFICATION_STATUS_ENUM.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("type", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "channel",
            NOTIFICATION_CHANNEL_ENUM,
            server_default="internal",
            nullable=False,
        ),
        sa.Column(
            "status",
            NOTIFICATION_STATUS_ENUM,
            server_default="pending",
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_notifications_user_id"), "notifications", ["user_id"], unique=False)
    op.create_index(op.f("ix_notifications_type"), "notifications", ["type"], unique=False)
    op.create_index(
        op.f("ix_notifications_channel"),
        "notifications",
        ["channel"],
        unique=False,
    )
    op.create_index(op.f("ix_notifications_status"), "notifications", ["status"], unique=False)
    op.create_index(
        op.f("ix_notifications_created_at"),
        "notifications",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_notifications_created_at"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_status"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_channel"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_type"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_user_id"), table_name="notifications")
    op.drop_table("notifications")
    NOTIFICATION_STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
    NOTIFICATION_CHANNEL_ENUM.drop(op.get_bind(), checkfirst=True)
