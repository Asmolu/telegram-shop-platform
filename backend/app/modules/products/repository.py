from __future__ import annotations

from typing import Any

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    Category,
    Product,
    ProductCategory,
    ProductSizeGrid,
    ProductStatus,
    ProductVariant,
    Tag,
)
from app.modules.products.search import (
    SEARCH_TRIGRAM_SIMILARITY_THRESHOLD,
    SearchToken,
    expand_color_query,
    normalize_search_text,
    tokenize_search_query,
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
        size_grid: ProductSizeGrid | None = None,
        size: str | None = None,
        color: str | None = None,
        active_variants_only: bool = False,
    ) -> tuple[list[Product], int]:
        conditions = self._build_filters(
            category_id=category_id,
            tag_id=tag_id,
            status=status,
            search=search,
            size_grid=size_grid,
            size=size,
            color=color,
        )
        variants_loader = selectinload(Product.variants)
        if active_variants_only:
            variants_loader = selectinload(
                Product.variants.and_(ProductVariant.is_active.is_(True))
            )

        order_by = self._list_ordering(search=search, category_id=category_id)
        products_query = (
            select(Product)
            .options(
                selectinload(Product.category),
                selectinload(Product.product_categories).selectinload(ProductCategory.category),
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
                selectinload(Product.product_categories).selectinload(ProductCategory.category),
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
                selectinload(Product.product_categories).selectinload(ProductCategory.category),
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
        size_grid: ProductSizeGrid | None = None,
        size: str | None = None,
        color: str | None = None,
    ) -> list[Any]:
        conditions = []
        if category_id is not None:
            conditions.append(
                or_(
                    Product.category_id == category_id,
                    Product.product_categories.any(ProductCategory.category_id == category_id),
                )
            )
        if tag_id is not None:
            conditions.append(Product.tags.any(Tag.id == tag_id))
        if status is not None:
            conditions.append(Product.status == status)
        if size_grid is not None:
            conditions.append(Product.size_grid == size_grid)
        if size is not None or color is not None:
            conditions.append(self._variant_filter_condition(size=size, color=color))
        normalized_search = normalize_search_text(search)
        if normalized_search:
            conditions.append(self._search_condition(normalized_search))
        return conditions

    def _list_ordering(
        self,
        *,
        search: str | None,
        category_id: int | None = None,
    ) -> tuple[Any, ...]:
        category_priority = (
            self._category_priority_expression(category_id) if category_id is not None else None
        )
        if normalize_search_text(search):
            if category_priority is not None:
                return (
                    Product.search_priority.asc(),
                    category_priority.asc(),
                    Product.created_at.desc(),
                    Product.id.desc(),
                )
            return (Product.search_priority.asc(), Product.created_at.desc(), Product.id.desc())
        if category_priority is not None:
            return (category_priority.asc(), Product.created_at.desc(), Product.id.desc())
        return (Product.created_at.desc(), Product.id.desc())

    def _search_condition(self, normalized_search: str) -> Any:
        tokens = tokenize_search_query(normalized_search)
        token_conditions = [self._search_token_condition(token) for token in tokens]
        numeric_sizes = [token.value for token in tokens if token.is_numeric_size]
        color_terms = tuple(
            dict.fromkeys(term for token in tokens for term in token.color_terms)
        )
        if numeric_sizes and color_terms:
            token_conditions.append(
                Product.variants.any(
                    and_(
                        ProductVariant.is_active.is_(True),
                        ProductVariant.size.in_(numeric_sizes),
                        self._color_matches(ProductVariant.color, color_terms),
                    )
                )
            )
        return and_(*token_conditions)

    def _search_token_condition(self, token: SearchToken) -> Any:
        if token.is_numeric_size:
            return Product.variants.any(
                and_(
                    ProductVariant.is_active.is_(True),
                    ProductVariant.size == token.value,
                )
            )

        terms = tuple(dict.fromkeys((token.value, *token.color_terms)))
        return or_(*(self._text_search_condition(term) for term in terms))

    def _text_search_condition(self, term: str) -> Any:
        search_pattern = f"%{term}%"
        return or_(
            self._text_matches(Product.name, term, search_pattern),
            self._text_matches(Product.slug, term, search_pattern),
            self._text_matches(Product.description, term, search_pattern),
            self._text_matches(Product.search_aliases, term, search_pattern),
            Product.category.has(
                or_(
                    self._text_matches(Category.name, term, search_pattern),
                    self._text_matches(Category.slug, term, search_pattern),
                    self._text_matches(Category.description, term, search_pattern),
                )
            ),
            Product.product_categories.any(
                ProductCategory.category.has(
                    or_(
                        self._text_matches(Category.name, term, search_pattern),
                        self._text_matches(Category.slug, term, search_pattern),
                        self._text_matches(Category.description, term, search_pattern),
                    )
                )
            ),
            Product.tags.any(
                or_(
                    self._text_matches(Tag.name, term, search_pattern),
                    self._text_matches(Tag.slug, term, search_pattern),
                )
            ),
            Product.variants.any(
                and_(
                    ProductVariant.is_active.is_(True),
                    or_(
                        self._text_matches(ProductVariant.sku, term, search_pattern),
                        self._text_matches(ProductVariant.color, term, search_pattern),
                    ),
                )
            ),
        )

    def _variant_filter_condition(self, *, size: str | None, color: str | None) -> Any:
        variant_conditions = [ProductVariant.is_active.is_(True)]
        if size is not None:
            variant_conditions.append(ProductVariant.size == size)
        color_terms = expand_color_query(color)
        if color_terms:
            variant_conditions.append(self._color_matches(ProductVariant.color, color_terms))
        return Product.variants.any(and_(*variant_conditions))

    def _color_matches(self, column: Any, terms: tuple[str, ...]) -> Any:
        normalized_column = self._normalized_column(column)
        return or_(*(normalized_column.ilike(f"%{term}%") for term in terms))

    def _text_matches(self, column: Any, normalized_search: str, search_pattern: str) -> Any:
        normalized_column = self._normalized_column(column)
        return or_(
            normalized_column.ilike(search_pattern),
            func.similarity(normalized_column, normalized_search)
            >= SEARCH_TRIGRAM_SIMILARITY_THRESHOLD,
        )

    def _normalized_column(self, column: Any) -> Any:
        return func.lower(func.replace(func.coalesce(column, ""), "ё", "е"))

    def _category_priority_expression(self, category_id: int) -> Any:
        relation_priority = (
            select(func.min(ProductCategory.priority))
            .where(
                ProductCategory.product_id == Product.id,
                ProductCategory.category_id == category_id,
            )
            .correlate(Product)
            .scalar_subquery()
        )
        legacy_priority = case((Product.category_id == category_id, 1), else_=4)
        return func.coalesce(relation_priority, legacy_priority)


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
