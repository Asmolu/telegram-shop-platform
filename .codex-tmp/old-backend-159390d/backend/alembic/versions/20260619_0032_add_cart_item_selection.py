"""Add cart item selection

Revision ID: 20260619_0032
Revises: 20260618_0031
Create Date: 2026-06-19 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260619_0032"
down_revision: str | None = "20260618_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cart_items",
        sa.Column(
            "is_selected",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("cart_items", "is_selected")
