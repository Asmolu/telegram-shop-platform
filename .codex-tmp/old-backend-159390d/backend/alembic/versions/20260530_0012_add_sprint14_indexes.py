"""Add Sprint 14 production indexes

Revision ID: 20260530_0012
Revises: 20260529_0011
Create Date: 2026-05-30 00:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260530_0012"
down_revision: str | None = "20260529_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS ix_products_created_at ON products (created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_orders_created_at ON orders (created_at)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notifications_created_at ON notifications (created_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_notifications_created_at")
    op.execute("DROP INDEX IF EXISTS ix_orders_created_at")
    op.execute("DROP INDEX IF EXISTS ix_products_created_at")
