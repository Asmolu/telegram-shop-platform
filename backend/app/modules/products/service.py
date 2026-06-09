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
from app.common.pagination import PageMeta
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import Product, ProductCategory, ProductImage, ProductStatus, ProductVariant, Tag
from app.modules.analytics.service import AnalyticsTracker
from app.modules.audit.service import AuditService, NoopAuditService
from app.modules.categories.repository import CategoriesRepository
from app.modules.products.inventory import InventoryValidationError, validate_inventory_quantities
from app.modules.products.repository import ProductsRepository, ProductVariantsRepository
from app.modules.products.schemas import (
    ProductCategoryInput,
    ProductCreate,
    ProductImageCreate,
    ProductList,
    ProductRead,
    ProductStatusUpdate,
    ProductUpdate,
    ProductVariantCreate,
    ProductVariantList,
    ProductVariantUpdate,
)
from app.modules.products.search import sanitize_search_query
from app.modules.tags.repository import TagsRepository

logger = logging.getLogger(__name__)

PRODUCT_AUDIT_FIELDS = (
    "name",
    "slug",
    "description",
    "base_price",
    "old_price",
    "search_priority",
    "search_aliases",
    "status",
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


class ProductsService:
    def __init__(
        self,
        session: AsyncSession,
        analytics_tracker: AnalyticsTracker | None = None,
        audit_service: AuditService | None = None,
        cache: CacheService | None = None,
    ) -> None:
        self.session = session
        self.repository = ProductsRepository(session)
        self.variants_repository = ProductVariantsRepository(session)
        self.categories_repository = CategoriesRepository(session)
        self.tags_repository = TagsRepository(session)
        self.analytics_tracker = analytics_tracker
        self.audit_service = audit_service or NoopAuditService()
        self.cache = cache

    async def list_public_products(
        self,
        *,
        limit: int,
        offset: int,
        category_id: int | None = None,
        tag_id: int | None = None,
        status: ProductStatus | None = None,
        search: str | None = None,
        user_id: int | None = None,
    ) -> ProductList:
        if status is not None and status != ProductStatus.ACTIVE:
            result = ProductList(items=[], meta=PageMeta(limit=limit, offset=offset, total=0))
            await self._track_search_event(search, user_id=user_id, result_count=0)
            return result

        cache_key = public_products_list_key(
            limit=limit,
            offset=offset,
            category_id=category_id,
            tag_id=tag_id,
            status=status,
            search=search,
        )
        if self.cache is not None:
            cached = await self.cache.get_model(cache_key, ProductList)
            if cached is not None:
                await self._track_search_event(
                    search,
                    user_id=user_id,
                    result_count=cached.meta.total,
                )
                return cached

        items, total = await self.repository.list(
            limit=limit,
            offset=offset,
            category_id=category_id,
            tag_id=tag_id,
            status=ProductStatus.ACTIVE,
            search=search,
            active_variants_only=True,
        )
        result = ProductList(items=items, meta=PageMeta(limit=limit, offset=offset, total=total))
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
    ) -> ProductList:
        items, total = await self.repository.list(
            limit=limit,
            offset=offset,
            category_id=category_id,
            tag_id=tag_id,
            status=status,
            search=search,
        )
        return ProductList(items=items, meta=PageMeta(limit=limit, offset=offset, total=total))

    async def get_public_product(
        self,
        product_id: int,
        user_id: int | None = None,
    ) -> Product | ProductRead:
        cache_key = public_product_detail_key(product_id)
        if self.cache is not None:
            cached = await self.cache.get_model(cache_key, ProductRead)
            if cached is not None:
                await self._track_event("product.viewed", user_id=user_id, product_id=product_id)
                return cached

        product = await self.repository.get_active_by_id(product_id)
        if product is None:
            raise AppError("Product not found", status.HTTP_404_NOT_FOUND)
        result = ProductRead.model_validate(product)
        if self.cache is not None:
            await self.cache.set_model(
                cache_key,
                result,
                settings.cache_public_product_detail_ttl_seconds,
            )
        await self._track_event("product.viewed", user_id=user_id, product_id=product.id)
        return result

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
        tags = await self._resolve_tags(payload.tag_ids)
        category_assignments = await self._resolve_category_assignments(
            category_id=payload.category_id,
            categories=payload.categories,
        )
        self._validate_images(payload.images)

        product_data = payload.model_dump(exclude={"tag_ids", "images", "categories"})
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
        )
        self.repository.add(product)
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

    async def update_product(
        self,
        product_id: int,
        payload: ProductUpdate,
        actor_user_id: int | None = None,
    ) -> Product:
        product = await self.get_product(product_id)
        before_data = self.audit_service.snapshot(product, PRODUCT_AUDIT_FIELDS)
        data = payload.model_dump(exclude_unset=True, exclude={"tag_ids", "images", "categories"})
        candidate_base_price = data.get("base_price", product.base_price)
        candidate_old_price = data.get("old_price", product.old_price)
        self._validate_price_pair(candidate_base_price, candidate_old_price)
        if data.get("search_priority") is None and "search_priority" in data:
            raise AppError("search_priority must be 1, 2, or 3", status.HTTP_400_BAD_REQUEST)

        categories_were_provided = "categories" in payload.model_fields_set
        category_id_was_provided = "category_id" in data
        if categories_were_provided or category_id_was_provided:
            category_assignments = await self._resolve_category_assignments(
                category_id=data.get("category_id", product.category_id),
                categories=payload.categories if categories_were_provided else None,
            )
            product.product_categories = [
                ProductCategory(
                    category_id=assignment.category_id,
                    priority=assignment.priority,
                )
                for assignment in category_assignments
            ]
            data["category_id"] = self._primary_category_id(category_assignments)

        if "tag_ids" in payload.model_fields_set and payload.tag_ids is not None:
            product.tags = await self._resolve_tags(payload.tag_ids)

        if "images" in payload.model_fields_set and payload.images is not None:
            self._validate_images(payload.images)
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
        await self.repository.delete(product)
        await self._commit()
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

    async def create_product_variant(
        self,
        product_id: int,
        payload: ProductVariantCreate,
        actor_user_id: int | None = None,
    ) -> ProductVariant:
        await self.get_product(product_id)
        self._validate_inventory(payload.stock_quantity, payload.reserved_quantity)

        variant = ProductVariant(product_id=product_id, **payload.model_dump())
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

    async def update_product_variant(
        self,
        variant_id: int,
        payload: ProductVariantUpdate,
        actor_user_id: int | None = None,
    ) -> ProductVariant:
        variant = await self.get_product_variant(variant_id)
        before_data = self.audit_service.snapshot(variant, VARIANT_AUDIT_FIELDS)
        data = payload.model_dump(exclude_unset=True)
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
            raise AppError("Tag not found", status.HTTP_404_NOT_FOUND)
        return tags

    def _validate_images(self, images: list[ProductImageCreate]) -> None:
        primary_count = sum(1 for image in images if image.is_primary)
        if primary_count > 1:
            raise AppError("Only one primary product image is allowed", status.HTTP_400_BAD_REQUEST)

    def _validate_inventory(self, stock_quantity: int, reserved_quantity: int) -> None:
        try:
            validate_inventory_quantities(stock_quantity, reserved_quantity)
        except InventoryValidationError as exc:
            raise AppError(str(exc), status.HTTP_400_BAD_REQUEST) from exc

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
