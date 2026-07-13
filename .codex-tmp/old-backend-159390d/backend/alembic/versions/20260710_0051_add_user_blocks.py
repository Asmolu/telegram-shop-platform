"""Add user blocks

Revision ID: 20260710_0051
Revises: 20260706_0050
Create Date: 2026-07-10 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260710_0051"
down_revision: str | None = "20260706_0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_blocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_username", sa.String(length=32), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "blocked_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("blocked_by_user_id", sa.Integer(), nullable=True),
        sa.Column("unblocked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unblocked_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["blocked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["unblocked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_user_blocks_active_telegram_id",
        "user_blocks",
        ["telegram_id", "unblocked_at"],
    )
    op.create_index("ix_user_blocks_active_user", "user_blocks", ["user_id", "unblocked_at"])
    op.create_index(
        "ix_user_blocks_active_username",
        "user_blocks",
        ["telegram_username", "unblocked_at"],
    )
    op.create_index("ix_user_blocks_blocked_at", "user_blocks", ["blocked_at"])
    op.create_index("ix_user_blocks_blocked_by_user_id", "user_blocks", ["blocked_by_user_id"])
    op.create_index("ix_user_blocks_telegram_id", "user_blocks", ["telegram_id"])
    op.create_index("ix_user_blocks_telegram_username", "user_blocks", ["telegram_username"])
    op.create_index("ix_user_blocks_unblocked_by_user_id", "user_blocks", ["unblocked_by_user_id"])
    op.create_index("ix_user_blocks_user_id", "user_blocks", ["user_id"])
    op.create_index(
        "uq_user_blocks_active_user_id",
        "user_blocks",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("unblocked_at IS NULL AND user_id IS NOT NULL"),
    )
    op.create_index(
        "uq_user_blocks_active_telegram_id",
        "user_blocks",
        ["telegram_id"],
        unique=True,
        postgresql_where=sa.text("unblocked_at IS NULL AND telegram_id IS NOT NULL"),
    )
    op.create_index(
        "uq_user_blocks_active_username",
        "user_blocks",
        ["telegram_username"],
        unique=True,
        postgresql_where=sa.text("unblocked_at IS NULL AND telegram_username IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_user_blocks_active_username", table_name="user_blocks")
    op.drop_index("uq_user_blocks_active_telegram_id", table_name="user_blocks")
    op.drop_index("uq_user_blocks_active_user_id", table_name="user_blocks")
    op.drop_index("ix_user_blocks_user_id", table_name="user_blocks")
    op.drop_index("ix_user_blocks_unblocked_by_user_id", table_name="user_blocks")
    op.drop_index("ix_user_blocks_telegram_username", table_name="user_blocks")
    op.drop_index("ix_user_blocks_telegram_id", table_name="user_blocks")
    op.drop_index("ix_user_blocks_blocked_by_user_id", table_name="user_blocks")
    op.drop_index("ix_user_blocks_blocked_at", table_name="user_blocks")
    op.drop_index("ix_user_blocks_active_username", table_name="user_blocks")
    op.drop_index("ix_user_blocks_active_user", table_name="user_blocks")
    op.drop_index("ix_user_blocks_active_telegram_id", table_name="user_blocks")
    op.drop_table("user_blocks")
