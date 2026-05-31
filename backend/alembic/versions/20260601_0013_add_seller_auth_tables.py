"""Add seller email auth tables

Revision ID: 20260601_0013
Revises: 20260530_0012
Create Date: 2026-06-01 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260601_0013"
down_revision: str | None = "20260530_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SELLER_REGISTRATION_STATUS_ENUM = postgresql.ENUM(
    "pending",
    "verified",
    "expired",
    "rejected",
    name="seller_registration_status",
    create_type=False,
)


def upgrade() -> None:
    SELLER_REGISTRATION_STATUS_ENUM.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "seller_credentials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("telegram_username", sa.String(length=255), nullable=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_seller_credentials_user_id"),
        "seller_credentials",
        ["user_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_seller_credentials_email"),
        "seller_credentials",
        ["email"],
        unique=True,
    )
    op.create_index(
        op.f("ix_seller_credentials_telegram_user_id"),
        "seller_credentials",
        ["telegram_user_id"],
        unique=False,
    )

    op.create_table(
        "pending_seller_registrations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("telegram_username", sa.String(length=255), nullable=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("bot_start_token_hash", sa.String(length=128), nullable=False),
        sa.Column("verification_code_hash", sa.String(length=128), nullable=True),
        sa.Column("verification_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            SELLER_REGISTRATION_STATUS_ENUM,
            server_default="pending",
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bot_start_token_hash", name="uq_pending_seller_start_token_hash"),
    )
    op.create_index(
        op.f("ix_pending_seller_registrations_email"),
        "pending_seller_registrations",
        ["email"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pending_seller_registrations_telegram_user_id"),
        "pending_seller_registrations",
        ["telegram_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pending_seller_registrations_status"),
        "pending_seller_registrations",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_pending_seller_registrations_status"),
        table_name="pending_seller_registrations",
    )
    op.drop_index(
        op.f("ix_pending_seller_registrations_telegram_user_id"),
        table_name="pending_seller_registrations",
    )
    op.drop_index(
        op.f("ix_pending_seller_registrations_email"),
        table_name="pending_seller_registrations",
    )
    op.drop_table("pending_seller_registrations")
    op.drop_index(op.f("ix_seller_credentials_telegram_user_id"), table_name="seller_credentials")
    op.drop_index(op.f("ix_seller_credentials_email"), table_name="seller_credentials")
    op.drop_index(op.f("ix_seller_credentials_user_id"), table_name="seller_credentials")
    op.drop_table("seller_credentials")
    SELLER_REGISTRATION_STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
