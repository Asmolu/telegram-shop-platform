from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Product, ProductStatus, Tag


class ProductsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        category_id: int | None = None,
        tag_id: int | None = None,
        status: ProductStatus | None = None,
        search: str | None = None,
    ) -> tuple[list[Product], int]:
        conditions = self._build_filters(
            category_id=category_id,
            tag_id=tag_id,
            status=status,
            search=search,
        )
        products_query = (
            select(Product)
            .options(
                selectinload(Product.category),
                selectinload(Product.tags),
                selectinload(Product.images),
            )
            .where(*conditions)
            .order_by(Product.created_at.desc(), Product.id.desc())
            .limit(limit)
            .offset(offset)
        )
        count_query = select(func.count(Product.id)).where(*conditions)

        products_result = await self.session.execute(products_query)
        count_result = await self.session.execute(count_query)
        return list(products_result.scalars().all()), count_result.scalar_one()

    async def get_by_id(self, product_id: int) -> Product | None:
        result = await self.session.execute(
            select(Product)
            .options(
                selectinload(Product.category),
                selectinload(Product.tags),
                selectinload(Product.images),
            )
            .where(Product.id == product_id)
        )
        return result.scalar_one_or_none()

    async def get_active_by_id(self, product_id: int) -> Product | None:
        result = await self.session.execute(
            select(Product)
            .options(
                selectinload(Product.category),
                selectinload(Product.tags),
                selectinload(Product.images),
            )
            .where(Product.id == product_id, Product.status == ProductStatus.ACTIVE)
        )
        return result.scalar_one_or_none()

    def add(self, product: Product) -> None:
        self.session.add(product)

    async def delete(self, product: Product) -> None:
        await self.session.delete(product)

    def _build_filters(
        self,
        *,
        category_id: int | None,
        tag_id: int | None,
        status: ProductStatus | None,
        search: str | None,
    ) -> list:
        conditions = []
        if category_id is not None:
            conditions.append(Product.category_id == category_id)
        if tag_id is not None:
            conditions.append(Product.tags.any(Tag.id == tag_id))
        if status is not None:
            conditions.append(Product.status == status)
        if search:
            search_pattern = f"%{search.strip()}%"
            conditions.append(
                or_(
                    Product.name.ilike(search_pattern),
                    Product.slug.ilike(search_pattern),
                    Product.description.ilike(search_pattern),
                )
            )
        return conditions
