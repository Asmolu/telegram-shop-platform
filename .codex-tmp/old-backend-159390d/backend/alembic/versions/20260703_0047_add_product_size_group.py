"""Add product size group

Revision ID: 20260703_0047
Revises: 20260703_0046
Create Date: 2026-07-03 00:00:02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260703_0047"
down_revision: str | None = "20260703_0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRODUCT_SIZE_GROUP_ENUM = postgresql.ENUM(
    "CLOTHING",
    "FOOTWEAR",
    "ONE_SIZE",
    name="product_size_group",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    size_group_type: sa.TypeEngine[str]
    if bind.dialect.name == "postgresql":
        PRODUCT_SIZE_GROUP_ENUM.create(bind, checkfirst=True)
        size_group_type = PRODUCT_SIZE_GROUP_ENUM
    else:
        size_group_type = sa.String(length=16)

    op.add_column(
        "products",
        sa.Column(
            "size_group",
            size_group_type,
            server_default="CLOTHING",
            nullable=False,
        ),
    )

    op.execute(
        sa.text(
            """
            UPDATE products
            SET size_group = 'ONE_SIZE'
            WHERE EXISTS (
                SELECT 1
                FROM product_variants pv
                WHERE pv.product_id = products.id
                  AND pv.is_active = TRUE
            )
              AND NOT EXISTS (
                SELECT 1
                FROM product_variants pv
                WHERE pv.product_id = products.id
                  AND pv.is_active = TRUE
                  AND pv.size <> 'ONE_SIZE'
            )
            """
        )
    )

    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                UPDATE products
                SET size_group = 'FOOTWEAR'
                WHERE size_group <> 'ONE_SIZE'
                  AND EXISTS (
                      SELECT 1
                      FROM product_variants pv
                      WHERE pv.product_id = products.id
                        AND pv.is_active = TRUE
                  )
                  AND NOT EXISTS (
                      SELECT 1
                      FROM product_variants pv
                      WHERE pv.product_id = products.id
                        AND pv.is_active = TRUE
                        AND NOT (
                            pv.size ~ '^[0-9]+$'
                            AND pv.size::integer BETWEEN 35 AND 47
                        )
                  )
                """
            )
        )
    else:
        op.execute(
            sa.text(
                """
                UPDATE products
                SET size_group = 'FOOTWEAR'
                WHERE size_group <> 'ONE_SIZE'
                  AND EXISTS (
                      SELECT 1
                      FROM product_variants pv
                      WHERE pv.product_id = products.id
                        AND pv.is_active = TRUE
                  )
                  AND NOT EXISTS (
                      SELECT 1
                      FROM product_variants pv
                      WHERE pv.product_id = products.id
                        AND pv.is_active = TRUE
                        AND NOT (
                            pv.size GLOB '[0-9]*'
                            AND CAST(pv.size AS INTEGER) BETWEEN 35 AND 47
                        )
                  )
                """
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_column("products", "size_group")
    if bind.dialect.name == "postgresql":
        PRODUCT_SIZE_GROUP_ENUM.drop(bind, checkfirst=True)
