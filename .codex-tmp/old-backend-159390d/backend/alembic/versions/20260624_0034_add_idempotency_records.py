"""Add idempotency records

Revision ID: 20260624_0034
Revises: 20260619_0033
Create Date: 2026-06-24 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260624_0034"
down_revision: str | None = "20260619_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=100), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="PROCESSING",
            nullable=False,
        ),
        sa.Column("response_status_code", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.JSON(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('PROCESSING', 'SUCCEEDED')",
            name="ck_idempotency_records_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "scope",
            "key",
            name="uq_idempotency_records_user_scope_key",
        ),
    )
    op.create_index(
        "ix_idempotency_records_expires_at",
        "idempotency_records",
        ["expires_at"],
    )
    op.create_index(
        "ix_idempotency_records_user_id",
        "idempotency_records",
        ["user_id"],
    )
    op.create_index(
        "ix_idempotency_records_user_scope",
        "idempotency_records",
        ["user_id", "scope"],
    )


def downgrade() -> None:
    op.drop_index("ix_idempotency_records_user_scope", table_name="idempotency_records")
    op.drop_index("ix_idempotency_records_user_id", table_name="idempotency_records")
    op.drop_index("ix_idempotency_records_expires_at", table_name="idempotency_records")
    op.drop_table("idempotency_records")
