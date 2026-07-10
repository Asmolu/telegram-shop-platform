"""Add channel-entry media and button-style history fields.

Revision ID: 20260710_0052
Revises: 20260710_0051
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260710_0052"
down_revision: str | None = "20260710_0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "telegram_channel_entry_messages",
        sa.Column("button_style", sa.String(length=16), server_default="default", nullable=False),
    )
    op.add_column(
        "telegram_channel_entry_messages",
        sa.Column("photo_paths", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
    )
    op.add_column(
        "telegram_channel_entry_messages",
        sa.Column(
            "telegram_media_message_ids",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("telegram_channel_entry_messages", "telegram_media_message_ids")
    op.drop_column("telegram_channel_entry_messages", "photo_paths")
    op.drop_column("telegram_channel_entry_messages", "button_style")
