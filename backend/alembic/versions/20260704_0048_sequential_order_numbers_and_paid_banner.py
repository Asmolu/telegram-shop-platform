"""Sequential order numbers and paid confirmation banner

Revision ID: 20260704_0048
Revises: 20260703_0047
Create Date: 2026-07-04 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260704_0048"
down_revision: str | None = "20260703_0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    op.add_column(
        "orders",
        sa.Column("payment_success_banner_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "seller_payment_settings",
        sa.Column("payment_success_banner_image_path", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "seller_payment_settings",
        sa.Column(
            "payment_success_banner_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )

    if bind.dialect.name == "postgresql":
        op.execute(sa.text("CREATE SEQUENCE IF NOT EXISTS order_number_seq"))
        op.execute(
            sa.text(
                """
                DO $$
                DECLARE
                    order_count integer;
                BEGIN
                    SELECT COUNT(*) INTO order_count FROM orders;
                    IF order_count > 999999 THEN
                        RAISE EXCEPTION 'Cannot assign ORD-NNNNNN numbers to % orders', order_count;
                    END IF;
                END $$;
                """
            )
        )
        op.execute(
            sa.text(
                """
                UPDATE orders
                SET order_number = 'ORD-MIGRATING-' || id::text
                """
            )
        )
        op.execute(
            sa.text(
                """
                WITH numbered_orders AS (
                    SELECT
                        id,
                        row_number() OVER (ORDER BY created_at ASC, id ASC) AS seq
                    FROM orders
                )
                UPDATE orders
                SET order_number = 'ORD-' || lpad(numbered_orders.seq::text, 6, '0')
                FROM numbered_orders
                WHERE orders.id = numbered_orders.id
                """
            )
        )
        op.execute(
            sa.text(
                """
                SELECT setval(
                    'order_number_seq',
                    GREATEST((SELECT COUNT(*) FROM orders), 1),
                    (SELECT COUNT(*) FROM orders) > 0
                )
                """
            )
        )

    op.execute(
        sa.text(
            """
            UPDATE orders
            SET payment_success_banner_seen_at = COALESCE(
                manual_payments.approved_at,
                orders.updated_at,
                now()
            )
            FROM manual_payments
            WHERE manual_payments.order_id = orders.id
              AND manual_payments.status = 'APPROVED'
              AND orders.payment_success_banner_seen_at IS NULL
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_column("seller_payment_settings", "payment_success_banner_enabled")
    op.drop_column("seller_payment_settings", "payment_success_banner_image_path")
    op.drop_column("orders", "payment_success_banner_seen_at")

    if bind.dialect.name == "postgresql":
        op.execute(sa.text("DROP SEQUENCE IF EXISTS order_number_seq"))
