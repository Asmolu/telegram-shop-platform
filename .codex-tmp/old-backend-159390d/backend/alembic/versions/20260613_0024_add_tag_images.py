"""Add tag images

Revision ID: 20260613_0024
Revises: 20260612_0023
Create Date: 2026-06-13 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260613_0024"
down_revision: str | None = "20260612_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tags",
        sa.Column("image_path", sa.String(length=1024), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tags", "image_path")
