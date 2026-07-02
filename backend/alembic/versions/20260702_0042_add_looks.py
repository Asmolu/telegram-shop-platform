"""Add looks tables

Revision ID: 20260702_0042
Revises: 20260701_0041
Create Date: 2026-07-02 00:00:01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260702_0042"
down_revision: str | None = "20260701_0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LOOK_STATUS_ENUM = postgresql.ENUM(
    "DRAFT",
    "ACTIVE",
    "ARCHIVED",
    name="look_status",
    create_type=False,
)


def upgrade() -> None:
    LOOK_STATUS_ENUM.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "looks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            LOOK_STATUS_ENUM,
            server_default="DRAFT",
            nullable=False,
        ),
        sa.Column("is_listed", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("search_priority", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "search_priority IN (1, 2, 3)",
            name="ck_looks_search_priority_range",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_looks_slug", "looks", ["slug"], unique=True)
    op.create_index("ix_looks_status", "looks", ["status"])
    op.create_index("ix_looks_is_listed", "looks", ["is_listed"])
    op.create_index("ix_looks_search_priority", "looks", ["search_priority"])
    op.create_index("ix_looks_created_at", "looks", ["created_at"])
    op.create_index(
        "ix_looks_public_listing",
        "looks",
        ["status", "is_listed", "search_priority", "created_at"],
    )

    op.create_table(
        "look_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("look_id", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("alt_text", sa.String(length=255), nullable=True),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "position >= 0",
            name="ck_look_images_position_non_negative",
        ),
        sa.ForeignKeyConstraint(["look_id"], ["looks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_look_images_look_id", "look_images", ["look_id"])

    op.create_table(
        "look_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("look_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("quantity", sa.Integer(), server_default="1", nullable=False),
        sa.Column("is_default_selected", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("quantity > 0", name="ck_look_items_quantity_positive"),
        sa.ForeignKeyConstraint(["look_id"], ["looks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("look_id", "product_id", name="uq_look_items_look_product"),
    )
    op.create_index("ix_look_items_look_id", "look_items", ["look_id"])
    op.create_index("ix_look_items_product_id", "look_items", ["product_id"])
    op.create_index("ix_look_items_look_position", "look_items", ["look_id", "position"])


def downgrade() -> None:
    op.drop_index("ix_look_items_look_position", table_name="look_items")
    op.drop_index("ix_look_items_product_id", table_name="look_items")
    op.drop_index("ix_look_items_look_id", table_name="look_items")
    op.drop_table("look_items")

    op.drop_index("ix_look_images_look_id", table_name="look_images")
    op.drop_table("look_images")

    op.drop_index("ix_looks_public_listing", table_name="looks")
    op.drop_index("ix_looks_created_at", table_name="looks")
    op.drop_index("ix_looks_search_priority", table_name="looks")
    op.drop_index("ix_looks_is_listed", table_name="looks")
    op.drop_index("ix_looks_status", table_name="looks")
    op.drop_index("ix_looks_slug", table_name="looks")
    op.drop_table("looks")
    LOOK_STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
