"""Add return request tables

Revision ID: 20260701_0041
Revises: 20260701_0040
Create Date: 2026-07-01 00:00:01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260701_0041"
down_revision: str | None = "20260701_0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RETURN_REQUEST_STATUS_ENUM = postgresql.ENUM(
    "PENDING",
    "APPROVED",
    "REJECTED",
    name="return_request_status",
    create_type=False,
)


def upgrade() -> None:
    RETURN_REQUEST_STATUS_ENUM.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "return_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("return_number", sa.String(length=32), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            RETURN_REQUEST_STATUS_ENUM,
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by_user_id", sa.Integer(), nullable=True),
        sa.Column("decision_comment", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", name="uq_return_requests_order_id"),
    )
    op.create_index(
        "ix_return_requests_return_number",
        "return_requests",
        ["return_number"],
        unique=True,
    )
    op.create_index("ix_return_requests_order_id", "return_requests", ["order_id"])
    op.create_index("ix_return_requests_user_id", "return_requests", ["user_id"])
    op.create_index("ix_return_requests_status", "return_requests", ["status"])
    op.create_index("ix_return_requests_created_at", "return_requests", ["created_at"])

    op.create_table(
        "return_request_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("return_request_id", sa.Integer(), nullable=False),
        sa.Column("order_item_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("product_variant_id", sa.Integer(), nullable=True),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("product_brand", sa.String(length=120), nullable=True),
        sa.Column("sku", sa.String(length=100), nullable=True),
        sa.Column("size", sa.String(length=64), nullable=True),
        sa.Column("color", sa.String(length=64), nullable=True),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "quantity > 0",
            name="ck_return_request_items_quantity_positive",
        ),
        sa.CheckConstraint(
            "unit_price >= 0",
            name="ck_return_request_items_unit_price_non_negative",
        ),
        sa.ForeignKeyConstraint(["order_item_id"], ["order_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["product_variant_id"],
            ["product_variants.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["return_request_id"],
            ["return_requests.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "return_request_id",
            "order_item_id",
            name="uq_return_request_items_request_order_item",
        ),
    )
    op.create_index(
        "ix_return_request_items_return_request_id",
        "return_request_items",
        ["return_request_id"],
    )

    op.create_table(
        "return_request_attachments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("return_request_id", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("media_type", sa.String(length=20), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "media_type IN ('image', 'video')",
            name="ck_return_request_attachments_media_type",
        ),
        sa.CheckConstraint(
            "position >= 0",
            name="ck_return_request_attachments_position_non_negative",
        ),
        sa.CheckConstraint(
            "size_bytes >= 0",
            name="ck_return_request_attachments_size_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["return_request_id"],
            ["return_requests.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_return_request_attachments_return_request_id",
        "return_request_attachments",
        ["return_request_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_return_request_attachments_return_request_id",
        table_name="return_request_attachments",
    )
    op.drop_table("return_request_attachments")

    op.drop_index(
        "ix_return_request_items_return_request_id",
        table_name="return_request_items",
    )
    op.drop_table("return_request_items")

    op.drop_index("ix_return_requests_created_at", table_name="return_requests")
    op.drop_index("ix_return_requests_status", table_name="return_requests")
    op.drop_index("ix_return_requests_user_id", table_name="return_requests")
    op.drop_index("ix_return_requests_order_id", table_name="return_requests")
    op.drop_index("ix_return_requests_return_number", table_name="return_requests")
    op.drop_table("return_requests")
    RETURN_REQUEST_STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
