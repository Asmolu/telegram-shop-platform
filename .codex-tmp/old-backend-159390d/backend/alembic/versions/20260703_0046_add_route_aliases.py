"""Add route aliases

Revision ID: 20260703_0046
Revises: 20260703_0045
Create Date: 2026-07-03 00:00:01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260703_0046"
down_revision: str | None = "20260703_0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROUTE_ALIAS_ENTITY_TYPE_ENUM = postgresql.ENUM(
    "PRODUCT",
    "CATEGORY",
    "LOOK",
    name="route_alias_entity_type",
    create_type=False,
)


def upgrade() -> None:
    ROUTE_ALIAS_ENTITY_TYPE_ENUM.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "route_aliases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entity_type", ROUTE_ALIAS_ENTITY_TYPE_ENUM, nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("alias_slug", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_route_aliases_created_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_route_aliases_alias_slug", "route_aliases", ["alias_slug"])
    op.create_index("ix_route_aliases_entity_type", "route_aliases", ["entity_type"])
    op.create_index("ix_route_aliases_entity_id", "route_aliases", ["entity_id"])
    op.create_index(
        "uq_route_aliases_active_entity_type_alias_slug",
        "route_aliases",
        ["entity_type", "alias_slug"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
        sqlite_where=sa.text("is_active = 1"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_route_aliases_active_entity_type_alias_slug",
        table_name="route_aliases",
    )
    op.drop_index("ix_route_aliases_entity_id", table_name="route_aliases")
    op.drop_index("ix_route_aliases_entity_type", table_name="route_aliases")
    op.drop_index("ix_route_aliases_alias_slug", table_name="route_aliases")
    op.drop_table("route_aliases")
    ROUTE_ALIAS_ENTITY_TYPE_ENUM.drop(op.get_bind(), checkfirst=True)
