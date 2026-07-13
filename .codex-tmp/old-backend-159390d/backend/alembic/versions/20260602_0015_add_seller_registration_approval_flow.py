"""Add seller registration approval flow

Revision ID: 20260602_0015
Revises: 20260601_0014
Create Date: 2026-06-02 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260602_0015"
down_revision: str | None = "20260601_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CANONICAL_SELLER_REGISTRATION_STATUS_VALUES = (
    "PENDING",
    "AWAITING_APPROVAL",
    "APPROVED",
    "VERIFIED",
    "EXPIRED",
    "REJECTED",
)
PREVIOUS_SELLER_REGISTRATION_STATUS_VALUES = (
    "PENDING",
    "VERIFIED",
    "EXPIRED",
    "REJECTED",
)

ENUM_NAME = "seller_registration_status"
UPGRADE_ENUM_NAME = "seller_registration_status_0015"
DOWNGRADE_ENUM_NAME = "seller_registration_status_0014"


def upgrade() -> None:
    op.add_column(
        "pending_seller_registrations",
        sa.Column("telegram_first_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "pending_seller_registrations",
        sa.Column("telegram_last_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "pending_seller_registrations",
        sa.Column("approval_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "pending_seller_registrations",
        sa.Column("approval_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "pending_seller_registrations",
        sa.Column("approval_decided_at", sa.DateTime(timezone=True), nullable=True),
    )
    _replace_status_enum(
        new_type_name=UPGRADE_ENUM_NAME,
        values=CANONICAL_SELLER_REGISTRATION_STATUS_VALUES,
        value_expression="status::text",
        default_value="PENDING",
    )


def downgrade() -> None:
    _replace_status_enum(
        new_type_name=DOWNGRADE_ENUM_NAME,
        values=PREVIOUS_SELLER_REGISTRATION_STATUS_VALUES,
        value_expression=(
            "CASE status::text "
            "WHEN 'AWAITING_APPROVAL' THEN 'PENDING' "
            "WHEN 'APPROVED' THEN 'PENDING' "
            "ELSE status::text END"
        ),
        default_value="PENDING",
    )
    op.drop_column("pending_seller_registrations", "approval_decided_at")
    op.drop_column("pending_seller_registrations", "approval_expires_at")
    op.drop_column("pending_seller_registrations", "approval_requested_at")
    op.drop_column("pending_seller_registrations", "telegram_last_name")
    op.drop_column("pending_seller_registrations", "telegram_first_name")


def _replace_status_enum(
    *,
    new_type_name: str,
    values: tuple[str, ...],
    value_expression: str,
    default_value: str,
) -> None:
    bind = op.get_bind()
    replacement_enum = postgresql.ENUM(*values, name=new_type_name)
    replacement_enum.create(bind, checkfirst=True)

    op.execute(
        "ALTER TABLE pending_seller_registrations "
        "ALTER COLUMN status DROP DEFAULT"
    )
    op.execute(
        sa.text(
            "ALTER TABLE pending_seller_registrations "
            f"ALTER COLUMN status TYPE {new_type_name} "
            f"USING ({value_expression})::{new_type_name}"
        )
    )
    op.execute(sa.text(f"DROP TYPE {ENUM_NAME}"))
    op.execute(sa.text(f"ALTER TYPE {new_type_name} RENAME TO {ENUM_NAME}"))
    op.execute(
        "ALTER TABLE pending_seller_registrations "
        f"ALTER COLUMN status SET DEFAULT '{default_value}'::{ENUM_NAME}"
    )
