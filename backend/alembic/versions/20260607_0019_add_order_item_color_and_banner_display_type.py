"""Add order item color snapshot and banner display type

Revision ID: 20260607_0019
Revises: 20260605_0018
Create Date: 2026-06-07 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260607_0019"
down_revision: str | None = "20260605_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BANNER_DISPLAY_TYPE_ENUM = postgresql.ENUM(
    "horizontal",
    "vertical",
    "popup",
    "aggressive_popup",
    name="banner_display_type",
    create_type=False,
)


def upgrade() -> None:
    BANNER_DISPLAY_TYPE_ENUM.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "order_items",
        sa.Column("variant_color", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "banners",
        sa.Column(
            "display_type",
            BANNER_DISPLAY_TYPE_ENUM,
            server_default="horizontal",
            nullable=False,
        ),
    )
    op.create_index(op.f("ix_banners_display_type"), "banners", ["display_type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_banners_display_type"), table_name="banners")
    op.drop_column("banners", "display_type")
    op.drop_column("order_items", "variant_color")

    BANNER_DISPLAY_TYPE_ENUM.drop(op.get_bind(), checkfirst=True)
