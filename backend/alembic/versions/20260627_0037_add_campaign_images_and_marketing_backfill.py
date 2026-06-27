"""Add customer campaign images and normalize Bot 1 marketing opt-in

Revision ID: 20260627_0037
Revises: 20260625_0036
Create Date: 2026-06-27 00:00:00

The marketing consent update is an irreversible one-time normalization for
existing active Bot 1 private chats that had no explicit marketing opt-out.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260627_0037"
down_revision: str | None = "20260625_0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "broadcast_campaigns",
        sa.Column("image_path", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "broadcast_campaigns",
        sa.Column("image_original_filename", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "broadcast_campaigns",
        sa.Column("image_mime_type", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "broadcast_campaigns",
        sa.Column("image_size_bytes", sa.Integer(), nullable=True),
    )

    op.execute(
        """
        UPDATE customer_telegram_subscriptions
        SET
            marketing_opt_in = true,
            marketing_opted_in_at = COALESCE(marketing_opted_in_at, now()),
            marketing_opted_out_at = null,
            opt_in_source = COALESCE(opt_in_source, 'migration_existing_bot1_chat')
        WHERE has_chat = true
          AND blocked_at IS NULL
          AND marketing_opt_in = false
          AND marketing_opted_out_at IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("broadcast_campaigns", "image_size_bytes")
    op.drop_column("broadcast_campaigns", "image_mime_type")
    op.drop_column("broadcast_campaigns", "image_original_filename")
    op.drop_column("broadcast_campaigns", "image_path")
