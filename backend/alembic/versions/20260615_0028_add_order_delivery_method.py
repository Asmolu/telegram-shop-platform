"""Add order delivery method

Revision ID: 20260615_0028
Revises: 20260614_0027
Create Date: 2026-06-15 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260615_0028"
down_revision: str | None = "20260614_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORDER_DELIVERY_METHOD_ENUM = postgresql.ENUM(
    "ROUTE_TAXI",
    "CITY_DELIVERY",
    "OZON",
    "WB",
    "CDEK",
    name="order_delivery_method",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    ORDER_DELIVERY_METHOD_ENUM.create(bind, checkfirst=True)
    op.add_column(
        "orders",
        sa.Column("delivery_method", ORDER_DELIVERY_METHOD_ENUM, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orders", "delivery_method")
    bind = op.get_bind()
    ORDER_DELIVERY_METHOD_ENUM.drop(bind, checkfirst=True)
