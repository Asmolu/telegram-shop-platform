"""Add return lifecycle statuses

Revision ID: 20260702_0043
Revises: 20260702_0042
Create Date: 2026-07-02 00:00:02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260702_0043"
down_revision: str | None = "20260702_0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE return_request_status ADD VALUE IF NOT EXISTS 'COMPLETED'")
    op.execute("ALTER TYPE return_request_status ADD VALUE IF NOT EXISTS 'CANCELLED'")

    op.add_column(
        "return_requests",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "return_requests",
        sa.Column("completed_by_user_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "return_requests",
        sa.Column("completion_comment", sa.Text(), nullable=True),
    )
    op.add_column(
        "return_requests",
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "return_requests",
        sa.Column("cancelled_by_user_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "return_requests",
        sa.Column("cancellation_comment", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_return_requests_completed_by_user_id_users",
        "return_requests",
        "users",
        ["completed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_return_requests_cancelled_by_user_id_users",
        "return_requests",
        "users",
        ["cancelled_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_return_requests_cancelled_by_user_id_users",
        "return_requests",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_return_requests_completed_by_user_id_users",
        "return_requests",
        type_="foreignkey",
    )
    op.drop_column("return_requests", "cancellation_comment")
    op.drop_column("return_requests", "cancelled_by_user_id")
    op.drop_column("return_requests", "cancelled_at")
    op.drop_column("return_requests", "completion_comment")
    op.drop_column("return_requests", "completed_by_user_id")
    op.drop_column("return_requests", "completed_at")
    # PostgreSQL cannot drop enum values without rebuilding dependent columns.
    # Keep COMPLETED and CANCELLED values in the enum on downgrade.
