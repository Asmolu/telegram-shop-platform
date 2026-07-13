"""Add configurable Look image badges.

Revision ID: 20260712_0055
Revises: 20260712_0054
Create Date: 2026-07-12 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260712_0055"
down_revision: str | None = "20260712_0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BADGE_TYPE = postgresql.ENUM(name="product_image_badge_type", create_type=False)
BADGE_COLOR = postgresql.ENUM(name="product_image_badge_color", create_type=False)
BADGE_POSITION = postgresql.ENUM(name="product_image_badge_position", create_type=False)


def upgrade() -> None:
    op.add_column(
        "looks",
        sa.Column("image_badge_type", BADGE_TYPE, nullable=False, server_default="none"),
    )
    op.add_column("looks", sa.Column("image_badge_text", sa.String(length=20), nullable=True))
    op.add_column("looks", sa.Column("image_badge_color", BADGE_COLOR, nullable=True))
    op.add_column("looks", sa.Column("image_badge_position", BADGE_POSITION, nullable=True))


def downgrade() -> None:
    op.drop_column("looks", "image_badge_position")
    op.drop_column("looks", "image_badge_color")
    op.drop_column("looks", "image_badge_text")
    op.drop_column("looks", "image_badge_type")
