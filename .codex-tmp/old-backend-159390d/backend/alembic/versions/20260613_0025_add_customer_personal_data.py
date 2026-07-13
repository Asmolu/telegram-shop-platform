"""Add customer personal data

Revision ID: 20260613_0025
Revises: 20260613_0024
Create Date: 2026-06-13 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260613_0025"
down_revision: str | None = "20260613_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("recipient_name", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("contact_phone", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("city", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("height_cm", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("weight_kg", sa.Numeric(precision=6, scale=2), nullable=True))
    op.add_column("users", sa.Column("telegram_username", sa.String(length=32), nullable=True))
    op.add_column(
        "users",
        sa.Column("persistent_comment", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "persistent_comment")
    op.drop_column("users", "telegram_username")
    op.drop_column("users", "weight_kg")
    op.drop_column("users", "height_cm")
    op.drop_column("users", "city")
    op.drop_column("users", "contact_phone")
    op.drop_column("users", "recipient_name")
