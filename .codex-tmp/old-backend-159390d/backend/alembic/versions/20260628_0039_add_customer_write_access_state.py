"""Add customer write access state

Revision ID: 20260628_0039
Revises: 20260627_0038
Create Date: 2026-06-28 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260628_0039"
down_revision: str | None = "20260627_0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "customer_telegram_subscriptions",
        sa.Column(
            "write_access_granted",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )
    op.add_column(
        "customer_telegram_subscriptions",
        sa.Column("write_access_granted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "customer_telegram_subscriptions",
        sa.Column("write_access_denied_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "customer_telegram_subscriptions",
        sa.Column("write_access_source", sa.String(length=100), nullable=True),
    )
    op.create_index(
        "ix_customer_telegram_subscriptions_write_access",
        "customer_telegram_subscriptions",
        ["write_access_granted", "service_opt_in"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_customer_telegram_subscriptions_write_access",
        table_name="customer_telegram_subscriptions",
    )
    op.drop_column("customer_telegram_subscriptions", "write_access_source")
    op.drop_column("customer_telegram_subscriptions", "write_access_denied_at")
    op.drop_column("customer_telegram_subscriptions", "write_access_granted_at")
    op.drop_column("customer_telegram_subscriptions", "write_access_granted")
