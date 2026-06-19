"""Add EU footwear size grid

Revision ID: 20260619_0033
Revises: 20260619_0032
Create Date: 2026-06-19 00:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260619_0033"
down_revision: str | None = "20260619_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE product_size_grid ADD VALUE IF NOT EXISTS 'shoes_eu'")


def downgrade() -> None:
    # PostgreSQL cannot drop enum values without rebuilding dependent columns.
    # Keep this downgrade intentionally data-safe and non-destructive.
    pass
