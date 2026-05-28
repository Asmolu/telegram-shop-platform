"""Extend banners for seller panel

Revision ID: 20260527_0009
Revises: 20260527_0008
Create Date: 2026-05-27 00:00:08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260527_0009"
down_revision: str | None = "20260527_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BANNER_TARGET_TYPE_ENUM = postgresql.ENUM(
    "product",
    "category",
    "promo",
    "external_url",
    name="banner_target_type",
    create_type=False,
)


def upgrade() -> None:
    BANNER_TARGET_TYPE_ENUM.create(op.get_bind(), checkfirst=True)

    op.add_column("banners", sa.Column("title", sa.String(length=255), nullable=True))
    op.add_column("banners", sa.Column("subtitle", sa.String(length=500), nullable=True))
    op.add_column("banners", sa.Column("target_type", BANNER_TARGET_TYPE_ENUM, nullable=True))
    op.add_column("banners", sa.Column("target_id", sa.Integer(), nullable=True))
    op.add_column("banners", sa.Column("external_url", sa.String(length=2048), nullable=True))
    op.add_column(
        "banners",
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "banners",
        sa.Column("is_active", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column("banners", sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("banners", sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "banners",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.execute(
        "UPDATE banners SET title = COALESCE(NULLIF(alt_text, ''), original_filename, 'Banner')"
    )
    op.alter_column("banners", "title", existing_type=sa.String(length=255), nullable=False)

    op.create_index(op.f("ix_banners_target_type"), "banners", ["target_type"], unique=False)
    op.create_index(op.f("ix_banners_target_id"), "banners", ["target_id"], unique=False)
    op.create_index(op.f("ix_banners_is_active"), "banners", ["is_active"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_banners_is_active"), table_name="banners")
    op.drop_index(op.f("ix_banners_target_id"), table_name="banners")
    op.drop_index(op.f("ix_banners_target_type"), table_name="banners")
    op.drop_column("banners", "updated_at")
    op.drop_column("banners", "ends_at")
    op.drop_column("banners", "starts_at")
    op.drop_column("banners", "is_active")
    op.drop_column("banners", "position")
    op.drop_column("banners", "external_url")
    op.drop_column("banners", "target_id")
    op.drop_column("banners", "target_type")
    op.drop_column("banners", "subtitle")
    op.drop_column("banners", "title")
    BANNER_TARGET_TYPE_ENUM.drop(op.get_bind(), checkfirst=True)
