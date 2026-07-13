"""Add upload metadata and banners

Revision ID: 20260527_0003
Revises: 20260527_0002
Create Date: 2026-05-27 00:00:02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260527_0003"
down_revision: str | None = "20260527_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "product_images",
        sa.Column("original_filename", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "product_images",
        sa.Column("mime_type", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "product_images",
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
    )

    op.create_table(
        "banners",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("alt_text", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("banners")
    op.drop_column("product_images", "size_bytes")
    op.drop_column("product_images", "mime_type")
    op.drop_column("product_images", "original_filename")
