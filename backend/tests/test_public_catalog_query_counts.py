import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.models import (
    Product,
    ProductImage,
    ProductImageBadgeType,
    ProductSizeGrid,
    ProductStatus,
    ProductVariant,
)
from app.modules.products.service import ProductsService

PROMPT3A_DATABASE_URL = os.getenv("PROMPT3A_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not PROMPT3A_DATABASE_URL,
    reason="set PROMPT3A_DATABASE_URL to run PostgreSQL query-count checks",
)


@dataclass
class QueryCounter:
    count: int = 0


@contextmanager
def count_queries(engine: AsyncEngine):
    counter = QueryCounter()

    def before_cursor_execute(*_: object) -> None:
        counter.count += 1

    event.listen(engine.sync_engine, "before_cursor_execute", before_cursor_execute)
    try:
        yield counter
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", before_cursor_execute)


@pytest.mark.asyncio
async def test_public_card_list_query_count_and_stable_pagination_postgres() -> None:
    assert PROMPT3A_DATABASE_URL is not None
    engine = create_async_engine(PROMPT3A_DATABASE_URL)
    connection = await engine.connect()
    transaction = await connection.begin()
    session_factory = async_sessionmaker(connection, expire_on_commit=False)
    try:
        async with session_factory() as session:
            await _seed_products(session)
            service = ProductsService(session)

            with count_queries(engine) as first_page_queries:
                first_page = await service.list_public_products(limit=20, offset=0)
            with count_queries(engine) as second_page_queries:
                second_page = await service.list_public_products(limit=20, offset=20)
            with count_queries(engine) as forty_item_queries:
                forty_items = await service.list_public_products(limit=40, offset=0)

            assert first_page_queries.count <= 5
            assert second_page_queries.count <= 5
            assert forty_item_queries.count <= 5
            assert len(forty_items.items) == 40
            assert {item.id for item in first_page.items}.isdisjoint(
                item.id for item in second_page.items
            )
    finally:
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


async def _seed_products(session: AsyncSession) -> None:
    prefix = uuid4().hex
    created_at = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)
    products = [
        Product(
            name=f"Prompt3A Product {index}",
            slug=f"prompt3a-{prefix}-{index}",
            brand="MENS STYLE",
            description="Hidden from card DTO",
            base_price=Decimal("1000.00") + Decimal(index),
            size_grid=ProductSizeGrid.CLOTHING_ALPHA,
            image_badge_type=ProductImageBadgeType.NONE,
            status=ProductStatus.ACTIVE,
            created_at=created_at,
            images=[
                ProductImage(
                    file_path=f"products/{prefix}-{index}.jpg",
                    thumbnail_path=f"products/{prefix}-{index}.thumbnail.webp",
                    card_path=f"products/{prefix}-{index}.card.webp",
                    detail_path=f"products/{prefix}-{index}.detail.webp",
                    position=0,
                    is_primary=True,
                )
            ],
            variants=[
                ProductVariant(
                    size="M",
                    color="black",
                    sku=f"PROMPT3A-{prefix}-{index}",
                    stock_quantity=10,
                    reserved_quantity=0,
                    is_active=True,
                )
            ],
        )
        for index in range(45)
    ]
    session.add_all(products)
    await session.flush()
