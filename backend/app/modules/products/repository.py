from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Category, Product, ProductStatus, ProductVariant, Tag
from app.modules.products.search import (
    SEARCH_TRIGRAM_SIMILARITY_THRESHOLD,
    normalize_search_text,
)


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
        active_variants_only: bool = False,
    ) -> tuple[list[Product], int]:
        conditions = self._build_filters(
            category_id=category_id,
            tag_id=tag_id,
            status=status,
            search=search,
        )
        variants_loader = selectinload(Product.variants)
        if active_variants_only:
            variants_loader = selectinload(
                Product.variants.and_(ProductVariant.is_active.is_(True))
            )

        order_by = self._list_ordering(search=search)
        products_query = (
            select(Product)
            .options(
                selectinload(Product.category),
                selectinload(Product.tags),
                selectinload(Product.images),
                variants_loader,
            )
            .where(*conditions)
            .order_by(*order_by)
            .limit(limit)
            .offset(offset)
        )
        count_query = select(func.count(Product.id)).where(*conditions)

        products_result = await self.session.execute(products_query)
        count_result = await self.session.execute(count_query)
        return list(products_result.scalars().all()), count_result.scalar_one()

    async def get_by_id(
        self,
        product_id: int,
        *,
        active_variants_only: bool = False,
    ) -> Product | None:
        variants_loader = selectinload(Product.variants)
        if active_variants_only:
            variants_loader = selectinload(
                Product.variants.and_(ProductVariant.is_active.is_(True))
            )

        result = await self.session.execute(
            select(Product)
            .options(
                selectinload(Product.category),
                selectinload(Product.tags),
                selectinload(Product.images),
                variants_loader,
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
                selectinload(Product.variants.and_(ProductVariant.is_active.is_(True))),
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
    ) -> list[Any]:
        conditions = []
        if category_id is not None:
            conditions.append(Product.category_id == category_id)
        if tag_id is not None:
            conditions.append(Product.tags.any(Tag.id == tag_id))
        if status is not None:
            conditions.append(Product.status == status)
        normalized_search = normalize_search_text(search)
        if normalized_search:
            conditions.append(self._search_condition(normalized_search))
        return conditions

    def _list_ordering(self, *, search: str | None) -> tuple[Any, ...]:
        if normalize_search_text(search):
            return (Product.search_priority.asc(), Product.created_at.desc(), Product.id.desc())
        return (Product.created_at.desc(), Product.id.desc())

    def _search_condition(self, normalized_search: str) -> Any:
        search_pattern = f"%{normalized_search}%"
        return or_(
            self._text_matches(Product.name, normalized_search, search_pattern),
            self._text_matches(Product.slug, normalized_search, search_pattern),
            self._text_matches(Product.description, normalized_search, search_pattern),
            self._text_matches(Product.search_aliases, normalized_search, search_pattern),
            Product.category.has(
                or_(
                    self._text_matches(Category.name, normalized_search, search_pattern),
                    self._text_matches(Category.slug, normalized_search, search_pattern),
                    self._text_matches(Category.description, normalized_search, search_pattern),
                )
            ),
            Product.tags.any(
                or_(
                    self._text_matches(Tag.name, normalized_search, search_pattern),
                    self._text_matches(Tag.slug, normalized_search, search_pattern),
                )
            ),
            Product.variants.any(
                self._text_matches(ProductVariant.sku, normalized_search, search_pattern)
            ),
        )

    def _text_matches(self, column: Any, normalized_search: str, search_pattern: str) -> Any:
        normalized_column = self._normalized_column(column)
        return or_(
            normalized_column.ilike(search_pattern),
            func.similarity(normalized_column, normalized_search)
            >= SEARCH_TRIGRAM_SIMILARITY_THRESHOLD,
        )

    def _normalized_column(self, column: Any) -> Any:
        return func.lower(func.replace(func.coalesce(column, ""), "ё", "е"))


class ProductVariantsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_product_id(
        self,
        product_id: int,
        *,
        active_only: bool = False,
    ) -> list[ProductVariant]:
        conditions = [ProductVariant.product_id == product_id]
        if active_only:
            conditions.append(ProductVariant.is_active.is_(True))

        result = await self.session.execute(
            select(ProductVariant).where(*conditions).order_by(ProductVariant.id)
        )
        return list(result.scalars().all())

    async def get_by_id(self, variant_id: int) -> ProductVariant | None:
        result = await self.session.execute(
            select(ProductVariant).where(ProductVariant.id == variant_id)
        )
        return result.scalar_one_or_none()

    def add(self, variant: ProductVariant) -> None:
        self.session.add(variant)

    async def delete(self, variant: ProductVariant) -> None:
        await self.session.delete(variant)
