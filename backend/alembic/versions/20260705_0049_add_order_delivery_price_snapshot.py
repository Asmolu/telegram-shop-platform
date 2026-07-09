"""Add order delivery price snapshot

Revision ID: 20260705_0049
Revises: 20260704_0048
Create Date: 2026-07-05 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260705_0049"
down_revision: str | None = "20260704_0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_enum e
                    JOIN pg_type t ON t.oid = e.enumtypid
                    WHERE t.typname = 'order_delivery_method'
                      AND e.enumlabel = 'PICKUP'
                ) THEN
                    ALTER TYPE order_delivery_method ADD VALUE 'PICKUP';
                END IF;
            END
            $$;
            """
        )
    op.add_column(
        "orders",
        sa.Column(
            "delivery_price",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0.00",
        ),
    )


def downgrade() -> None:
    op.drop_column("orders", "delivery_price")
