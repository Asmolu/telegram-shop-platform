"""Add seller contact URLs

Revision ID: 20260706_0050
Revises: 20260705_0049
Create Date: 2026-07-06 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260706_0050"
down_revision: str | None = "20260705_0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "seller_payment_settings",
        sa.Column("seller_contact_telegram_url", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "seller_payment_settings",
        sa.Column("seller_contact_whatsapp_url", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "seller_payment_settings",
        sa.Column("seller_contact_instagram_url", sa.String(length=1024), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("seller_payment_settings", "seller_contact_instagram_url")
    op.drop_column("seller_payment_settings", "seller_contact_whatsapp_url")
    op.drop_column("seller_payment_settings", "seller_contact_telegram_url")
