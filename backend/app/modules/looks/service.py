import logging
from decimal import Decimal
from uuid import uuid4

from fastapi import UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

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
    ProductStatus,
    ProductVariant,
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
    LookUpdate,
)
from app.modules.uploads.service import UploadsService
from app.modules.uploads.storage import LocalStorageService

ONE_SIZE = "ONE_SIZE"

logger = logging.getLogger(__name__)


class LooksService:
    def __init__(
        self,
        session: AsyncSession,
        storage: LocalStorageService | None = None,
    ) -> None:
        self.session = session
        self.repository = LooksRepository(session)
        self.cart_repository = CartRepository(session)
        self.storage = storage or LocalStorageService()

    async def list_public_looks(self, *, limit: int, offset: int) -> LookList:
        looks, total = await self.repository.list_public(limit=limit, offset=offset)
        return LookList(
            items=[self._build_card(look) for look in looks],
            meta=PageMeta(limit=limit, offset=offset, total=total),
        )

    async def get_public_look(self, slug: str) -> LookDetailRead:
        look = await self.repository.get_public_by_slug(slug)
        if look is None:
            raise AppError("Look not found", status.HTTP_404_NOT_FOUND)
        return self._build_detail(look)

    async def add_look_to_cart(
        self,
        *,
        slug: str,
        user_id: int,
        payload: LookCartAddRequest,
    ) -> LookCartAddResponse:
        look = await self.repository.get_public_by_slug(slug)
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

        resolved_items = [
            (item, self._resolve_variant_for_cart(item, requested_size=payload.size))
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

    async def create_admin_look(self, payload: LookCreate) -> LookAdminRead:
        existing = await self.repository.get_by_slug(payload.slug)
        if existing is not None:
            raise AppError("Look slug already exists", status.HTTP_409_CONFLICT)

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
        return await self._commit_and_return_admin(
            look,
            duplicate_message="Look slug already exists",
        )

    async def update_admin_look(self, look_id: int, payload: LookUpdate) -> LookAdminRead:
        look = await self.repository.get_admin_by_id(look_id)
        if look is None:
            raise AppError("Look not found", status.HTTP_404_NOT_FOUND)

        if payload.slug is not None and payload.slug != look.slug:
            existing = await self.repository.get_by_slug(payload.slug)
            if existing is not None and existing.id != look.id:
                raise AppError("Look slug already exists", status.HTTP_409_CONFLICT)
            look.slug = payload.slug

        if payload.title is not None:
            look.title = payload.title
        if "description" in payload.model_fields_set:
            look.description = payload.description
        if payload.is_listed is not None:
            look.is_listed = payload.is_listed
        if payload.search_priority is not None:
            look.search_priority = payload.search_priority
        if payload.status is not None:
            look.status = payload.status

        if payload.items is not None:
            products_by_id = await self._validate_item_inputs(
                payload.items,
                target_status=look.status,
            )
            look.items = [
                LookItem(
                    product_id=item.product_id,
                    product=products_by_id[item.product_id],
                    position=item.position,
                    quantity=item.quantity,
                    is_default_selected=item.is_default_selected,
                )
                for item in payload.items
            ]

        await self._validate_look_publishable(look)
        return await self._commit_and_return_admin(
            look,
            duplicate_message="Look slug already exists",
        )

    async def archive_admin_look(self, look_id: int) -> LookAdminRead:
        look = await self.repository.get_admin_by_id(look_id)
        if look is None:
            raise AppError("Look not found", status.HTTP_404_NOT_FOUND)
        look.status = LookStatus.ARCHIVED
        return await self._commit_and_return_admin(look, duplicate_message="Could not archive Look")

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
        duplicate_message: str,
    ) -> LookAdminRead:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(duplicate_message, status.HTTP_409_CONFLICT) from exc

        reloaded = await self.repository.get_admin_by_id(look.id)
        if reloaded is None:
            raise AppError("Look not found", status.HTTP_404_NOT_FOUND)
        return LookAdminRead.model_validate(reloaded)

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
        requested_size: str | None,
    ) -> ProductVariant:
        product = item.product
        if product.status != ProductStatus.ACTIVE:
            raise AppError("Product is not active", status.HTTP_400_BAD_REQUEST)

        if self._is_one_size_product(product):
            variant = self._find_one_size_variant(product, required_quantity=item.quantity)
            if variant is None:
                raise AppError("Insufficient stock", status.HTTP_400_BAD_REQUEST)
            return variant

        if not requested_size or requested_size == ONE_SIZE:
            raise AppError("Size is required for selected Look items", status.HTTP_400_BAD_REQUEST)

        variant = next(
            (
                variant
                for variant in product.variants
                if variant.is_active and variant.size == requested_size
            ),
            None,
        )
        if variant is None:
            raise AppError("Product size is unavailable", status.HTTP_400_BAD_REQUEST)
        if variant.available_quantity < item.quantity:
            raise AppError("Insufficient stock", status.HTTP_400_BAD_REQUEST)
        return variant

    def _build_card(self, look: Look) -> LookCardRead:
        selected_items = self._default_selected_items(look)
        available_sizes = self._common_sizes(selected_items)
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
            is_available=bool(available_sizes),
            available_sizes=available_sizes,
        )

    def _build_detail(self, look: Look) -> LookDetailRead:
        selected_items = self._default_selected_items(look)
        available_sizes = self._common_sizes(selected_items)
        price, old_price = self._sum_price(selected_items)
        return LookDetailRead(
            id=look.id,
            slug=look.slug,
            title=look.title,
            description=look.description,
            images=[LookImageRead.model_validate(image) for image in look.images],
            items=[self._build_public_item(item) for item in look.items],
            default_selected_item_ids=[item.id for item in selected_items],
            default_price=price,
            old_price=old_price,
            available_sizes=available_sizes,
            is_available=bool(available_sizes),
        )

    def _build_public_item(self, item: LookItem) -> LookPublicItemRead:
        product = item.product
        available_sizes = self._available_sizes(product, required_quantity=item.quantity)
        one_size = self._is_one_size_product(product)
        is_available = bool(available_sizes)
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

    def _common_sizes(self, items: list[LookItem]) -> list[str]:
        clothing_size_sets: list[set[str]] = []
        has_selected_one_size = False
        for item in items:
            product = item.product
            if self._is_one_size_product(product):
                has_selected_one_size = True
                if self._find_one_size_variant(product, required_quantity=item.quantity) is None:
                    return []
                continue

            sizes = {
                size
                for size in self._available_sizes(product, required_quantity=item.quantity)
                if size != ONE_SIZE
            }
            if not sizes:
                return []
            clothing_size_sets.append(sizes)

        if clothing_size_sets:
            common = set.intersection(*clothing_size_sets)
            return sorted(common)
        if has_selected_one_size:
            return [ONE_SIZE]
        return []

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
