import logging
from collections.abc import Awaitable, Callable
from decimal import Decimal

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.cache import (
    CacheService,
    product_cache_patterns,
    public_product_detail_key,
    public_products_list_key,
)
from app.common.numeric_identifiers import allocate_numeric_identifiers
from app.common.pagination import PageMeta
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import (
    Category,
    Product,
    ProductCategory,
    ProductImage,
    ProductImageBadgeType,
    ProductRelatedProduct,
    ProductSizeGrid,
    ProductStatus,
    ProductVariant,
    RouteAliasEntityType,
    Tag,
)
from app.modules.analytics.service import AnalyticsTracker
from app.modules.audit.service import AuditService, NoopAuditService
from app.modules.categories.repository import CategoriesRepository
from app.modules.products.inventory import InventoryValidationError, validate_inventory_quantities
from app.modules.products.repository import ProductsRepository, ProductVariantsRepository
from app.modules.products.schemas import (
    ProductCardList,
    ProductCardRead,
    ProductCategoryInput,
    ProductCreate,
    ProductImageCreate,
    ProductList,
    ProductPublicDetailRead,
    ProductResolveResponse,
    ProductResolveRouteCategory,
    ProductResolveRouteContext,
    ProductSearchSuggestion,
    ProductSearchSuggestionList,
    ProductSlugList,
    ProductStatusUpdate,
    ProductUpdate,
    ProductVariantCreate,
    ProductVariantList,
    ProductVariantSkuList,
    ProductVariantUpdate,
)
from app.modules.products.search import sanitize_search_query
from app.modules.products.size_grids import (
    SizeGridValidationError,
    incompatible_sizes,
    is_footwear_size_grid,
    is_legacy_product_size_grid,
    normalize_size,
)
from app.modules.route_aliases.service import RouteAliasesService
from app.modules.tags.repository import TagsRepository
from app.modules.uploads.storage import LocalStorageService

logger = logging.getLogger(__name__)

PRODUCT_AUDIT_FIELDS = (
    "name",
    "slug",
    "brand",
    "description",
    "base_price",
    "old_price",
    "search_priority",
    "search_aliases",
    "size_grid",
    "size_group",
    "image_badge_type",
    "image_badge_text",
    "image_badge_color",
    "image_badge_position",
    "status",
    "is_listed",
    "is_returnable",
    "category_id",
)
VARIANT_AUDIT_FIELDS = (
    "product_id",
    "size",
    "color",
    "sku",
    "stock_quantity",
    "reserved_quantity",
    "is_active",
)
NUMERIC_VARIANT_SKU_MIN = 1
NUMERIC_VARIANT_SKU_MAX = 99999
NUMERIC_VARIANT_SKU_EXHAUSTED_MESSAGE = "Numeric SKU range 00001-99999 is exhausted"
NUMERIC_PRODUCT_SLUG_MIN = 1
NUMERIC_PRODUCT_SLUG_MAX = 99999
NUMERIC_PRODUCT_SLUG_EXHAUSTED_MESSAGE = (
    "Numeric product slug range 00001-99999 is exhausted."
)
SIMILAR_PRODUCTS_DEFAULT_LIMIT = 12
SIMILAR_PRODUCTS_MAX_LIMIT = 50


class ProductsService:
    def __init__(
        self,
        session: AsyncSession,
        analytics_tracker: AnalyticsTracker | None = None,
        audit_service: AuditService | None = None,
        cache: CacheService | None = None,
        storage: LocalStorageService | None = None,
    ) -> None:
        self.session = session
        self.repository = ProductsRepository(session)
        self.variants_repository = ProductVariantsRepository(session)
        self.categories_repository = CategoriesRepository(session)
        self.tags_repository = TagsRepository(session)
        self.route_aliases = RouteAliasesService(session)
        self.analytics_tracker = analytics_tracker
        self.audit_service = audit_service or NoopAuditService()
        self.cache = cache
        self.storage = storage or LocalStorageService()

    async def list_public_products(
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
        user_id: int | None = None,
        track_search: bool = True,
    ) -> ProductCardList:
        if status is not None and status != ProductStatus.ACTIVE:
            result = ProductCardList(items=[], meta=PageMeta(limit=limit, offset=offset, total=0))
            if track_search:
                await self._track_search_event(search, user_id=user_id, result_count=0)
            return result

        normalized_size = self._normalize_size_filter(size_grid=size_grid, size=size)

        cache_key = public_products_list_key(
            limit=limit,
            offset=offset,
            category_id=category_id,
            tag_id=tag_id,
            status=status,
            search=search,
            size_grid=size_grid,
            size=normalized_size,
            color=color,
        )
        if self.cache is not None:
            cached = await self.cache.get_model(cache_key, ProductCardList)
            if cached is not None:
                if track_search:
                    await self._track_search_event(
                        search,
                        user_id=user_id,
                        result_count=cached.meta.total,
                    )
                return cached

        items, total = await self.repository.list_public_cards(
            limit=limit,
            offset=offset,
            category_id=category_id,
            tag_id=tag_id,
            status=ProductStatus.ACTIVE,
            search=search,
            size_grid=size_grid,
            size=normalized_size,
            color=color,
        )
        result = ProductCardList(
            items=[ProductCardRead.model_validate(item) for item in items],
            meta=PageMeta(limit=limit, offset=offset, total=total),
        )
        if track_search:
            await self._track_search_event(search, user_id=user_id, result_count=total)
        if self.cache is not None:
            await self.cache.set_model(
                cache_key,
                result,
                settings.cache_public_products_ttl_seconds,
            )
        return result

    async def list_products(
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
    ) -> ProductList:
        items, total = await self.repository.list(
            limit=limit,
            offset=offset,
            category_id=category_id,
            tag_id=tag_id,
            status=status,
            search=search,
            size_grid=size_grid,
            size=self._normalize_size_filter(size_grid=size_grid, size=size),
            color=color,
        )
        return ProductList(items=items, meta=PageMeta(limit=limit, offset=offset, total=total))

    async def list_search_suggestions(
        self,
        *,
        query: str | None,
        limit: int = 8,
    ) -> ProductSearchSuggestionList:
        sanitized_query = sanitize_search_query(query, max_length=100)
        if sanitized_query is None or len(sanitized_query) < 2:
            return ProductSearchSuggestionList(items=[])

        safe_limit = min(max(limit, 1), 10)
        suggestions = await self.repository.list_search_suggestions(
            query=sanitized_query,
            limit=safe_limit,
        )
        return ProductSearchSuggestionList(
            items=[
                ProductSearchSuggestion(
                    value=suggestion.value,
                    kind=suggestion.kind,
                    label=suggestion.label,
                )
                for suggestion in suggestions
            ]
        )

    async def get_public_product(
        self,
        product_id: int,
        user_id: int | None = None,
        track_view: bool = True,
    ) -> ProductPublicDetailRead:
        cache_key = public_product_detail_key(product_id)
        if self.cache is not None:
            cached = await self.cache.get_model(cache_key, ProductPublicDetailRead)
            if cached is not None:
                if track_view:
                    await self._track_event(
                        "product.viewed",
                        user_id=user_id,
                        product_id=product_id,
                    )
                return cached

        product = await self.repository.get_public_detail_by_id(product_id)
        if product is None:
            raise AppError("Product not found", status.HTTP_404_NOT_FOUND)
        result = self._build_public_product_detail(product)
        if self.cache is not None:
            await self.cache.set_model(
                cache_key,
                result,
                settings.cache_public_product_detail_ttl_seconds,
            )
        if track_view:
            await self._track_event("product.viewed", user_id=user_id, product_id=product.id)
        return result

    async def resolve_public_product(
        self,
        *,
        product_slug: str,
        category_slug: str | None = None,
        sku: str | None = None,
        user_id: int | None = None,
        track_view: bool = True,
    ) -> ProductResolveResponse:
        product = await self._get_public_product_by_slug_or_alias(product_slug)
        if product is None:
            raise AppError("Product not found", status.HTTP_404_NOT_FOUND)

        route_category: ProductResolveRouteCategory | None = None
        if category_slug is not None:
            category = await self._get_category_by_slug_or_alias(category_slug)
            if category is None or not self._product_has_category(product, category.id):
                raise AppError("Product not found", status.HTTP_404_NOT_FOUND)
            route_category = ProductResolveRouteCategory(
                id=category.id,
                slug=category.slug,
                name=category.name,
            )

        selected_variant: ProductVariant | None = None
        variant_status: str | None = "sku_missing" if sku is None else None
        if sku:
            variant = await self.variants_repository.get_by_sku(sku)
            if variant is None:
                variant_status = "sku_not_found"
            elif variant.product_id != product.id:
                variant_status = "sku_not_for_product"
            elif not variant.is_active:
                variant_status = "inactive"
            else:
                selected_variant = variant
                variant_status = (
                    "out_of_stock" if variant.available_quantity <= 0 else "selected"
                )

        result = ProductResolveResponse(
            product=self._build_public_product_detail(product),
            route_context=ProductResolveRouteContext(
                category=route_category,
                product_slug=product.slug,
                requested_sku=sku,
                selected_variant_id=selected_variant.id if selected_variant else None,
                selected_variant_sku=selected_variant.sku if selected_variant else None,
                variant_status=variant_status,
            ),
        )
        if track_view:
            await self._track_event("product.viewed", user_id=user_id, product_id=product.id)
        return result

    async def track_public_product_list_search(
        self,
        *,
        search: str | None,
        user_id: int | None,
        result_count: int | None,
    ) -> None:
        await self._track_search_event(search, user_id=user_id, result_count=result_count)

    async def track_public_product_view(
        self,
        *,
        product_id: int,
        user_id: int | None,
    ) -> None:
        await self._track_event("product.viewed", user_id=user_id, product_id=product_id)

    async def list_similar_products(
        self,
        product_id: int,
        *,
        limit: int = SIMILAR_PRODUCTS_DEFAULT_LIMIT,
    ) -> ProductCardList:
        product = await self.repository.get_similarity_context_by_id(product_id)
        if product is None:
            raise AppError("Product not found", status.HTTP_404_NOT_FOUND)

        return await self.list_similar_products_for_context(
            category_ids=self._product_category_ids(product),
            tag_ids=self._product_tag_ids(product),
            exclude_product_ids={product.id},
            limit=limit,
            rank_category_overlap_count=False,
        )

    async def list_similar_products_for_context(
        self,
        *,
        category_ids: set[int],
        tag_ids: set[int],
        exclude_product_ids: set[int],
        limit: int = SIMILAR_PRODUCTS_DEFAULT_LIMIT,
        rank_category_overlap_count: bool = True,
    ) -> ProductCardList:
        safe_limit = min(max(limit, 1), SIMILAR_PRODUCTS_MAX_LIMIT)
        if not category_ids and not tag_ids:
            return ProductCardList(
                items=[],
                meta=PageMeta(limit=safe_limit, offset=0, total=0),
            )

        candidates = await self.repository.list_public_similarity_candidates(
            category_ids=category_ids,
            tag_ids=tag_ids,
            exclude_product_ids=exclude_product_ids,
        )
        ranked = self._rank_similar_products(
            candidates,
            category_ids=category_ids,
            tag_ids=tag_ids,
            exclude_product_ids=exclude_product_ids,
            rank_category_overlap_count=rank_category_overlap_count,
        )
        return ProductCardList(
            items=[ProductCardRead.model_validate(product) for product in ranked[:safe_limit]],
            meta=PageMeta(limit=safe_limit, offset=0, total=len(ranked)),
        )

    def _build_public_product_detail(self, product: Product) -> ProductPublicDetailRead:
        active_related_products = [
            related_product
            for related_product in product.related_products
            if related_product.status == ProductStatus.ACTIVE and related_product.is_listed
        ]
        return ProductPublicDetailRead.model_validate(product).model_copy(
            update={
                "related_product_ids": [item.id for item in active_related_products],
                "related_products": [
                    ProductCardRead.model_validate(item) for item in active_related_products
                ],
            }
        )

    def _product_has_category(self, product: Product, category_id: int) -> bool:
        return product.category_id == category_id or any(
            assignment.category_id == category_id for assignment in product.product_categories
        )

    def _rank_similar_products(
        self,
        candidates: list[Product],
        *,
        category_ids: set[int],
        tag_ids: set[int],
        exclude_product_ids: set[int],
        rank_category_overlap_count: bool,
    ) -> list[Product]:
        seen_ids: set[int] = set()
        scored: list[tuple[tuple[int, int, int, float, int], Product]] = []

        for candidate in candidates:
            if candidate.id in seen_ids or candidate.id in exclude_product_ids:
                continue
            seen_ids.add(candidate.id)
            if candidate.status != ProductStatus.ACTIVE or not candidate.is_listed:
                continue

            category_overlap = len(category_ids & self._product_category_ids(candidate))
            shared_tag_count = len(tag_ids & self._product_tag_ids(candidate))
            if category_overlap <= 0 and shared_tag_count <= 0:
                continue

            category_rank = (
                category_overlap if rank_category_overlap_count else int(category_overlap > 0)
            )
            search_priority = candidate.search_priority or 2
            created_at = candidate.created_at
            created_timestamp = created_at.timestamp() if created_at is not None else 0.0
            scored.append(
                (
                    (
                        -category_rank,
                        -shared_tag_count,
                        search_priority,
                        -created_timestamp,
                        -candidate.id,
                    ),
                    candidate,
                )
            )

        return [product for _score, product in sorted(scored, key=lambda item: item[0])]

    @staticmethod
    def _product_category_ids(product: Product) -> set[int]:
        category_ids = {product.category_id} if product.category_id is not None else set()
        category_ids.update(
            assignment.category_id
            for assignment in getattr(product, "product_categories", []) or []
            if assignment.category_id is not None
        )
        return category_ids

    @staticmethod
    def _product_tag_ids(product: Product) -> set[int]:
        return {tag.id for tag in getattr(product, "tags", []) or [] if tag.id is not None}

    async def _get_public_product_by_slug_or_alias(self, product_slug: str) -> Product | None:
        product = await self.repository.get_public_detail_by_slug(product_slug)
        if product is not None:
            return product

        product_id = await self.route_aliases.resolve_entity_id(
            RouteAliasEntityType.PRODUCT,
            product_slug,
        )
        if product_id is None:
            return None
        return await self.repository.get_public_detail_by_id(product_id)

    async def _get_category_by_slug_or_alias(self, category_slug: str) -> Category | None:
        category = await self.categories_repository.get_by_slug(category_slug)
        if category is not None:
            return category

        category_id = await self.route_aliases.resolve_entity_id(
            RouteAliasEntityType.CATEGORY,
            category_slug,
        )
        if category_id is None:
            return None
        return await self.categories_repository.get_by_id(category_id)

    async def get_product(self, product_id: int) -> Product:
        product = await self.repository.get_by_id(product_id)
        if product is None:
            raise AppError("Product not found", status.HTTP_404_NOT_FOUND)
        return product

    async def create_product(
        self,
        payload: ProductCreate,
        actor_user_id: int | None = None,
    ) -> Product:
        try:
            payload = await self._prepare_product_create_payload_slug(payload)
            await self.route_aliases.ensure_slug_available(
                RouteAliasEntityType.PRODUCT,
                payload.slug,
                conflict_message="Product slug conflicts with an active route alias",
            )
            product = await self.stage_product_with_variants(payload, [])
        except AppError:
            await self.session.rollback()
            raise
        product_id = await self._flush_commit_and_get_id(
            product,
            audit_callback=lambda created_product: self._record_audit(
                actor_user_id=actor_user_id,
                action="product.created",
                entity_type="product",
                entity_id=created_product.id,
                before_data=None,
                after_data=self.audit_service.snapshot(created_product, PRODUCT_AUDIT_FIELDS),
            ),
        )
        created_product = await self.repository.get_by_id(product_id)
        if created_product is None:
            raise AppError("Product not found", status.HTTP_404_NOT_FOUND)
        await self._invalidate_product_cache(product_id=created_product.id)
        return created_product

    async def stage_product_with_variants(
        self,
        payload: ProductCreate,
        variants: list[ProductVariantCreate],
    ) -> Product:
        """Validate and stage a product graph without committing the transaction."""
        tags = await self._resolve_tags(payload.tag_ids)
        related_product_ids = await self._resolve_related_product_ids(
            payload.related_product_ids,
        )
        category_assignments = await self._resolve_category_assignments(
            category_id=payload.category_id,
            categories=payload.categories,
        )
        self._validate_images(payload.images)
        self._validate_new_product_size_grid(payload.size_grid)

        product_data = payload.model_dump(
            exclude={"tag_ids", "images", "categories", "related_product_ids"}
        )
        product_data["category_id"] = self._primary_category_id(category_assignments)
        product = Product(
            **product_data,
            tags=tags,
            product_categories=[
                ProductCategory(
                    category_id=assignment.category_id,
                    priority=assignment.priority,
                )
                for assignment in category_assignments
            ],
            images=[ProductImage(**image.model_dump()) for image in payload.images],
            related_product_links=[],
        )
        self.repository.add(product)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            raise AppError(
                "Product slug or variant SKU already exists",
                status.HTTP_409_CONFLICT,
            ) from exc

        self._validate_related_product_self_reference(product.id, related_product_ids)
        product.related_product_links.extend(
            ProductRelatedProduct(related_product_id=related_product_id, position=position)
            for position, related_product_id in enumerate(related_product_ids)
        )

        prepared_payloads = await self._prepare_variant_create_payloads(variants)
        combinations: set[tuple[str, str | None]] = set()
        for variant_payload in prepared_payloads:
            variant = self.prepare_product_variant(
                product_id=product.id,
                size_grid=product.size_grid,
                payload=variant_payload,
            )
            combination = (
                variant.size,
                variant.color.strip().casefold() if variant.color else None,
            )
            if combination in combinations:
                color = variant.color or "without color"
                raise AppError(
                    f"Duplicate product variant for size {variant.size} and color {color}",
                    status.HTTP_400_BAD_REQUEST,
                )
            combinations.add(combination)
            self.variants_repository.add(variant)

        return product

    async def update_product(
        self,
        product_id: int,
        payload: ProductUpdate,
        actor_user_id: int | None = None,
    ) -> Product:
        product = await self.get_product(product_id)
        before_data = self.audit_service.snapshot(product, PRODUCT_AUDIT_FIELDS)
        data = payload.model_dump(
            exclude_unset=True,
            exclude={"tag_ids", "images", "categories", "related_product_ids"},
        )
        candidate_base_price = data.get("base_price", product.base_price)
        candidate_old_price = data.get("old_price", product.old_price)
        self._validate_price_pair(candidate_base_price, candidate_old_price)
        if data.get("search_priority") is None and "search_priority" in data:
            raise AppError("search_priority must be 1, 2, or 3", status.HTTP_400_BAD_REQUEST)
        if data.get("size_grid") is None and "size_grid" in data:
            raise AppError(
                "size_grid must be clothing_alpha or shoes_eu",
                status.HTTP_400_BAD_REQUEST,
            )
        if data.get("size_group") is None and "size_group" in data:
            raise AppError(
                "size_group must be CLOTHING, FOOTWEAR, or ONE_SIZE",
                status.HTTP_400_BAD_REQUEST,
            )
        candidate_size_grid = data.get("size_grid", product.size_grid)
        if candidate_size_grid != product.size_grid:
            self._validate_product_size_grid_change(product, candidate_size_grid)
            invalid_sizes = incompatible_sizes(
                candidate_size_grid,
                (variant.size for variant in product.variants),
            )
            if invalid_sizes:
                joined = ", ".join(invalid_sizes)
                raise AppError(
                    f"Cannot change size_grid to {candidate_size_grid.value}; "
                    f"incompatible variant sizes: {joined}. Clean variants where safe or create "
                    "a new product.",
                    status.HTTP_400_BAD_REQUEST,
                )

        candidate_badge_type = data.get("image_badge_type", product.image_badge_type)
        candidate_badge_text = data.get("image_badge_text", product.image_badge_text)
        if candidate_badge_type == ProductImageBadgeType.CUSTOM and not candidate_badge_text:
            raise AppError(
                "image_badge_text is required for a custom badge",
                status.HTTP_400_BAD_REQUEST,
            )
        if candidate_badge_type != ProductImageBadgeType.CUSTOM:
            data["image_badge_text"] = None

        next_slug = data.get("slug")
        slug_is_changing = next_slug is not None and next_slug != product.slug
        if slug_is_changing:
            existing_slug_owner = await self.repository.get_by_slug(next_slug)
            if existing_slug_owner is not None and existing_slug_owner.id != product.id:
                raise AppError(
                    "Product slug or variant SKU already exists",
                    status.HTTP_409_CONFLICT,
                )
            await self.route_aliases.ensure_slug_available(
                RouteAliasEntityType.PRODUCT,
                next_slug,
                entity_id=product.id,
                conflict_message="Product slug conflicts with an active route alias",
            )

        categories_were_provided = "categories" in payload.model_fields_set
        category_id_was_provided = "category_id" in data
        resolved_tags = None
        if "tag_ids" in payload.model_fields_set and payload.tag_ids is not None:
            resolved_tags = await self._resolve_tags(payload.tag_ids)

        if categories_were_provided or category_id_was_provided:
            category_assignments = await self._resolve_category_assignments(
                category_id=data.get("category_id", product.category_id),
                categories=payload.categories if categories_were_provided else None,
            )
            await self._sync_category_assignments(product, category_assignments)
            data["category_id"] = self._primary_category_id(category_assignments)

        if resolved_tags is not None:
            self._sync_tags(product, resolved_tags)

        if slug_is_changing:
            await self.route_aliases.create_alias_for_slug_change(
                RouteAliasEntityType.PRODUCT,
                entity_id=product.id,
                old_slug=product.slug,
                new_slug=next_slug,
                created_by_user_id=actor_user_id,
                conflict_message="Product slug conflicts with an active route alias",
            )

        if (
            "related_product_ids" in payload.model_fields_set
            and payload.related_product_ids is not None
        ):
            related_product_ids = await self._resolve_related_product_ids(
                payload.related_product_ids,
                product_id=product.id,
            )
            await self._sync_related_products(product, related_product_ids)

        stale_image_paths: list[str] = []
        if "images" in payload.model_fields_set and payload.images is not None:
            self._validate_images(payload.images)
            next_file_paths = {image.file_path for image in payload.images}
            stale_image_paths = [
                path
                for image in product.images
                if image.file_path not in next_file_paths
                for path in self._product_image_paths(image)
            ]
            product.images = [ProductImage(**image.model_dump()) for image in payload.images]

        for field, value in data.items():
            setattr(product, field, value)

        product_id = await self._flush_commit_and_get_id(
            product,
            audit_callback=lambda updated_product: self._record_audit(
                actor_user_id=actor_user_id,
                action="product.updated",
                entity_type="product",
                entity_id=updated_product.id,
                before_data=before_data,
                after_data=self.audit_service.snapshot(updated_product, PRODUCT_AUDIT_FIELDS),
            ),
        )
        updated_product = await self.repository.get_by_id(product_id)
        if updated_product is None:
            raise AppError("Product not found", status.HTTP_404_NOT_FOUND)
        self._delete_upload_paths(stale_image_paths, stage="product_image_replacement")
        await self._invalidate_product_cache(product_id=updated_product.id)
        return updated_product

    async def update_product_status(
        self,
        product_id: int,
        payload: ProductStatusUpdate,
        actor_user_id: int | None = None,
    ) -> Product:
        return await self._set_product_status(
            product_id,
            payload.status,
            actor_user_id=actor_user_id,
            action="product.status_changed",
        )

    async def archive_product(
        self,
        product_id: int,
        actor_user_id: int | None = None,
    ) -> Product:
        return await self._set_product_status(
            product_id,
            ProductStatus.ARCHIVED,
            actor_user_id=actor_user_id,
            action="product.archived",
        )

    async def delete_product(self, product_id: int) -> None:
        product = await self.get_product(product_id)
        image_paths = [
            path
            for image in product.images
            for path in self._product_image_paths(image)
        ]
        await self.repository.delete(product)
        await self._commit()
        self._delete_upload_paths(image_paths, stage="product_delete")
        await self._invalidate_product_cache(product_id=product_id)

    async def list_public_product_variants(self, product_id: int) -> ProductVariantList:
        product = await self.repository.get_active_by_id(product_id)
        if product is None:
            raise AppError("Product not found", status.HTTP_404_NOT_FOUND)
        variants = await self.variants_repository.list_by_product_id(product_id, active_only=True)
        return ProductVariantList(items=variants)

    async def list_product_variants(self, product_id: int) -> ProductVariantList:
        await self.get_product(product_id)
        variants = await self.variants_repository.list_by_product_id(product_id)
        return ProductVariantList(items=variants)

    async def generate_variant_skus(self, count: int) -> ProductVariantSkuList:
        existing_skus = await self.variants_repository.list_skus()
        return ProductVariantSkuList(
            items=self._allocate_numeric_variant_skus(existing_skus, count)
        )

    async def generate_product_slugs(self, count: int) -> ProductSlugList:
        existing_slugs = await self.repository.list_numeric_slug_candidates()
        alias_slugs = await self.route_aliases.repository.list_active_alias_slugs(
            RouteAliasEntityType.PRODUCT
        )
        existing_slugs.extend(alias_slugs)
        return ProductSlugList(items=self._allocate_numeric_product_slugs(existing_slugs, count))

    async def _prepare_product_create_payload_slug(self, payload: ProductCreate) -> ProductCreate:
        if payload.slug is not None:
            return payload
        generated_slug = (await self.generate_product_slugs(1)).items[0]
        return payload.model_copy(update={"slug": generated_slug})

    async def create_product_variant(
        self,
        product_id: int,
        payload: ProductVariantCreate,
        actor_user_id: int | None = None,
    ) -> ProductVariant:
        product = await self.get_product(product_id)
        payload = (await self._prepare_variant_create_payloads([payload]))[0]
        variant = self.prepare_product_variant(
            product_id=product_id,
            size_grid=product.size_grid,
            payload=payload,
        )
        self.variants_repository.add(variant)
        variant_id = await self._flush_commit_and_get_id(
            variant,
            audit_callback=lambda created_variant: self._record_audit(
                actor_user_id=actor_user_id,
                action="variant.created",
                entity_type="product_variant",
                entity_id=created_variant.id,
                before_data=None,
                after_data=self.audit_service.snapshot(created_variant, VARIANT_AUDIT_FIELDS),
                metadata={"product_id": product_id},
            ),
        )
        created_variant = await self.variants_repository.get_by_id(variant_id)
        if created_variant is None:
            raise AppError("Product variant not found", status.HTTP_404_NOT_FOUND)
        await self._invalidate_product_cache(product_id=created_variant.product_id)
        return created_variant

    def prepare_product_variant(
        self,
        *,
        product_id: int,
        size_grid: ProductSizeGrid,
        payload: ProductVariantCreate,
    ) -> ProductVariant:
        self._validate_inventory(payload.stock_quantity, payload.reserved_quantity)
        if payload.sku is None:
            raise AppError(
                "Product variant SKU was not generated",
                status.HTTP_400_BAD_REQUEST,
            )
        variant_data = payload.model_dump()
        variant_data["size"] = self._normalize_variant_size(size_grid, payload.size)
        return ProductVariant(product_id=product_id, **variant_data)

    async def _prepare_variant_create_payloads(
        self,
        variants: list[ProductVariantCreate],
    ) -> list[ProductVariantCreate]:
        if not variants:
            return []
        if all(
            payload.sku is not None
            and not self._is_numeric_variant_sku_candidate(payload.sku)
            for payload in variants
        ):
            return variants

        existing_skus = await self.variants_repository.list_skus()
        reserved_skus: set[str] = set()
        return [
            self._prepare_variant_create_payload_sku(
                payload,
                existing_skus=existing_skus,
                reserved_skus=reserved_skus,
            )
            for payload in variants
        ]

    def _prepare_variant_create_payload_sku(
        self,
        payload: ProductVariantCreate,
        *,
        existing_skus: list[str],
        reserved_skus: set[str],
    ) -> ProductVariantCreate:
        sku = payload.sku
        existing_sku_set = set(existing_skus)
        if sku is not None and not self._is_numeric_variant_sku_candidate(sku):
            reserved_skus.add(sku)
            return payload

        if (
            sku is not None
            and self._numeric_variant_sku_value(sku) is not None
            and sku not in existing_sku_set
            and sku not in reserved_skus
        ):
            reserved_skus.add(sku)
            return payload

        generated_sku = self._allocate_numeric_variant_skus(
            existing_skus,
            1,
            reserved_skus=reserved_skus,
        )[0]
        reserved_skus.add(generated_sku)
        return payload.model_copy(update={"sku": generated_sku})

    def _allocate_numeric_variant_skus(
        self,
        existing_skus: list[str],
        count: int,
        *,
        reserved_skus: set[str] | None = None,
    ) -> list[str]:
        used_numbers = {
            value
            for sku in [*existing_skus, *(reserved_skus or set())]
            if (value := self._numeric_variant_sku_value(sku)) is not None
        }
        generated: list[str] = []

        for value in range(NUMERIC_VARIANT_SKU_MIN, NUMERIC_VARIANT_SKU_MAX + 1):
            if value in used_numbers:
                continue
            used_numbers.add(value)
            generated.append(self._format_numeric_variant_sku(value))
            if len(generated) == count:
                return generated

        raise AppError(
            NUMERIC_VARIANT_SKU_EXHAUSTED_MESSAGE,
            status.HTTP_400_BAD_REQUEST,
        )

    @staticmethod
    def _numeric_variant_sku_value(sku: str) -> int | None:
        if not ProductsService._is_numeric_variant_sku_candidate(sku):
            return None
        value = int(sku)
        if value < NUMERIC_VARIANT_SKU_MIN or value > NUMERIC_VARIANT_SKU_MAX:
            return None
        return value

    @staticmethod
    def _is_numeric_variant_sku_candidate(sku: str) -> bool:
        return len(sku) == 5 and all("0" <= char <= "9" for char in sku)

    @staticmethod
    def _format_numeric_variant_sku(value: int) -> str:
        return f"{value:05d}"

    def _allocate_numeric_product_slugs(
        self,
        existing_slugs: list[str],
        count: int,
    ) -> list[str]:
        return allocate_numeric_identifiers(
            existing_slugs,
            count,
            min_value=NUMERIC_PRODUCT_SLUG_MIN,
            max_value=NUMERIC_PRODUCT_SLUG_MAX,
            width=5,
            exhausted_message=NUMERIC_PRODUCT_SLUG_EXHAUSTED_MESSAGE,
        )

    @staticmethod
    def _numeric_product_slug_value(slug: str) -> int | None:
        if not ProductsService._is_numeric_product_slug_candidate(slug):
            return None
        value = int(slug)
        if value < NUMERIC_PRODUCT_SLUG_MIN or value > NUMERIC_PRODUCT_SLUG_MAX:
            return None
        return value

    @staticmethod
    def _is_numeric_product_slug_candidate(slug: str) -> bool:
        return len(slug) == 5 and all("0" <= char <= "9" for char in slug)

    @staticmethod
    def _format_numeric_product_slug(value: int) -> str:
        return f"{value:05d}"

    async def update_product_variant(
        self,
        variant_id: int,
        payload: ProductVariantUpdate,
        actor_user_id: int | None = None,
    ) -> ProductVariant:
        variant = await self.get_product_variant(variant_id)
        before_data = self.audit_service.snapshot(variant, VARIANT_AUDIT_FIELDS)
        data = payload.model_dump(exclude_unset=True)
        if "size" in data:
            product = await self.get_product(variant.product_id)
            data["size"] = self._normalize_variant_size(product.size_grid, data["size"])
        stock_quantity = data.get("stock_quantity", variant.stock_quantity)
        reserved_quantity = data.get("reserved_quantity", variant.reserved_quantity)
        self._validate_inventory(stock_quantity, reserved_quantity)

        for field, value in data.items():
            setattr(variant, field, value)

        variant_id = await self._flush_commit_and_get_id(
            variant,
            audit_callback=lambda updated_variant: self._record_audit(
                actor_user_id=actor_user_id,
                action="variant.updated",
                entity_type="product_variant",
                entity_id=updated_variant.id,
                before_data=before_data,
                after_data=self.audit_service.snapshot(updated_variant, VARIANT_AUDIT_FIELDS),
                metadata={"product_id": updated_variant.product_id},
            ),
        )
        updated_variant = await self.variants_repository.get_by_id(variant_id)
        if updated_variant is None:
            raise AppError("Product variant not found", status.HTTP_404_NOT_FOUND)
        await self._invalidate_product_cache(product_id=updated_variant.product_id)
        return updated_variant

    async def deactivate_product_variant(
        self,
        variant_id: int,
        actor_user_id: int | None = None,
    ) -> ProductVariant:
        variant = await self.get_product_variant(variant_id)
        before_data = self.audit_service.snapshot(variant, VARIANT_AUDIT_FIELDS)
        variant.is_active = False
        variant_id = await self._flush_commit_and_get_id(
            variant,
            audit_callback=lambda deactivated_variant: self._record_audit(
                actor_user_id=actor_user_id,
                action="variant.deactivated",
                entity_type="product_variant",
                entity_id=deactivated_variant.id,
                before_data=before_data,
                after_data=self.audit_service.snapshot(
                    deactivated_variant,
                    VARIANT_AUDIT_FIELDS,
                ),
                metadata={"product_id": deactivated_variant.product_id},
            ),
        )
        updated_variant = await self.variants_repository.get_by_id(variant_id)
        if updated_variant is None:
            raise AppError("Product variant not found", status.HTTP_404_NOT_FOUND)
        await self._invalidate_product_cache(product_id=updated_variant.product_id)
        return updated_variant

    async def delete_product_variant(self, variant_id: int) -> None:
        variant = await self.get_product_variant(variant_id)
        product_id = variant.product_id
        await self.variants_repository.delete(variant)
        await self._commit()
        await self._invalidate_product_cache(product_id=product_id)

    async def get_product_variant(self, variant_id: int) -> ProductVariant:
        variant = await self.variants_repository.get_by_id(variant_id)
        if variant is None:
            raise AppError("Product variant not found", status.HTTP_404_NOT_FOUND)
        return variant

    async def _ensure_category_exists(self, category_id: int | None) -> None:
        if category_id is None:
            return
        category = await self.categories_repository.get_by_id(category_id)
        if category is None:
            raise AppError("Category not found", status.HTTP_404_NOT_FOUND)

    async def _resolve_category_assignments(
        self,
        *,
        category_id: int | None,
        categories: list[ProductCategoryInput] | None,
    ) -> list[ProductCategoryInput]:
        assignments = (
            [ProductCategoryInput(category_id=category_id, priority=1)]
            if categories is None and category_id is not None
            else categories or []
        )

        for assignment in assignments:
            await self._ensure_category_exists(assignment.category_id)

        return sorted(assignments, key=lambda assignment: assignment.priority)

    def _primary_category_id(
        self,
        assignments: list[ProductCategoryInput],
    ) -> int | None:
        if not assignments:
            return None
        return min(assignments, key=lambda assignment: assignment.priority).category_id

    async def _resolve_tags(self, tag_ids: list[int]) -> list[Tag]:
        unique_tag_ids = list(dict.fromkeys(tag_ids))
        tags = await self.tags_repository.list_by_ids(unique_tag_ids)
        if len(tags) != len(unique_tag_ids):
            found_ids = {tag.id for tag in tags}
            missing_ids = sorted(set(unique_tag_ids) - found_ids)
            joined = ", ".join(str(tag_id) for tag_id in missing_ids)
            raise AppError(f"Unknown tag_ids: {joined}", status.HTTP_400_BAD_REQUEST)
        return tags

    async def _resolve_related_product_ids(
        self,
        related_product_ids: list[int],
        *,
        product_id: int | None = None,
    ) -> list[int]:
        if not related_product_ids:
            return []
        unique_ids = list(dict.fromkeys(related_product_ids))
        if len(unique_ids) != len(related_product_ids):
            raise AppError(
                "Duplicate related product IDs are not allowed",
                status.HTTP_400_BAD_REQUEST,
            )
        if product_id is not None:
            self._validate_related_product_self_reference(product_id, unique_ids)

        found_ids = await self.repository.list_existing_ids(unique_ids)
        if len(found_ids) != len(unique_ids):
            missing_ids = sorted(set(unique_ids) - found_ids)
            joined = ", ".join(str(related_id) for related_id in missing_ids)
            raise AppError(
                f"Unknown related product IDs: {joined}",
                status.HTTP_400_BAD_REQUEST,
            )
        return unique_ids

    def _validate_related_product_self_reference(
        self,
        product_id: int,
        related_product_ids: list[int],
    ) -> None:
        if product_id in related_product_ids:
            raise AppError(
                "A product cannot be related to itself",
                status.HTTP_400_BAD_REQUEST,
            )

    async def _sync_category_assignments(
        self,
        product: Product,
        assignments: list[ProductCategoryInput],
    ) -> None:
        current = sorted(
            (assignment.category_id, assignment.priority)
            for assignment in product.product_categories
        )
        desired = sorted(
            (assignment.category_id, assignment.priority) for assignment in assignments
        )
        if current == desired:
            return

        product.product_categories.clear()
        await self.session.flush()
        product.product_categories.extend(
            ProductCategory(
                category_id=assignment.category_id,
                priority=assignment.priority,
            )
            for assignment in assignments
        )

    def _sync_tags(self, product: Product, tags: list[Tag]) -> None:
        if {tag.id for tag in product.tags} == {tag.id for tag in tags}:
            return
        product.tags = tags

    async def _sync_related_products(
        self,
        product: Product,
        related_product_ids: list[int],
    ) -> None:
        if product.related_product_ids == related_product_ids:
            return
        product.related_product_links.clear()
        await self.session.flush()
        product.related_product_links.extend(
            ProductRelatedProduct(related_product_id=related_product_id, position=position)
            for position, related_product_id in enumerate(related_product_ids)
        )

    def _validate_images(self, images: list[ProductImageCreate]) -> None:
        primary_count = sum(1 for image in images if image.is_primary)
        if primary_count > 1:
            raise AppError("Only one primary product image is allowed", status.HTTP_400_BAD_REQUEST)

    def _validate_inventory(self, stock_quantity: int, reserved_quantity: int) -> None:
        try:
            validate_inventory_quantities(stock_quantity, reserved_quantity)
        except InventoryValidationError as exc:
            raise AppError(str(exc), status.HTTP_400_BAD_REQUEST) from exc

    def _normalize_variant_size(self, size_grid: ProductSizeGrid, size: str) -> str:
        try:
            return normalize_size(size_grid, size)
        except SizeGridValidationError as exc:
            raise AppError(str(exc), status.HTTP_400_BAD_REQUEST) from exc

    def _normalize_size_filter(
        self,
        *,
        size_grid: ProductSizeGrid | None,
        size: str | None,
    ) -> str | None:
        if size is None:
            return None
        normalized = size.strip()
        if not normalized:
            raise AppError("size filter must not be empty", status.HTTP_400_BAD_REQUEST)
        if size_grid is None:
            return normalized.upper() if not normalized.isdigit() else normalized
        return self._normalize_variant_size(size_grid, normalized)

    def _validate_price_pair(
        self,
        base_price: Decimal,
        old_price: Decimal | None,
    ) -> None:
        if old_price is not None and old_price <= base_price:
            raise AppError(
                "old_price must be greater than base_price",
                status.HTTP_400_BAD_REQUEST,
            )

    async def _set_product_status(
        self,
        product_id: int,
        product_status: ProductStatus,
        *,
        actor_user_id: int | None,
        action: str,
    ) -> Product:
        product = await self.get_product(product_id)
        before_data = self.audit_service.snapshot(product, PRODUCT_AUDIT_FIELDS)
        product.status = product_status
        product_id = await self._flush_commit_and_get_id(
            product,
            audit_callback=lambda updated_product: self._record_audit(
                actor_user_id=actor_user_id,
                action=action,
                entity_type="product",
                entity_id=updated_product.id,
                before_data=before_data,
                after_data=self.audit_service.snapshot(updated_product, PRODUCT_AUDIT_FIELDS),
            ),
        )
        updated_product = await self.repository.get_by_id(product_id)
        if updated_product is None:
            raise AppError("Product not found", status.HTTP_404_NOT_FOUND)
        await self._invalidate_product_cache(product_id=updated_product.id)
        return updated_product

    async def _invalidate_product_cache(self, *, product_id: int | None = None) -> None:
        if self.cache is None:
            return
        if product_id is not None:
            await self.cache.delete(public_product_detail_key(product_id))
        await self.cache.delete_patterns(*product_cache_patterns())

    def _product_image_paths(self, image: ProductImage) -> list[str]:
        return [
            path
            for path in (
                image.file_path,
                image.thumbnail_path,
                image.card_path,
                image.detail_path,
            )
            if path
        ]

    def _delete_upload_paths(self, paths: list[str], *, stage: str) -> None:
        for path in paths:
            try:
                self.storage.delete(path)
            except OSError:
                logger.warning("Failed to delete upload during %s: %s", stage, path)

    async def _flush_commit_and_get_id(
        self,
        instance: Product | ProductVariant,
        audit_callback: Callable[[Product | ProductVariant], Awaitable[None]] | None = None,
    ) -> int:
        try:
            await self.session.flush()
            if audit_callback is not None:
                await audit_callback(instance)
            instance_id = instance.id
            await self.session.commit()
            return instance_id
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(
                "Product slug or variant SKU already exists",
                status.HTTP_409_CONFLICT,
            ) from exc

    async def _commit(self) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(
                "Product slug or variant SKU already exists",
                status.HTTP_409_CONFLICT,
            ) from exc

    async def _record_audit(
        self,
        *,
        actor_user_id: int | None,
        action: str,
        entity_type: str,
        entity_id: int | None,
        before_data: dict[str, object] | None,
        after_data: dict[str, object] | None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        await self.audit_service.record_action(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_data=before_data,
            after_data=after_data,
            metadata=metadata,
        )

    async def _track_event(
        self,
        event_name: str,
        *,
        user_id: int | None,
        product_id: int | None = None,
    ) -> None:
        if self.analytics_tracker is None:
            return
        try:
            await self.analytics_tracker.track(
                event_name,
                user_id=user_id,
                product_id=product_id,
            )
        except Exception:
            logger.warning("Failed to track product analytics event %s", event_name, exc_info=True)

    async def _track_search_event(
        self,
        search: str | None,
        *,
        user_id: int | None,
        result_count: int | None,
    ) -> None:
        sanitized_query = sanitize_search_query(search)
        if sanitized_query is None:
            return
        if self.analytics_tracker is None:
            return
        try:
            await self.analytics_tracker.track(
                "search.performed",
                user_id=user_id,
                metadata={"query": sanitized_query, "result_count": result_count},
            )
        except Exception:
            logger.warning("Failed to track product search analytics event", exc_info=True)

    def _validate_new_product_size_grid(self, size_grid: ProductSizeGrid) -> None:
        if is_legacy_product_size_grid(size_grid):
            raise AppError(
                "size_grid shoes_ru is legacy. Use shoes_eu for new footwear products.",
                status.HTTP_400_BAD_REQUEST,
            )

    def _validate_product_size_grid_change(
        self,
        product: Product,
        candidate_size_grid: ProductSizeGrid,
    ) -> None:
        if is_legacy_product_size_grid(candidate_size_grid):
            raise AppError(
                "size_grid shoes_ru is legacy and cannot be selected for new footwear. "
                "Use shoes_eu.",
                status.HTTP_400_BAD_REQUEST,
            )
        if (
            is_footwear_size_grid(product.size_grid)
            and is_footwear_size_grid(candidate_size_grid)
            and product.variants
        ):
            raise AppError(
                "Cannot change size_grid between legacy shoes_ru and shoes_eu while variants "
                "exist; create a new EU footwear product or remove variants first.",
                status.HTTP_400_BAD_REQUEST,
            )
