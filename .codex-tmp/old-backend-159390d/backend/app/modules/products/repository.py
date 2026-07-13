from __future__ import annotations

from typing import Any

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only, selectinload

from app.db.models import (
    Category,
    Product,
    ProductCategory,
    ProductImage,
    ProductRelatedProduct,
    ProductSizeGrid,
    ProductStatus,
    ProductVariant,
    Tag,
)
from app.modules.products.search import (
    SEARCH_TRIGRAM_SIMILARITY_THRESHOLD,
    SearchSuggestionCandidate,
    SearchSuggestionKind,
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

    async def list_public_cards(
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
    ) -> tuple[list[Product], int]:
        conditions = self._build_filters(
            category_id=category_id,
            tag_id=tag_id,
            status=status,
            search=search,
            size_grid=size_grid,
            size=size,
            color=color,
            listed_only=True,
        )
        order_by = self._list_ordering(search=search, category_id=category_id)
        products_query = (
            select(Product)
            .options(
                load_only(
                    Product.id,
                    Product.name,
                    Product.slug,
                    Product.brand,
                    Product.base_price,
                    Product.old_price,
                    Product.size_grid,
                    Product.size_group,
                    Product.image_badge_type,
                    Product.image_badge_text,
                    Product.image_badge_color,
                    Product.image_badge_position,
                    Product.created_at,
                ),
                selectinload(Product.images).load_only(
                    ProductImage.id,
                    ProductImage.product_id,
                    ProductImage.file_path,
                    ProductImage.thumbnail_path,
                    ProductImage.card_path,
                    ProductImage.detail_path,
                    ProductImage.alt_text,
                    ProductImage.position,
                    ProductImage.is_primary,
                ),
                selectinload(Product.variants.and_(ProductVariant.is_active.is_(True))).load_only(
                    ProductVariant.id,
                    ProductVariant.product_id,
                    ProductVariant.size,
                    ProductVariant.color,
                    ProductVariant.stock_quantity,
                    ProductVariant.reserved_quantity,
                    ProductVariant.is_active,
                ),
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

    async def get_similarity_context_by_id(self, product_id: int) -> Product | None:
        result = await self.session.execute(
            select(Product)
            .options(
                load_only(
                    Product.id,
                    Product.category_id,
                    Product.status,
                ),
                selectinload(Product.product_categories).load_only(
                    ProductCategory.product_id,
                    ProductCategory.category_id,
                    ProductCategory.priority,
                ),
                selectinload(Product.tags).load_only(Tag.id),
            )
            .where(Product.id == product_id, Product.status == ProductStatus.ACTIVE)
        )
        return result.scalar_one_or_none()

    async def list_public_similarity_candidates(
        self,
        *,
        category_ids: set[int],
        tag_ids: set[int],
        exclude_product_ids: set[int],
    ) -> list[Product]:
        match_conditions = []
        if category_ids:
            match_conditions.extend(
                [
                    Product.category_id.in_(category_ids),
                    Product.product_categories.any(
                        ProductCategory.category_id.in_(category_ids)
                    ),
                ]
            )
        if tag_ids:
            match_conditions.append(Product.tags.any(Tag.id.in_(tag_ids)))
        if not match_conditions:
            return []

        conditions = [
            Product.status == ProductStatus.ACTIVE,
            Product.is_listed.is_(True),
            or_(*match_conditions),
        ]
        if exclude_product_ids:
            conditions.append(~Product.id.in_(exclude_product_ids))

        result = await self.session.execute(
            select(Product)
            .options(
                load_only(
                    Product.id,
                    Product.name,
                    Product.slug,
                    Product.brand,
                    Product.base_price,
                    Product.old_price,
                    Product.search_priority,
                    Product.size_grid,
                    Product.size_group,
                    Product.image_badge_type,
                    Product.image_badge_text,
                    Product.image_badge_color,
                    Product.image_badge_position,
                    Product.status,
                    Product.is_listed,
                    Product.category_id,
                    Product.created_at,
                ),
                selectinload(Product.product_categories).load_only(
                    ProductCategory.product_id,
                    ProductCategory.category_id,
                    ProductCategory.priority,
                ),
                selectinload(Product.tags).load_only(Tag.id),
                selectinload(Product.images).load_only(
                    ProductImage.id,
                    ProductImage.product_id,
                    ProductImage.file_path,
                    ProductImage.thumbnail_path,
                    ProductImage.card_path,
                    ProductImage.detail_path,
                    ProductImage.alt_text,
                    ProductImage.position,
                    ProductImage.is_primary,
                ),
                selectinload(Product.variants.and_(ProductVariant.is_active.is_(True))).load_only(
                    ProductVariant.id,
                    ProductVariant.product_id,
                    ProductVariant.size,
                    ProductVariant.color,
                    ProductVariant.stock_quantity,
                    ProductVariant.reserved_quantity,
                    ProductVariant.is_active,
                ),
            )
            .where(*conditions)
            .order_by(Product.search_priority.asc(), Product.created_at.desc(), Product.id.desc())
        )
        return list(result.scalars().all())

    async def list_search_suggestions(
        self,
        *,
        query: str,
        limit: int,
    ) -> list[SearchSuggestionCandidate]:
        normalized_query = normalize_search_text(query)
        if not normalized_query:
            return []

        search_pattern = f"%{normalized_query}%"
        per_source_limit = max(limit * 2, 4)
        candidates: list[SearchSuggestionCandidate] = []

        product_rows = await self.session.execute(
            select(Product.name)
            .where(
                Product.status == ProductStatus.ACTIVE,
                Product.is_listed.is_(True),
                self._suggestion_text_matches(Product.name, search_pattern),
            )
            .order_by(
                self._suggestion_prefix_rank(Product.name, normalized_query),
                Product.search_priority.asc(),
                Product.created_at.desc(),
                Product.id.desc(),
            )
            .limit(per_source_limit)
        )
        candidates.extend(
            self._suggestion_candidate(value, "product", normalized_query, 0)
            for value in product_rows.scalars().all()
            if value
        )

        brand_rows = await self.session.execute(
            select(Product.brand, func.count(Product.id).label("product_count"))
            .where(
                Product.status == ProductStatus.ACTIVE,
                Product.is_listed.is_(True),
                Product.brand.is_not(None),
                self._normalized_column(Product.brand) != "",
                self._suggestion_text_matches(Product.brand, search_pattern),
            )
            .group_by(Product.brand)
            .order_by(
                self._suggestion_prefix_rank(Product.brand, normalized_query),
                func.count(Product.id).desc(),
                func.min(Product.search_priority).asc(),
                Product.brand.asc(),
            )
            .limit(per_source_limit)
        )
        candidates.extend(
            self._suggestion_candidate(value, "brand", normalized_query, 20)
            for value, _ in brand_rows.all()
            if value
        )

        active_category_condition = or_(
            Category.products.any(
                and_(
                    Product.status == ProductStatus.ACTIVE,
                    Product.is_listed.is_(True),
                )
            ),
            Category.product_categories.any(
                ProductCategory.product.has(
                    and_(
                        Product.status == ProductStatus.ACTIVE,
                        Product.is_listed.is_(True),
                    )
                )
            ),
        )
        category_rows = await self.session.execute(
            select(Category.name)
            .where(
                active_category_condition,
                or_(
                    self._suggestion_text_matches(Category.name, search_pattern),
                    self._suggestion_text_matches(Category.slug, search_pattern),
                    self._suggestion_text_matches(Category.description, search_pattern),
                ),
            )
            .order_by(
                self._suggestion_prefix_rank(Category.name, normalized_query),
                Category.name.asc(),
            )
            .limit(per_source_limit)
        )
        candidates.extend(
            self._suggestion_candidate(value, "category", normalized_query, 40)
            for value in category_rows.scalars().all()
            if value
        )

        tag_rows = await self.session.execute(
            select(Tag.name)
            .where(
                Tag.products.any(
                    and_(
                        Product.status == ProductStatus.ACTIVE,
                        Product.is_listed.is_(True),
                    )
                ),
                or_(
                    self._suggestion_text_matches(Tag.name, search_pattern),
                    self._suggestion_text_matches(Tag.slug, search_pattern),
                ),
            )
            .order_by(
                self._suggestion_prefix_rank(Tag.name, normalized_query),
                Tag.name.asc(),
            )
            .limit(per_source_limit)
        )
        candidates.extend(
            self._suggestion_candidate(value, "tag", normalized_query, 50)
            for value in tag_rows.scalars().all()
            if value
        )

        alias_rows = await self.session.execute(
            select(Product.search_aliases)
            .where(
                Product.status == ProductStatus.ACTIVE,
                Product.is_listed.is_(True),
                Product.search_aliases.is_not(None),
                self._suggestion_text_matches(Product.search_aliases, search_pattern),
            )
            .order_by(
                self._suggestion_prefix_rank(Product.search_aliases, normalized_query),
                Product.search_priority.asc(),
                Product.created_at.desc(),
                Product.id.desc(),
            )
            .limit(per_source_limit)
        )
        for raw_aliases in alias_rows.scalars().all():
            for alias in self._split_search_aliases(raw_aliases):
                if self._suggestion_value_matches(alias, normalized_query):
                    candidates.append(
                        self._suggestion_candidate(alias, "alias", normalized_query, 60)
                    )

        return self._dedupe_suggestions(candidates, limit)

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
                selectinload(Product.related_product_links)
                .selectinload(ProductRelatedProduct.related_product)
                .selectinload(Product.category),
                selectinload(Product.related_product_links)
                .selectinload(ProductRelatedProduct.related_product)
                .selectinload(Product.product_categories)
                .selectinload(ProductCategory.category),
                selectinload(Product.related_product_links)
                .selectinload(ProductRelatedProduct.related_product)
                .selectinload(Product.tags),
                selectinload(Product.related_product_links)
                .selectinload(ProductRelatedProduct.related_product)
                .selectinload(Product.images),
                selectinload(Product.related_product_links)
                .selectinload(ProductRelatedProduct.related_product)
                .selectinload(Product.variants),
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
                selectinload(Product.related_product_links)
                .selectinload(ProductRelatedProduct.related_product)
                .selectinload(Product.category),
                selectinload(Product.related_product_links)
                .selectinload(ProductRelatedProduct.related_product)
                .selectinload(Product.product_categories)
                .selectinload(ProductCategory.category),
                selectinload(Product.related_product_links)
                .selectinload(ProductRelatedProduct.related_product)
                .selectinload(Product.tags),
                selectinload(Product.related_product_links)
                .selectinload(ProductRelatedProduct.related_product)
                .selectinload(Product.images),
                selectinload(Product.related_product_links)
                .selectinload(ProductRelatedProduct.related_product)
                .selectinload(
                    Product.variants.and_(ProductVariant.is_active.is_(True))
                ),
            )
            .where(Product.id == product_id, Product.status == ProductStatus.ACTIVE)
        )
        return result.scalar_one_or_none()

    async def get_public_detail_by_id(self, product_id: int) -> Product | None:
        related_product_loader = selectinload(
            Product.related_product_links
        ).selectinload(ProductRelatedProduct.related_product)

        result = await self.session.execute(
            select(Product)
            .options(
                selectinload(Product.category),
                selectinload(Product.product_categories).selectinload(ProductCategory.category),
                selectinload(Product.tags),
                selectinload(Product.images),
                selectinload(Product.variants.and_(ProductVariant.is_active.is_(True))),
                related_product_loader.load_only(
                    Product.id,
                    Product.name,
                    Product.slug,
                    Product.brand,
                    Product.base_price,
                    Product.old_price,
                    Product.size_grid,
                    Product.size_group,
                    Product.image_badge_type,
                    Product.image_badge_text,
                    Product.image_badge_color,
                    Product.image_badge_position,
                    Product.status,
                    Product.is_listed,
                    Product.created_at,
                ),
                related_product_loader.selectinload(Product.images).load_only(
                    ProductImage.id,
                    ProductImage.product_id,
                    ProductImage.file_path,
                    ProductImage.thumbnail_path,
                    ProductImage.card_path,
                    ProductImage.detail_path,
                    ProductImage.alt_text,
                    ProductImage.position,
                    ProductImage.is_primary,
                ),
                related_product_loader.selectinload(
                    Product.variants.and_(ProductVariant.is_active.is_(True))
                ).load_only(
                    ProductVariant.id,
                    ProductVariant.product_id,
                    ProductVariant.size,
                    ProductVariant.color,
                    ProductVariant.stock_quantity,
                    ProductVariant.reserved_quantity,
                    ProductVariant.is_active,
                ),
            )
            .where(Product.id == product_id, Product.status == ProductStatus.ACTIVE)
        )
        return result.scalar_one_or_none()

    async def get_public_detail_by_slug(self, product_slug: str) -> Product | None:
        related_product_loader = selectinload(
            Product.related_product_links
        ).selectinload(ProductRelatedProduct.related_product)

        result = await self.session.execute(
            select(Product)
            .options(
                selectinload(Product.category),
                selectinload(Product.product_categories).selectinload(ProductCategory.category),
                selectinload(Product.tags),
                selectinload(Product.images),
                selectinload(Product.variants.and_(ProductVariant.is_active.is_(True))),
                related_product_loader.load_only(
                    Product.id,
                    Product.name,
                    Product.slug,
                    Product.brand,
                    Product.base_price,
                    Product.old_price,
                    Product.size_grid,
                    Product.size_group,
                    Product.image_badge_type,
                    Product.image_badge_text,
                    Product.image_badge_color,
                    Product.image_badge_position,
                    Product.status,
                    Product.is_listed,
                    Product.created_at,
                ),
                related_product_loader.selectinload(Product.images).load_only(
                    ProductImage.id,
                    ProductImage.product_id,
                    ProductImage.file_path,
                    ProductImage.thumbnail_path,
                    ProductImage.card_path,
                    ProductImage.detail_path,
                    ProductImage.alt_text,
                    ProductImage.position,
                    ProductImage.is_primary,
                ),
                related_product_loader.selectinload(
                    Product.variants.and_(ProductVariant.is_active.is_(True))
                ).load_only(
                    ProductVariant.id,
                    ProductVariant.product_id,
                    ProductVariant.size,
                    ProductVariant.color,
                    ProductVariant.stock_quantity,
                    ProductVariant.reserved_quantity,
                    ProductVariant.is_active,
                ),
            )
            .where(Product.slug == product_slug, Product.status == ProductStatus.ACTIVE)
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, product_slug: str) -> Product | None:
        result = await self.session.execute(select(Product).where(Product.slug == product_slug))
        return result.scalar_one_or_none()

    async def list_existing_ids(self, product_ids: list[int]) -> set[int]:
        if not product_ids:
            return set()
        result = await self.session.execute(
            select(Product.id).where(Product.id.in_(product_ids))
        )
        return set(result.scalars().all())

    async def list_numeric_slug_candidates(self) -> list[str]:
        result = await self.session.execute(
            select(Product.slug).where(
                func.length(Product.slug) == 5,
                Product.slug >= "00001",
                Product.slug <= "99999",
            )
        )
        return list(result.scalars().all())

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
        listed_only: bool = False,
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
        if listed_only:
            conditions.append(Product.is_listed.is_(True))
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
            self._text_matches(Product.brand, term, search_pattern),
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

    def _suggestion_text_matches(self, column: Any, search_pattern: str) -> Any:
        return self._normalized_column(column).ilike(search_pattern)

    def _suggestion_prefix_rank(self, column: Any, normalized_search: str) -> Any:
        return case(
            (self._normalized_column(column).ilike(f"{normalized_search}%"), 0),
            else_=1,
        )

    def _suggestion_candidate(
        self,
        value: str,
        kind: SearchSuggestionKind,
        normalized_query: str,
        kind_score: int,
    ) -> SearchSuggestionCandidate:
        normalized_value = normalize_search_text(value) or ""
        exact_or_prefix_bonus = 0 if normalized_value == normalized_query else 2
        if normalized_value and not normalized_value.startswith(normalized_query):
            exact_or_prefix_bonus = 8
        return SearchSuggestionCandidate(
            value=value.strip(),
            kind=kind,
            score=kind_score + exact_or_prefix_bonus,
        )

    def _dedupe_suggestions(
        self,
        candidates: list[SearchSuggestionCandidate],
        limit: int,
    ) -> list[SearchSuggestionCandidate]:
        suggestions: list[SearchSuggestionCandidate] = []
        seen_values: set[str] = set()
        for candidate in sorted(
            candidates,
            key=lambda item: (item.score, len(item.value), item.value.casefold()),
        ):
            if not candidate.value:
                continue
            key = candidate.value.casefold()
            if key in seen_values:
                continue
            seen_values.add(key)
            suggestions.append(candidate)
            if len(suggestions) >= limit:
                break
        return suggestions

    def _split_search_aliases(self, value: str | None) -> list[str]:
        if value is None:
            return []
        return [
            part.strip()
            for raw_line in value.replace(",", "\n").splitlines()
            for part in raw_line.split(",")
            if part.strip()
        ]

    def _suggestion_value_matches(self, value: str, normalized_query: str) -> bool:
        normalized_value = normalize_search_text(value)
        return bool(normalized_value and normalized_query in normalized_value)

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

    async def get_by_sku(self, sku: str) -> ProductVariant | None:
        result = await self.session.execute(
            select(ProductVariant).where(ProductVariant.sku == sku)
        )
        return result.scalar_one_or_none()

    async def list_skus(self) -> list[str]:
        result = await self.session.execute(select(ProductVariant.sku))
        return list(result.scalars().all())

    def add(self, variant: ProductVariant) -> None:
        self.session.add(variant)

    async def delete(self, variant: ProductVariant) -> None:
        await self.session.delete(variant)
