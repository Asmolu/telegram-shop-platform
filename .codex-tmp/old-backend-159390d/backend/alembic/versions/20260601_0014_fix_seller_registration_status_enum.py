"""Fix seller registration status enum values

Revision ID: 20260601_0014
Revises: 20260601_0013
Create Date: 2026-06-01 00:00:01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260601_0014"
down_revision: str | None = "20260601_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CANONICAL_SELLER_REGISTRATION_STATUS_VALUES = (
    "PENDING",
    "VERIFIED",
    "EXPIRED",
    "REJECTED",
)
LEGACY_SELLER_REGISTRATION_STATUS_VALUES = (
    "pending",
    "verified",
    "expired",
    "rejected",
)

ENUM_NAME = "seller_registration_status"
NEW_ENUM_NAME = "seller_registration_status_new"
OLD_ENUM_NAME = "seller_registration_status_old"


def upgrade() -> None:
    _replace_status_enum(
        new_type_name=NEW_ENUM_NAME,
        values=CANONICAL_SELLER_REGISTRATION_STATUS_VALUES,
        value_transform="upper",
        default_value="PENDING",
    )


def downgrade() -> None:
    _replace_status_enum(
        new_type_name=OLD_ENUM_NAME,
        values=LEGACY_SELLER_REGISTRATION_STATUS_VALUES,
        value_transform="lower",
        default_value="pending",
    )


def _replace_status_enum(
    *,
    new_type_name: str,
    values: tuple[str, ...],
    value_transform: str,
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
            f"USING {value_transform}(status::text)::{new_type_name}"
        )
    )
    op.execute(sa.text(f"DROP TYPE {ENUM_NAME}"))
    op.execute(sa.text(f"ALTER TYPE {new_type_name} RENAME TO {ENUM_NAME}"))
    op.execute(
        "ALTER TABLE pending_seller_registrations "
        f"ALTER COLUMN status SET DEFAULT '{default_value}'::{ENUM_NAME}"
    )
