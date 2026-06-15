"""Add manual payment Telegram message references

Revision ID: 20260615_0029
Revises: 20260615_0028
Create Date: 2026-06-15 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260615_0029"
down_revision: str | None = "20260615_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "manual_payments",
        sa.Column("seller_telegram_chat_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "manual_payments",
        sa.Column("seller_telegram_message_id", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("manual_payments", "seller_telegram_message_id")
    op.drop_column("manual_payments", "seller_telegram_chat_id")
