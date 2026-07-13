"""Add reviews and favorites

Revision ID: 20260527_0008
Revises: 20260527_0007
Create Date: 2026-05-27 00:00:07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260527_0008"
down_revision: str | None = "20260527_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REVIEW_STATUS_ENUM = postgresql.ENUM(
    "PENDING",
    "APPROVED",
    "REJECTED",
    name="review_status",
    create_type=False,
)


def upgrade() -> None:
    REVIEW_STATUS_ENUM.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "status",
            REVIEW_STATUS_ENUM,
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("moderated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("moderated_by_id", sa.Integer(), nullable=True),
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
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="ck_reviews_rating_range"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["moderated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "product_id", name="uq_reviews_user_product"),
    )
    op.create_index(op.f("ix_reviews_user_id"), "reviews", ["user_id"], unique=False)
    op.create_index(op.f("ix_reviews_product_id"), "reviews", ["product_id"], unique=False)
    op.create_index(op.f("ix_reviews_order_id"), "reviews", ["order_id"], unique=False)
    op.create_index(op.f("ix_reviews_status"), "reviews", ["status"], unique=False)
    op.create_index(
        op.f("ix_reviews_moderated_by_id"),
        "reviews",
        ["moderated_by_id"],
        unique=False,
    )

    op.create_table(
        "favorites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "product_id", name="uq_favorites_user_product"),
    )
    op.create_index(op.f("ix_favorites_user_id"), "favorites", ["user_id"], unique=False)
    op.create_index(op.f("ix_favorites_product_id"), "favorites", ["product_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_favorites_product_id"), table_name="favorites")
    op.drop_index(op.f("ix_favorites_user_id"), table_name="favorites")
    op.drop_table("favorites")
    op.drop_index(op.f("ix_reviews_moderated_by_id"), table_name="reviews")
    op.drop_index(op.f("ix_reviews_status"), table_name="reviews")
    op.drop_index(op.f("ix_reviews_order_id"), table_name="reviews")
    op.drop_index(op.f("ix_reviews_product_id"), table_name="reviews")
    op.drop_index(op.f("ix_reviews_user_id"), table_name="reviews")
    op.drop_table("reviews")
    REVIEW_STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
