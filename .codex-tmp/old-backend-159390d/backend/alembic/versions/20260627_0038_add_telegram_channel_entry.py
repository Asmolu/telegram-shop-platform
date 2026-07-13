"""Add Telegram channel entry tables

Revision ID: 20260627_0038
Revises: 20260627_0037
Create Date: 2026-06-27 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260627_0038"
down_revision: str | None = "20260627_0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_channels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("chat_id", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_check_status", sa.String(length=64), nullable=True),
        sa.Column("last_check_error", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", name="uq_telegram_channels_chat_id"),
    )
    op.create_index(
        "ix_telegram_channels_chat_id",
        "telegram_channels",
        ["chat_id"],
        unique=True,
    )
    op.create_index(
        "ix_telegram_channels_created_by_user_id",
        "telegram_channels",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_telegram_channels_active_created",
        "telegram_channels",
        ["is_active", "created_at"],
        unique=False,
    )

    op.create_table(
        "telegram_channel_entry_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=True),
        sa.Column("chat_id", sa.String(length=255), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "button_text",
            sa.String(length=64),
            server_default="Открыть",
            nullable=False,
        ),
        sa.Column("button_url", sa.String(length=1024), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("is_pinned", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["telegram_channels.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_telegram_channel_entry_messages_channel_id",
        "telegram_channel_entry_messages",
        ["channel_id"],
        unique=False,
    )
    op.create_index(
        "ix_telegram_channel_entry_messages_chat_id",
        "telegram_channel_entry_messages",
        ["chat_id"],
        unique=False,
    )
    op.create_index(
        "ix_telegram_channel_entry_messages_created_by_user_id",
        "telegram_channel_entry_messages",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_telegram_channel_entry_messages_created",
        "telegram_channel_entry_messages",
        ["created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_telegram_channel_entry_messages_channel_created",
        "telegram_channel_entry_messages",
        ["channel_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_telegram_channel_entry_messages_channel_created",
        table_name="telegram_channel_entry_messages",
    )
    op.drop_index(
        "ix_telegram_channel_entry_messages_created",
        table_name="telegram_channel_entry_messages",
    )
    op.drop_index(
        "ix_telegram_channel_entry_messages_created_by_user_id",
        table_name="telegram_channel_entry_messages",
    )
    op.drop_index(
        "ix_telegram_channel_entry_messages_chat_id",
        table_name="telegram_channel_entry_messages",
    )
    op.drop_index(
        "ix_telegram_channel_entry_messages_channel_id",
        table_name="telegram_channel_entry_messages",
    )
    op.drop_table("telegram_channel_entry_messages")

    op.drop_index("ix_telegram_channels_active_created", table_name="telegram_channels")
    op.drop_index("ix_telegram_channels_created_by_user_id", table_name="telegram_channels")
    op.drop_index("ix_telegram_channels_chat_id", table_name="telegram_channels")
    op.drop_table("telegram_channels")
