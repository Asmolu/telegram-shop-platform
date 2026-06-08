"""Add product old price and search foundation

Revision ID: 20260608_0020
Revises: 20260607_0019
Create Date: 2026-06-08 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260608_0020"
down_revision: str | None = "20260607_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.add_column("products", sa.Column("old_price", sa.Numeric(12, 2), nullable=True))
    op.add_column(
        "products",
        sa.Column("search_priority", sa.Integer(), server_default="2", nullable=False),
    )
    op.add_column("products", sa.Column("search_aliases", sa.Text(), nullable=True))

    op.create_check_constraint(
        "ck_products_old_price_above_base_price",
        "products",
        "old_price IS NULL OR old_price > base_price",
    )
    op.create_check_constraint(
        "ck_products_search_priority_range",
        "products",
        "search_priority IN (1, 2, 3)",
    )
    op.create_index(
        op.f("ix_products_search_priority"),
        "products",
        ["search_priority"],
        unique=False,
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_products_name_trgm "
        "ON products USING gin (lower(replace(coalesce(name, ''), 'ё', 'е')) gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_products_slug_trgm "
        "ON products USING gin (lower(replace(coalesce(slug, ''), 'ё', 'е')) gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_products_description_trgm "
        "ON products USING gin (lower(replace(coalesce(description, ''), 'ё', 'е')) gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_products_search_aliases_trgm "
        "ON products USING gin (lower(replace(coalesce(search_aliases, ''), 'ё', 'е')) "
        "gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_products_search_aliases_trgm")
    op.execute("DROP INDEX IF EXISTS ix_products_description_trgm")
    op.execute("DROP INDEX IF EXISTS ix_products_slug_trgm")
    op.execute("DROP INDEX IF EXISTS ix_products_name_trgm")
    op.drop_index(op.f("ix_products_search_priority"), table_name="products")
    op.drop_constraint("ck_products_search_priority_range", "products", type_="check")
    op.drop_constraint("ck_products_old_price_above_base_price", "products", type_="check")
    op.drop_column("products", "search_aliases")
    op.drop_column("products", "search_priority")
    op.drop_column("products", "old_price")
