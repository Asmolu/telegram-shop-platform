import logging
from decimal import Decimal

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import Cart, CartItem, Product, ProductStatus, ProductVariant
from app.modules.analytics.service import AnalyticsTracker
from app.modules.cart.repository import CartRepository
from app.modules.cart.schemas import (
    CartItemCreate,
    CartItemRead,
    CartItemSelectionUpdate,
    CartItemUpdate,
    CartProductRead,
    CartProductVariantRead,
    CartRead,
    CartSelectionUpdate,
)
from app.modules.products.inventory import calculate_available_quantity

logger = logging.getLogger(__name__)


class CartService:
    def __init__(
        self,
        session: AsyncSession,
        analytics_tracker: AnalyticsTracker | None = None,
    ) -> None:
        self.session = session
        self.repository = CartRepository(session)
        self.analytics_tracker = analytics_tracker

    async def get_current_user_cart(self, user_id: int) -> CartRead:
        cart = await self._get_or_create_cart(user_id)
        return self._build_cart_response(cart)

    async def add_item(self, user_id: int, payload: CartItemCreate) -> CartRead:
        cart = await self._get_or_create_cart(user_id)
        product, variant = await self._validate_product_variant(
            product_id=payload.product_id,
            product_variant_id=payload.product_variant_id,
        )

        existing_item = await self.repository.get_item_by_cart_and_variant(
            cart_id=cart.id,
            product_variant_id=variant.id,
        )
        quantity = payload.quantity
        if existing_item is not None:
            quantity += existing_item.quantity

        total_variant_quantity = self._cart_variant_quantity(cart, variant.id) + payload.quantity
        self._validate_quantity(total_variant_quantity, variant)

        if existing_item is None:
            self.repository.add(
                CartItem(
                    cart_id=cart.id,
                    product_id=product.id,
                    product_variant_id=variant.id,
                    quantity=quantity,
                    is_selected=True,
                )
            )
        else:
            existing_item.quantity = quantity
            existing_item.is_selected = True

        cart_response = await self._commit_and_reload(user_id)
        await self._track_event(
            "cart.item_added",
            user_id=user_id,
            product_id=product.id,
            metadata={
                "product_variant_id": variant.id,
                "quantity": payload.quantity,
                "cart_id": cart.id,
            },
        )
        return cart_response

    async def update_item_quantity(
        self,
        user_id: int,
        item_id: int,
        payload: CartItemUpdate,
    ) -> CartRead:
        item = await self.repository.get_item_for_user(user_id=user_id, item_id=item_id)
        if item is None:
            raise AppError("Cart item not found", status.HTTP_404_NOT_FOUND)

        await self._validate_product_variant(
            product_id=item.product_id,
            product_variant_id=item.product_variant_id,
        )
        cart = await self.repository.get_by_user_id(user_id)
        if cart is None:
            raise AppError("Cart not found", status.HTTP_404_NOT_FOUND)
        total_variant_quantity = self._cart_variant_quantity(
            cart,
            item.product_variant_id,
            exclude_item_id=item.id,
        ) + payload.quantity
        self._validate_quantity(total_variant_quantity, item.product_variant)
        item.quantity = payload.quantity

        return await self._commit_and_reload(user_id)

    async def update_item_selection(
        self,
        user_id: int,
        item_id: int,
        payload: CartItemSelectionUpdate,
    ) -> CartRead:
        item = await self.repository.get_item_for_user(user_id=user_id, item_id=item_id)
        if item is None:
            raise AppError("Cart item not found", status.HTTP_404_NOT_FOUND)

        item.is_selected = payload.is_selected
        return await self._commit_and_reload(user_id)

    async def update_selection(
        self,
        user_id: int,
        payload: CartSelectionUpdate,
    ) -> CartRead:
        cart = await self._get_or_create_cart(user_id)
        items = cart.items
        if payload.item_ids is not None:
            requested_ids = set(payload.item_ids)
            items = [item for item in cart.items if item.id in requested_ids]
            if len(items) != len(requested_ids):
                raise AppError("Cart item not found", status.HTTP_404_NOT_FOUND)

        for item in items:
            item.is_selected = payload.is_selected

        return await self._commit_and_reload(user_id)

    async def remove_item(self, user_id: int, item_id: int) -> CartRead:
        item = await self.repository.get_item_for_user(user_id=user_id, item_id=item_id)
        if item is None:
            raise AppError("Cart item not found", status.HTTP_404_NOT_FOUND)

        await self.repository.delete_item(item)
        return await self._commit_and_reload(user_id)

    async def clear_cart(self, user_id: int) -> CartRead:
        cart = await self._get_or_create_cart(user_id)
        await self.repository.clear_cart(cart.id)
        return await self._commit_and_reload(user_id)

    async def _get_or_create_cart(self, user_id: int) -> Cart:
        cart = await self.repository.get_by_user_id(user_id)
        if cart is not None:
            return cart

        cart = Cart(user_id=user_id)
        self.repository.add(cart)
        try:
            await self.session.flush()
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("Cart already exists", status.HTTP_409_CONFLICT) from exc

        cart = await self.repository.get_by_user_id(user_id)
        if cart is None:
            raise AppError("Cart not found", status.HTTP_404_NOT_FOUND)
        return cart

    async def _validate_product_variant(
        self,
        *,
        product_id: int,
        product_variant_id: int,
    ) -> tuple[Product, ProductVariant]:
        product = await self.repository.get_product_by_id(product_id)
        if product is None:
            raise AppError("Product not found", status.HTTP_404_NOT_FOUND)
        if product.status != ProductStatus.ACTIVE:
            raise AppError("Product is not active", status.HTTP_400_BAD_REQUEST)

        variant = await self.repository.get_product_variant_by_id(product_variant_id)
        if variant is None:
            raise AppError("Product variant not found", status.HTTP_404_NOT_FOUND)
        if variant.product_id != product.id:
            raise AppError(
                "Product variant does not belong to selected product",
                status.HTTP_400_BAD_REQUEST,
            )
        if not variant.is_active:
            raise AppError("Product variant is not active", status.HTTP_400_BAD_REQUEST)

        return product, variant

    def _validate_quantity(self, quantity: int, variant: ProductVariant) -> None:
        if quantity <= 0:
            raise AppError("Quantity must be positive", status.HTTP_400_BAD_REQUEST)
        available_quantity = calculate_available_quantity(
            variant.stock_quantity,
            variant.reserved_quantity,
        )
        if quantity > available_quantity:
            raise AppError("Insufficient stock", status.HTTP_400_BAD_REQUEST)

    def _cart_variant_quantity(
        self,
        cart: Cart,
        product_variant_id: int,
        *,
        exclude_item_id: int | None = None,
    ) -> int:
        return sum(
            item.quantity
            for item in cart.items
            if item.product_variant_id == product_variant_id and item.id != exclude_item_id
        )

    async def _commit_and_reload(self, user_id: int) -> CartRead:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("Cart item already exists", status.HTTP_409_CONFLICT) from exc

        cart = await self.repository.get_by_user_id(user_id)
        if cart is None:
            raise AppError("Cart not found", status.HTTP_404_NOT_FOUND)
        return self._build_cart_response(cart)

    def _build_cart_response(self, cart: Cart) -> CartRead:
        items = [self._build_item_response(item) for item in cart.items]
        total = sum((item.subtotal for item in items), Decimal("0.00"))
        quantity_total = sum(item.quantity for item in items)
        selected_items = [item for item in items if item.is_selected]
        selected_total = sum((item.subtotal for item in selected_items), Decimal("0.00"))
        selected_quantity_total = sum(item.quantity for item in selected_items)
        return CartRead(
            id=cart.id,
            user_id=cart.user_id,
            items=items,
            total=total,
            quantity_total=quantity_total,
            distinct_item_count=len(items),
            selected_total=selected_total,
            selected_quantity_total=selected_quantity_total,
            selected_distinct_item_count=len(selected_items),
            created_at=cart.created_at,
            updated_at=cart.updated_at,
        )

    def _build_item_response(self, item: CartItem) -> CartItemRead:
        unit_price = item.product.base_price
        subtotal = unit_price * item.quantity
        return CartItemRead(
            id=item.id,
            product=CartProductRead.model_validate(item.product),
            product_variant=CartProductVariantRead.model_validate(item.product_variant),
            quantity=item.quantity,
            is_selected=item.is_selected,
            unit_price=unit_price,
            subtotal=subtotal,
            source_type=item.source_type,
            source_group_id=item.source_group_id,
            source_look_id=item.source_look_id,
            source_look_slug=item.source_look_slug,
            source_look_title=item.source_look_title,
            source_look_image_url=item.source_look_image_url,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    async def _track_event(
        self,
        event_name: str,
        *,
        user_id: int,
        product_id: int | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        if self.analytics_tracker is None:
            return
        try:
            await self.analytics_tracker.track(
                event_name,
                user_id=user_id,
                product_id=product_id,
                metadata=metadata,
            )
        except Exception:
            logger.warning("Failed to track cart analytics event %s", event_name, exc_info=True)
