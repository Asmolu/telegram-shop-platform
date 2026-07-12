import logging
from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

from fastapi import UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.numeric_identifiers import allocate_numeric_identifiers
from app.common.pagination import PageMeta
from app.core.errors import AppError
from app.db.models import (
    Cart,
    CartItem,
    Look,
    LookImage,
    LookItem,
    LookStatus,
    Product,
    ProductImageBadgeType,
    ProductSizeGroup,
    ProductStatus,
    ProductVariant,
    RouteAliasEntityType,
)
from app.modules.cart.repository import CartRepository
from app.modules.cart.service import CartService
from app.modules.looks.repository import LooksRepository
from app.modules.looks.schemas import (
    LookAdminList,
    LookAdminRead,
    LookCardRead,
    LookCartAddRequest,
    LookCartAddResponse,
    LookCreate,
    LookDetailRead,
    LookImageRead,
    LookItemInput,
    LookList,
    LookProductSummaryRead,
    LookPublicItemRead,
    LookSlugList,
    LookUpdate,
)
from app.modules.products.schemas import ProductCardList
from app.modules.products.service import ProductsService
from app.modules.products.size_grids import is_footwear_size_grid
from app.modules.route_aliases.service import RouteAliasesService
from app.modules.uploads.service import UploadsService
from app.modules.uploads.storage import LocalStorageService

ONE_SIZE = "ONE_SIZE"
NUMERIC_LOOK_SLUG_MIN = 1
NUMERIC_LOOK_SLUG_MAX = 99999
NUMERIC_LOOK_SLUG_EXHAUSTED_MESSAGE = "Numeric Look slug range 00001-99999 is exhausted."
LOOK_SLUG_CONFLICT_MESSAGE = "Look slug already exists"
LOOK_ALIAS_CONFLICT_MESSAGE = "Look slug conflicts with an active route alias"
LOOK_PRODUCT_CONFLICT_MESSAGE = "Product is already included in this Look"
LOOK_SLUG_CONSTRAINT = "ix_looks_slug"
LOOK_ALIAS_CONSTRAINT = "uq_route_aliases_active_entity_type_alias_slug"
LOOK_PRODUCT_CONSTRAINT = "uq_look_items_look_product"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LookSizeSummary:
    available_sizes: list[str]
    available_clothing_sizes: list[str]
    available_footwear_sizes: list[str]
    requires_clothing_size: bool
    requires_footwear_size: bool
    is_available: bool


class LooksService:
    def __init__(
        self,
        session: AsyncSession,
        storage: LocalStorageService | None = None,
    ) -> None:
        self.session = session
        self.repository = LooksRepository(session)
        self.cart_repository = CartRepository(session)
        self.products_service = ProductsService(session)
        self.route_aliases = RouteAliasesService(session)
        self.storage = storage or LocalStorageService()

    async def list_public_looks(self, *, limit: int, offset: int) -> LookList:
        looks, total = await self.repository.list_public(limit=limit, offset=offset)
        return LookList(
            items=[self._build_card(look) for look in looks],
            meta=PageMeta(limit=limit, offset=offset, total=total),
        )

    async def get_public_look(self, slug: str) -> LookDetailRead:
        look = await self._get_public_look_by_slug_or_alias(slug)
        if look is None:
            raise AppError("Look not found", status.HTTP_404_NOT_FOUND)
        return self._build_detail(look)

    async def list_similar_products(
        self,
        slug: str,
        *,
        limit: int = 12,
    ) -> ProductCardList:
        look = await self._get_public_look_similarity_context_by_slug_or_alias(slug)
        if look is None:
            raise AppError("Look not found", status.HTTP_404_NOT_FOUND)

        component_products = [item.product for item in look.items]
        category_ids = {
            category_id
            for product in component_products
            for category_id in ProductsService._product_category_ids(product)
        }
        tag_ids = {
            tag_id
            for product in component_products
            for tag_id in ProductsService._product_tag_ids(product)
        }
        return await self.products_service.list_similar_products_for_context(
            category_ids=category_ids,
            tag_ids=tag_ids,
            exclude_product_ids={product.id for product in component_products},
            limit=limit,
            rank_category_overlap_count=True,
        )

    async def add_look_to_cart(
        self,
        *,
        slug: str,
        user_id: int,
        payload: LookCartAddRequest,
    ) -> LookCartAddResponse:
        look = await self._get_public_look_by_slug_or_alias(slug)
        if look is None:
            raise AppError("Look not found", status.HTTP_404_NOT_FOUND)

        selected_item_ids = list(dict.fromkeys(payload.selected_item_ids))
        if len(selected_item_ids) != len(payload.selected_item_ids):
            raise AppError("Selected look item ids must be unique", status.HTTP_400_BAD_REQUEST)

        items_by_id = {item.id: item for item in look.items}
        selected_items: list[LookItem] = []
        for item_id in selected_item_ids:
            item = items_by_id.get(item_id)
            if item is None:
                raise AppError(
                    "Selected look item does not belong to this Look",
                    status.HTTP_400_BAD_REQUEST,
                )
            selected_items.append(item)

        size_summary = self._size_summary(selected_items)
        clothing_size, footwear_size = self._requested_sizes_for_cart(
            payload,
            size_summary=size_summary,
        )

        resolved_items = [
            (
                item,
                self._resolve_variant_for_cart(
                    item,
                    clothing_size=clothing_size,
                    footwear_size=footwear_size,
                ),
            )
            for item in selected_items
        ]

        cart = await self._get_or_create_cart_for_mutation(user_id)
        additions_by_variant: dict[int, int] = {}
        for item, variant in resolved_items:
            additions_by_variant[variant.id] = (
                additions_by_variant.get(variant.id, 0) + item.quantity
            )

        for variant_id, added_quantity in additions_by_variant.items():
            variant = next(variant for _, variant in resolved_items if variant.id == variant_id)
            target_quantity = added_quantity + sum(
                cart_item.quantity
                for cart_item in cart.items
                if cart_item.product_variant_id == variant_id
            )
            if target_quantity > variant.available_quantity:
                raise AppError("Insufficient stock", status.HTTP_400_BAD_REQUEST)

        source_group_id = str(uuid4())
        for item, variant in resolved_items:
            self.cart_repository.add(
                CartItem(
                    cart_id=cart.id,
                    product_id=item.product_id,
                    product_variant_id=variant.id,
                    quantity=item.quantity,
                    is_selected=True,
                    source_type="LOOK",
                    source_look_id=look.id,
                    source_look_slug=look.slug,
                    source_look_title=look.title,
                    source_look_image_url=look.image_url,
                    source_group_id=source_group_id,
                )
            )

        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("Cart item already exists", status.HTTP_409_CONFLICT) from exc

        reloaded_cart = await self.cart_repository.get_by_user_id(user_id)
        if reloaded_cart is None:
            raise AppError("Cart not found", status.HTTP_404_NOT_FOUND)
        return LookCartAddResponse(
            message="Look items added to cart",
            cart=CartService(self.session)._build_cart_response(reloaded_cart),
        )

    async def list_admin_looks(
        self,
        *,
        limit: int,
        offset: int,
        status_filter: LookStatus | None = None,
    ) -> LookAdminList:
        looks, total = await self.repository.list_admin(
            limit=limit,
            offset=offset,
            status_filter=status_filter,
        )
        return LookAdminList(
            items=[LookAdminRead.model_validate(look) for look in looks],
            meta=PageMeta(limit=limit, offset=offset, total=total),
        )

    async def get_admin_look(self, look_id: int) -> LookAdminRead:
        look = await self.repository.get_admin_by_id(look_id)
        if look is None:
            raise AppError("Look not found", status.HTTP_404_NOT_FOUND)
        return LookAdminRead.model_validate(look)

    async def generate_look_slugs(self, count: int) -> LookSlugList:
        existing_slugs = await self.repository.list_numeric_slug_candidates()
        alias_slugs = await self.route_aliases.repository.list_active_alias_slugs(
            RouteAliasEntityType.LOOK
        )
        existing_slugs.extend(alias_slugs)
        return LookSlugList(
            items=allocate_numeric_identifiers(
                existing_slugs,
                count,
                min_value=NUMERIC_LOOK_SLUG_MIN,
                max_value=NUMERIC_LOOK_SLUG_MAX,
                width=5,
                exhausted_message=NUMERIC_LOOK_SLUG_EXHAUSTED_MESSAGE,
            )
        )

    async def create_admin_look(
        self,
        payload: LookCreate,
        actor_user_id: int | None = None,
    ) -> LookAdminRead:
        try:
            await self._ensure_slug_available(payload.slug)
            products_by_id = await self._validate_item_inputs(
                payload.items,
                target_status=payload.status,
            )
            look = Look(
                title=payload.title,
                slug=payload.slug,
                description=payload.description,
                status=payload.status,
                is_listed=payload.is_listed,
                search_priority=payload.search_priority,
                image_badge_type=payload.image_badge_type,
                image_badge_text=payload.image_badge_text,
                image_badge_color=payload.image_badge_color,
                image_badge_position=payload.image_badge_position,
                items=[
                    LookItem(
                        product_id=item.product_id,
                        product=products_by_id[item.product_id],
                        position=item.position,
                        quantity=item.quantity,
                        is_default_selected=item.is_default_selected,
                    )
                    for item in payload.items
                ],
            )
            self.repository.add(look)
        except AppError:
            await self.session.rollback()
            raise
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(
                self._look_integrity_error_message(
                    exc,
                    fallback_message="Could not create Look",
                ),
                status.HTTP_409_CONFLICT,
            ) from exc

        return await self._commit_and_return_admin(
            look,
            persistence_message="Could not create Look",
        )

    async def update_admin_look(
        self,
        look_id: int,
        payload: LookUpdate,
        actor_user_id: int | None = None,
    ) -> LookAdminRead:
        look = await self.repository.get_admin_by_id(look_id)
        if look is None:
            raise AppError("Look not found", status.HTTP_404_NOT_FOUND)

        try:
            next_slug = (
                payload.slug if payload.slug is not None and payload.slug != look.slug else None
            )
            if next_slug is not None:
                await self._ensure_slug_available(next_slug, entity_id=look.id)

            if payload.title is not None:
                look.title = payload.title
            if "description" in payload.model_fields_set:
                look.description = payload.description
            if payload.is_listed is not None:
                look.is_listed = payload.is_listed
            if payload.search_priority is not None:
                look.search_priority = payload.search_priority
            if payload.image_badge_type is not None:
                look.image_badge_type = payload.image_badge_type
            if "image_badge_text" in payload.model_fields_set:
                look.image_badge_text = payload.image_badge_text
            if "image_badge_color" in payload.model_fields_set:
                look.image_badge_color = payload.image_badge_color
            if "image_badge_position" in payload.model_fields_set:
                look.image_badge_position = payload.image_badge_position
            badge_type = look.image_badge_type or ProductImageBadgeType.NONE
            look.image_badge_type = badge_type
            if badge_type == ProductImageBadgeType.CUSTOM and not look.image_badge_text:
                raise AppError(
                    "image_badge_text is required for a custom badge",
                    status.HTTP_400_BAD_REQUEST,
                )
            if badge_type != ProductImageBadgeType.CUSTOM:
                look.image_badge_text = None
            if payload.status is not None:
                look.status = payload.status

            if payload.items is not None:
                products_by_id = await self._validate_item_inputs(
                    payload.items,
                    target_status=look.status,
                )
                await self._synchronize_items(
                    look,
                    payload.items,
                    products_by_id=products_by_id,
                )

            await self._validate_look_publishable(look)
            if next_slug is not None:
                await self.route_aliases.create_alias_for_slug_change(
                    RouteAliasEntityType.LOOK,
                    entity_id=look.id,
                    old_slug=look.slug,
                    new_slug=next_slug,
                    created_by_user_id=actor_user_id,
                    conflict_message=LOOK_ALIAS_CONFLICT_MESSAGE,
                )
                look.slug = next_slug
        except AppError:
            await self.session.rollback()
            raise
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(
                self._look_integrity_error_message(
                    exc,
                    fallback_message="Could not update Look",
                ),
                status.HTTP_409_CONFLICT,
            ) from exc

        return await self._commit_and_return_admin(
            look,
            persistence_message="Could not update Look",
        )

    async def archive_admin_look(self, look_id: int) -> LookAdminRead:
        look = await self.repository.get_admin_by_id(look_id)
        if look is None:
            raise AppError("Look not found", status.HTTP_404_NOT_FOUND)
        look.status = LookStatus.ARCHIVED
        return await self._commit_and_return_admin(
            look,
            persistence_message="Could not archive Look",
        )

    async def upload_image(
        self,
        *,
        look_id: int,
        file: UploadFile,
        alt_text: str | None = None,
        position: int | None = None,
        is_primary: bool = False,
    ) -> LookImageRead:
        look = await self.repository.get_admin_by_id(look_id)
        if look is None:
            raise AppError("Look not found", status.HTTP_404_NOT_FOUND)

        upload = await UploadsService(
            self.session,
            storage=self.storage,
        ).validate_and_read_image(file)
        file_path = self.storage.save_bytes(upload.content, folder="looks", suffix=upload.extension)
        image = LookImage(
            look_id=look_id,
            file_path=file_path,
            original_filename=upload.original_filename,
            mime_type=upload.mime_type,
            size_bytes=upload.size_bytes,
            alt_text=alt_text,
            position=position
            if position is not None
            else await self.repository.next_image_position(look_id),
            is_primary=is_primary or not look.images,
        )

        try:
            if image.is_primary:
                await self.repository.clear_primary_images(look_id)
            self.repository.add(image)
            await self.session.commit()
            await self.session.refresh(image)
        except IntegrityError as exc:
            await self.session.rollback()
            self.storage.delete(file_path)
            raise AppError("Could not persist Look image", status.HTTP_409_CONFLICT) from exc
        except Exception:
            await self.session.rollback()
            self.storage.delete(file_path)
            raise

        return LookImageRead.model_validate(image)

    async def delete_image(self, *, look_id: int, image_id: int) -> None:
        image = await self.repository.get_image(look_id=look_id, image_id=image_id)
        if image is None:
            raise AppError("Look image not found", status.HTTP_404_NOT_FOUND)

        file_path = image.file_path
        await self.repository.delete(image)
        await self.session.commit()
        try:
            self.storage.delete(file_path)
        except OSError:
            logger.warning("Failed to delete Look image file: %s", file_path, exc_info=True)

    async def _validate_item_inputs(
        self,
        items: list[LookItemInput],
        *,
        target_status: LookStatus,
    ) -> dict[int, Product]:
        if target_status == LookStatus.ACTIVE and not any(
            item.is_default_selected for item in items
        ):
            raise AppError(
                "Active Look must have at least one default selected item",
                status.HTTP_400_BAD_REQUEST,
            )

        products_by_id: dict[int, Product] = {}
        for item in items:
            product = await self.repository.get_product_by_id(item.product_id)
            if product is None:
                raise AppError("Product not found", status.HTTP_404_NOT_FOUND)
            self._validate_component_product(product, target_status=target_status)
            products_by_id[product.id] = product
        return products_by_id

    async def _validate_look_publishable(self, look: Look) -> None:
        if look.status != LookStatus.ACTIVE:
            return

        if not any(item.is_default_selected for item in look.items):
            raise AppError(
                "Active Look must have at least one default selected item",
                status.HTTP_400_BAD_REQUEST,
            )

        for item in look.items:
            product = item.product or await self.repository.get_product_by_id(item.product_id)
            if product is None:
                raise AppError("Product not found", status.HTTP_404_NOT_FOUND)
            self._validate_component_product(product, target_status=LookStatus.ACTIVE)

    async def _synchronize_items(
        self,
        look: Look,
        items: list[LookItemInput],
        *,
        products_by_id: dict[int, Product],
    ) -> None:
        existing_items_by_product_id = {item.product_id: item for item in look.items}
        synchronized_items: list[LookItem] = []

        for item_input in sorted(items, key=lambda item: item.position):
            look_item = existing_items_by_product_id.pop(item_input.product_id, None)
            if look_item is None:
                look_item = LookItem(
                    look_id=look.id,
                    product_id=item_input.product_id,
                    product=products_by_id[item_input.product_id],
                )
            look_item.position = item_input.position
            look_item.quantity = item_input.quantity
            look_item.is_default_selected = item_input.is_default_selected
            synchronized_items.append(look_item)

        for removed_item in existing_items_by_product_id.values():
            await self.repository.delete(removed_item)

        look.items = synchronized_items

    async def _get_public_look_by_slug_or_alias(self, slug: str) -> Look | None:
        look = await self.repository.get_public_by_slug(slug)
        if look is not None:
            return look

        look_id = await self.route_aliases.resolve_entity_id(RouteAliasEntityType.LOOK, slug)
        if look_id is None:
            return None
        return await self.repository.get_public_by_id(look_id)

    async def _get_public_look_similarity_context_by_slug_or_alias(
        self,
        slug: str,
    ) -> Look | None:
        look = await self.repository.get_public_similarity_context_by_slug(slug)
        if look is not None:
            return look

        look_id = await self.route_aliases.resolve_entity_id(RouteAliasEntityType.LOOK, slug)
        if look_id is None:
            return None
        return await self.repository.get_public_similarity_context_by_id(look_id)

    def _validate_component_product(self, product: Product, *, target_status: LookStatus) -> None:
        if product.status == ProductStatus.ARCHIVED:
            raise AppError("Archived products cannot be used in Looks", status.HTTP_400_BAD_REQUEST)
        if target_status == LookStatus.ACTIVE and product.status != ProductStatus.ACTIVE:
            raise AppError(
                "Active Look can include only active products",
                status.HTTP_400_BAD_REQUEST,
            )

        colors = {
            variant.color.strip().casefold()
            for variant in product.variants
            if variant.is_active and variant.color and variant.color.strip()
        }
        if len(colors) > 1:
            raise AppError(
                "Products in a Look cannot have more than one active color",
                status.HTTP_400_BAD_REQUEST,
            )

    async def _commit_and_return_admin(
        self,
        look: Look,
        *,
        persistence_message: str,
    ) -> LookAdminRead:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(
                self._look_integrity_error_message(
                    exc,
                    fallback_message=persistence_message,
                ),
                status.HTTP_409_CONFLICT,
            ) from exc

        reloaded = await self.repository.get_admin_by_id(look.id)
        if reloaded is None:
            raise AppError("Look not found", status.HTTP_404_NOT_FOUND)
        return LookAdminRead.model_validate(reloaded)

    async def _ensure_slug_available(self, slug: str, *, entity_id: int | None = None) -> None:
        existing = await self.repository.get_by_slug(slug)
        if existing is not None and existing.id != entity_id:
            raise AppError(LOOK_SLUG_CONFLICT_MESSAGE, status.HTTP_409_CONFLICT)
        await self.route_aliases.ensure_slug_available(
            RouteAliasEntityType.LOOK,
            slug,
            entity_id=entity_id,
            conflict_message=LOOK_ALIAS_CONFLICT_MESSAGE,
        )

    @staticmethod
    def _look_integrity_error_message(
        exc: IntegrityError,
        *,
        fallback_message: str,
    ) -> str:
        constraint_name = LooksService._integrity_constraint_name(exc)
        if constraint_name == LOOK_SLUG_CONSTRAINT:
            return LOOK_SLUG_CONFLICT_MESSAGE
        if constraint_name == LOOK_ALIAS_CONSTRAINT:
            return LOOK_ALIAS_CONFLICT_MESSAGE
        if constraint_name == LOOK_PRODUCT_CONSTRAINT:
            return LOOK_PRODUCT_CONFLICT_MESSAGE

        # SQLite and some wrapped async drivers do not expose structured constraint metadata.
        # Inspect only the sanitized driver message; never include it in the API response.
        driver_text = str(exc.orig).lower()
        if (
            LOOK_SLUG_CONSTRAINT in driver_text
            or "unique constraint failed: looks.slug" in driver_text
        ):
            return LOOK_SLUG_CONFLICT_MESSAGE
        if LOOK_ALIAS_CONSTRAINT in driver_text or (
            "unique constraint failed:" in driver_text
            and "route_aliases.entity_type" in driver_text
            and "route_aliases.alias_slug" in driver_text
        ):
            return LOOK_ALIAS_CONFLICT_MESSAGE
        if LOOK_PRODUCT_CONSTRAINT in driver_text or (
            "unique constraint failed:" in driver_text
            and "look_items.look_id" in driver_text
            and "look_items.product_id" in driver_text
        ):
            return LOOK_PRODUCT_CONFLICT_MESSAGE
        return fallback_message

    @staticmethod
    def _integrity_constraint_name(exc: IntegrityError) -> str | None:
        current: BaseException | None = exc.orig
        seen: set[int] = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            constraint_name = getattr(current, "constraint_name", None)
            if isinstance(constraint_name, str):
                return constraint_name
            diagnostic = getattr(current, "diag", None)
            diagnostic_name = getattr(diagnostic, "constraint_name", None)
            if isinstance(diagnostic_name, str):
                return diagnostic_name
            current = current.__cause__ or current.__context__
        return None

    async def _get_or_create_cart_for_mutation(self, user_id: int) -> Cart:
        cart = await self.cart_repository.get_by_user_id(user_id)
        if cart is not None:
            return cart

        cart = Cart(user_id=user_id)
        self.cart_repository.add(cart)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("Cart already exists", status.HTTP_409_CONFLICT) from exc
        return cart

    def _resolve_variant_for_cart(
        self,
        item: LookItem,
        *,
        clothing_size: str | None,
        footwear_size: str | None,
    ) -> ProductVariant:
        product = item.product
        if product.status != ProductStatus.ACTIVE:
            raise AppError("Product is not active", status.HTTP_400_BAD_REQUEST)

        size_group = self._product_size_group(product)
        if size_group == ProductSizeGroup.ONE_SIZE:
            variant = self._find_one_size_variant(product, required_quantity=item.quantity)
            if variant is None:
                raise AppError("Insufficient stock", status.HTTP_400_BAD_REQUEST)
            return variant

        requested_size = (
            clothing_size if size_group == ProductSizeGroup.CLOTHING else footwear_size
        )
        missing_message = (
            "Выберите размер одежды"
            if size_group == ProductSizeGroup.CLOTHING
            else "Выберите размер обуви"
        )
        unavailable_message = (
            "Выбранный размер одежды недоступен"
            if size_group == ProductSizeGroup.CLOTHING
            else "Выбранный размер обуви недоступен"
        )
        if not requested_size or requested_size == ONE_SIZE:
            raise AppError(missing_message, status.HTTP_400_BAD_REQUEST)

        variant = next(
            (
                variant
                for variant in product.variants
                if variant.is_active and variant.size == requested_size
            ),
            None,
        )
        if variant is None:
            raise AppError(unavailable_message, status.HTTP_400_BAD_REQUEST)
        if variant.available_quantity < item.quantity:
            raise AppError("Insufficient stock", status.HTTP_400_BAD_REQUEST)
        return variant

    def build_card(self, look: Look) -> LookCardRead:
        return self._build_card(look)

    def _build_card(self, look: Look) -> LookCardRead:
        selected_items = list(look.items)
        size_summary = self._size_summary(selected_items)
        price, old_price = self._sum_price(selected_items)
        return LookCardRead(
            id=look.id,
            slug=look.slug,
            title=look.title,
            description=look.description,
            primary_image_url=look.image_url,
            price=price,
            old_price=old_price,
            item_count=len(look.items),
            image_badge_type=look.image_badge_type or ProductImageBadgeType.NONE,
            image_badge_text=look.image_badge_text,
            image_badge_color=look.image_badge_color,
            image_badge_position=look.image_badge_position,
            default_selected_item_ids=[item.id for item in selected_items],
            is_available=size_summary.is_available,
            available_sizes=size_summary.available_sizes,
            available_clothing_sizes=size_summary.available_clothing_sizes,
            available_footwear_sizes=size_summary.available_footwear_sizes,
            requires_clothing_size=size_summary.requires_clothing_size,
            requires_footwear_size=size_summary.requires_footwear_size,
        )

    def _build_detail(self, look: Look) -> LookDetailRead:
        selected_items = list(look.items)
        size_summary = self._size_summary(selected_items)
        price, old_price = self._sum_price(selected_items)
        return LookDetailRead(
            id=look.id,
            slug=look.slug,
            title=look.title,
            description=look.description,
            image_badge_type=look.image_badge_type or ProductImageBadgeType.NONE,
            image_badge_text=look.image_badge_text,
            image_badge_color=look.image_badge_color,
            image_badge_position=look.image_badge_position,
            images=[LookImageRead.model_validate(image) for image in look.images],
            items=[self._build_public_item(item) for item in look.items],
            default_selected_item_ids=[item.id for item in selected_items],
            default_price=price,
            old_price=old_price,
            available_sizes=size_summary.available_sizes,
            available_clothing_sizes=size_summary.available_clothing_sizes,
            available_footwear_sizes=size_summary.available_footwear_sizes,
            requires_clothing_size=size_summary.requires_clothing_size,
            requires_footwear_size=size_summary.requires_footwear_size,
            is_available=size_summary.is_available,
        )

    def _build_public_item(self, item: LookItem) -> LookPublicItemRead:
        product = item.product
        size_group = self._product_size_group(product)
        available_sizes = self._available_sizes(product, required_quantity=item.quantity)
        one_size = size_group == ProductSizeGroup.ONE_SIZE
        is_available = (
            self._find_one_size_variant(product, required_quantity=item.quantity) is not None
            if one_size
            else any(size for size in available_sizes if size != ONE_SIZE)
        )
        summary = LookProductSummaryRead(
            product_id=product.id,
            product_slug=product.slug,
            name=product.name,
            brand=product.brand,
            image_url=product.image_url,
            price=product.base_price,
            old_price=product.old_price,
        )
        return LookPublicItemRead(
            look_item_id=item.id,
            product=summary,
            product_id=product.id,
            product_slug=product.slug,
            product_name=product.name,
            brand=product.brand,
            primary_image_url=product.image_url,
            price=product.base_price,
            old_price=product.old_price,
            quantity=item.quantity,
            is_default_selected=item.is_default_selected,
            size_group=size_group,
            available_sizes=available_sizes,
            one_size=one_size,
            is_available=is_available,
        )

    def _default_selected_items(self, look: Look) -> list[LookItem]:
        return [
            item
            for item in look.items
            if item.is_default_selected and item.product.status == ProductStatus.ACTIVE
        ]

    def _sum_price(self, items: list[LookItem]) -> tuple[Decimal, Decimal | None]:
        price = Decimal("0.00")
        old_price = Decimal("0.00")
        has_old_price = False
        for item in items:
            quantity = Decimal(item.quantity)
            product = item.product
            price += product.base_price * quantity
            if product.old_price is not None:
                has_old_price = True
                old_price += product.old_price * quantity
            else:
                old_price += product.base_price * quantity
        return price, old_price if has_old_price else None

    def _size_summary(self, items: list[LookItem]) -> LookSizeSummary:
        clothing_size_sets: list[set[str]] = []
        footwear_size_sets: list[set[str]] = []
        has_selected_one_size = False
        one_size_available = True
        for item in items:
            product = item.product
            size_group = self._product_size_group(product)
            if size_group == ProductSizeGroup.ONE_SIZE:
                has_selected_one_size = True
                if self._find_one_size_variant(product, required_quantity=item.quantity) is None:
                    one_size_available = False
                continue

            sizes = {
                size
                for size in self._available_sizes(product, required_quantity=item.quantity)
                if size != ONE_SIZE
            }
            if size_group == ProductSizeGroup.FOOTWEAR:
                footwear_size_sets.append(sizes)
            else:
                clothing_size_sets.append(sizes)

        clothing_sizes = (
            sorted(set.intersection(*clothing_size_sets)) if clothing_size_sets else []
        )
        footwear_sizes = (
            sorted(set.intersection(*footwear_size_sets)) if footwear_size_sets else []
        )
        requires_clothing_size = bool(clothing_size_sets)
        requires_footwear_size = bool(footwear_size_sets)
        is_available = (
            one_size_available
            and (not requires_clothing_size or bool(clothing_sizes))
            and (not requires_footwear_size or bool(footwear_sizes))
        )

        if requires_clothing_size:
            legacy_available_sizes = clothing_sizes
        elif requires_footwear_size:
            legacy_available_sizes = footwear_sizes
        elif has_selected_one_size and one_size_available:
            legacy_available_sizes = [ONE_SIZE]
        else:
            legacy_available_sizes = []

        return LookSizeSummary(
            available_sizes=legacy_available_sizes,
            available_clothing_sizes=clothing_sizes,
            available_footwear_sizes=footwear_sizes,
            requires_clothing_size=requires_clothing_size,
            requires_footwear_size=requires_footwear_size,
            is_available=is_available,
        )

    def _requested_sizes_for_cart(
        self,
        payload: LookCartAddRequest,
        *,
        size_summary: LookSizeSummary,
    ) -> tuple[str | None, str | None]:
        clothing_size = payload.clothing_size
        footwear_size = payload.footwear_size

        if payload.size is not None:
            if size_summary.requires_clothing_size and not size_summary.requires_footwear_size:
                clothing_size = clothing_size or payload.size
            elif size_summary.requires_footwear_size and not size_summary.requires_clothing_size:
                footwear_size = footwear_size or payload.size

        if size_summary.requires_clothing_size:
            if not clothing_size or clothing_size == ONE_SIZE:
                raise AppError("Выберите размер одежды", status.HTTP_400_BAD_REQUEST)
            if clothing_size not in size_summary.available_clothing_sizes:
                raise AppError(
                    "Выбранный размер одежды недоступен",
                    status.HTTP_400_BAD_REQUEST,
                )
        if size_summary.requires_footwear_size:
            if not footwear_size or footwear_size == ONE_SIZE:
                raise AppError("Выберите размер обуви", status.HTTP_400_BAD_REQUEST)
            if footwear_size not in size_summary.available_footwear_sizes:
                raise AppError(
                    "Выбранный размер обуви недоступен",
                    status.HTTP_400_BAD_REQUEST,
                )

        return clothing_size, footwear_size

    def _available_sizes(self, product: Product, *, required_quantity: int) -> list[str]:
        sizes = {
            variant.size
            for variant in product.variants
            if variant.is_active and variant.available_quantity >= required_quantity
        }
        return sorted(sizes)

    def _is_one_size_product(self, product: Product) -> bool:
        active_variants = [variant for variant in product.variants if variant.is_active]
        return bool(active_variants) and all(
            variant.size == ONE_SIZE for variant in active_variants
        )

    def _product_size_group(self, product: Product) -> ProductSizeGroup:
        raw_group = getattr(product, "size_group", None)
        if raw_group is not None:
            try:
                return ProductSizeGroup(raw_group)
            except ValueError:
                pass
        if self._is_one_size_product(product):
            return ProductSizeGroup.ONE_SIZE
        if is_footwear_size_grid(product.size_grid):
            return ProductSizeGroup.FOOTWEAR
        return ProductSizeGroup.CLOTHING

    def _find_one_size_variant(
        self,
        product: Product,
        *,
        required_quantity: int,
    ) -> ProductVariant | None:
        return next(
            (
                variant
                for variant in sorted(product.variants, key=lambda variant: variant.id)
                if variant.is_active
                and variant.size == ONE_SIZE
                and variant.available_quantity >= required_quantity
            ),
            None,
        )
