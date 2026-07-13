"""Add configurable product image badge appearance

Revision ID: 20260618_0031
Revises: 20260618_0030
Create Date: 2026-06-18 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260618_0031"
down_revision: str | None = "20260618_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRODUCT_IMAGE_BADGE_COLOR_ENUM = postgresql.ENUM(
    "purple",
    "pink",
    "red",
    "orange",
    "blue",
    "green",
    "black",
    "white",
    name="product_image_badge_color",
    create_type=False,
)

PRODUCT_IMAGE_BADGE_POSITION_ENUM = postgresql.ENUM(
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
    name="product_image_badge_position",
    create_type=False,
)


def upgrade() -> None:
    PRODUCT_IMAGE_BADGE_COLOR_ENUM.create(op.get_bind(), checkfirst=True)
    PRODUCT_IMAGE_BADGE_POSITION_ENUM.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "products",
        sa.Column("image_badge_color", PRODUCT_IMAGE_BADGE_COLOR_ENUM, nullable=True),
    )
    op.add_column(
        "products",
        sa.Column("image_badge_position", PRODUCT_IMAGE_BADGE_POSITION_ENUM, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("products", "image_badge_position")
    op.drop_column("products", "image_badge_color")
    PRODUCT_IMAGE_BADGE_POSITION_ENUM.drop(op.get_bind(), checkfirst=True)
    PRODUCT_IMAGE_BADGE_COLOR_ENUM.drop(op.get_bind(), checkfirst=True)
