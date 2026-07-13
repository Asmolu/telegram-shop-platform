"""Add return refund and restock audit fields

Revision ID: 20260702_0044
Revises: 20260702_0043
Create Date: 2026-07-02 00:00:03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260702_0044"
down_revision: str | None = "20260702_0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "return_refunds",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("return_request_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="RUB", nullable=False),
        sa.Column("method", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="PENDING", nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_by_user_id", sa.Integer(), nullable=True),
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
        sa.CheckConstraint("amount >= 0", name="ck_return_refunds_amount_non_negative"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RECORDED')",
            name="ck_return_refunds_status",
        ),
        sa.ForeignKeyConstraint(
            ["processed_by_user_id"],
            ["users.id"],
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
            name="uq_return_refunds_return_request_id",
        ),
    )
    op.create_index(
        "ix_return_refunds_processed_by_user_id",
        "return_refunds",
        ["processed_by_user_id"],
    )

    op.add_column(
        "return_request_items",
        sa.Column("restocked_quantity", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "return_request_items",
        sa.Column("restocked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "return_request_items",
        sa.Column("restocked_by_user_id", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_return_request_items_restocked_quantity_non_negative",
        "return_request_items",
        "restocked_quantity >= 0",
    )
    op.create_check_constraint(
        "ck_return_request_items_restocked_quantity_not_above_quantity",
        "return_request_items",
        "restocked_quantity <= quantity",
    )
    op.create_foreign_key(
        "fk_return_request_items_restocked_by_user_id_users",
        "return_request_items",
        "users",
        ["restocked_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_return_request_items_restocked_by_user_id",
        "return_request_items",
        ["restocked_by_user_id"],
    )
    op.create_index(
        "ix_return_request_items_product_variant_id",
        "return_request_items",
        ["product_variant_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_return_request_items_product_variant_id",
        table_name="return_request_items",
    )
    op.drop_index(
        "ix_return_request_items_restocked_by_user_id",
        table_name="return_request_items",
    )
    op.drop_constraint(
        "fk_return_request_items_restocked_by_user_id_users",
        "return_request_items",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_return_request_items_restocked_quantity_not_above_quantity",
        "return_request_items",
        type_="check",
    )
    op.drop_constraint(
        "ck_return_request_items_restocked_quantity_non_negative",
        "return_request_items",
        type_="check",
    )
    op.drop_column("return_request_items", "restocked_by_user_id")
    op.drop_column("return_request_items", "restocked_at")
    op.drop_column("return_request_items", "restocked_quantity")

    op.drop_index(
        "ix_return_refunds_processed_by_user_id",
        table_name="return_refunds",
    )
    op.drop_table("return_refunds")
