from collections.abc import Mapping
from decimal import Decimal
from secrets import token_hex
from typing import Protocol

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import (
    Cart,
    CartItem,
    Order,
    OrderItem,
    OrderStatus,
    ProductStatus,
    ProductVariant,
)
from app.events.names import ORDER_CREATED
from app.modules.orders.repository import OrdersRepository
from app.modules.orders.schemas import OrderCheckoutCreate, OrderList, OrderRead, OrderStatusUpdate


class OrderEventPublisher(Protocol):
    async def emit(self, name: str, payload: Mapping[str, object]) -> None:
        """Emit an internal post-commit order event."""


class InternalOrderEventPublisher:
    """No-op event placeholder for the future notification pipeline."""

    async def emit(self, name: str, payload: Mapping[str, object]) -> None:
        del name, payload


class OrdersService:
    """Order checkout and order management endpoints."""

    def __init__(
        self,
        session: AsyncSession,
        event_publisher: OrderEventPublisher | None = None,
    ) -> None:
        self.session = session
        self.repository = OrdersRepository(session)
        self.event_publisher = event_publisher or InternalOrderEventPublisher()

    async def checkout_current_user_cart(
        self,
        user_id: int,
        payload: OrderCheckoutCreate,
    ) -> OrderRead:
        event_payload: dict[str, object] | None = None
        try:
            cart = await self.repository.get_cart_for_checkout(user_id)
            self._validate_cart_not_empty(cart)
            assert cart is not None

            variants_by_id = await self.repository.lock_variants_by_ids(
                item.product_variant_id for item in cart.items
            )
            self._validate_checkout_items(cart.items, variants_by_id)

            order = self._build_order(user_id=user_id, payload=payload, items=cart.items)
            self.repository.add(order)
            await self.session.flush()

            for item in cart.items:
                variant = variants_by_id[item.product_variant_id]
                subtotal = item.product.base_price * item.quantity
                variant.stock_quantity -= item.quantity
                self.repository.add(
                    OrderItem(
                        order_id=order.id,
                        product_id=item.product_id,
                        product_variant_id=item.product_variant_id,
                        product_name=item.product.name,
                        variant_size=variant.size,
                        variant_sku=variant.sku,
                        unit_price=item.product.base_price,
                        quantity=item.quantity,
                        subtotal=subtotal,
                    )
                )

            await self.repository.clear_cart(cart.id)
            await self.session.flush()

            created_order = await self.repository.get_by_id(order.id)
            if created_order is None:
                raise AppError("Order not found", status.HTTP_404_NOT_FOUND)
            response = OrderRead.model_validate(created_order)
            event_payload = {"order_id": created_order.id, "user_id": user_id}
            await self.session.commit()
        except AppError:
            await self.session.rollback()
            raise
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("Order checkout failed", status.HTTP_409_CONFLICT) from exc
        except Exception:
            await self.session.rollback()
            raise

        await self.event_publisher.emit(ORDER_CREATED, event_payload)
        return response

    async def list_current_user_orders(
        self,
        user_id: int,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> OrderList:
        orders = await self.repository.list_for_user(user_id=user_id, limit=limit, offset=offset)
        return OrderList(items=[OrderRead.model_validate(order) for order in orders])

    async def get_current_user_order(self, user_id: int, order_id: int) -> OrderRead:
        order = await self.repository.get_for_user(user_id=user_id, order_id=order_id)
        if order is None:
            raise AppError("Order not found", status.HTTP_404_NOT_FOUND)
        return OrderRead.model_validate(order)

    async def list_orders(self, *, limit: int = 20, offset: int = 0) -> OrderList:
        orders = await self.repository.list_all(limit=limit, offset=offset)
        return OrderList(items=[OrderRead.model_validate(order) for order in orders])

    async def get_order(self, order_id: int) -> OrderRead:
        order = await self.repository.get_by_id(order_id)
        if order is None:
            raise AppError("Order not found", status.HTTP_404_NOT_FOUND)
        return OrderRead.model_validate(order)

    async def update_order_status(
        self,
        order_id: int,
        payload: OrderStatusUpdate,
    ) -> OrderRead:
        order = await self.repository.get_by_id(order_id)
        if order is None:
            raise AppError("Order not found", status.HTTP_404_NOT_FOUND)

        order.status = payload.status
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("Order update failed", status.HTTP_409_CONFLICT) from exc

        return OrderRead.model_validate(order)

    def _validate_cart_not_empty(self, cart: Cart | None) -> None:
        if cart is None or not cart.items:
            raise AppError("Cart is empty", status.HTTP_400_BAD_REQUEST)

    def _validate_checkout_items(
        self,
        items: list[CartItem],
        variants_by_id: Mapping[int, ProductVariant],
    ) -> None:
        for item in items:
            product = item.product
            if product.status != ProductStatus.ACTIVE:
                raise AppError("Product is not active", status.HTTP_400_BAD_REQUEST)

            variant = variants_by_id.get(item.product_variant_id)
            if variant is None:
                raise AppError("Product variant not found", status.HTTP_404_NOT_FOUND)
            if not variant.is_active:
                raise AppError("Product variant is not active", status.HTTP_400_BAD_REQUEST)
            if item.quantity > variant.available_quantity:
                raise AppError("Insufficient stock", status.HTTP_400_BAD_REQUEST)

    def _build_order(
        self,
        *,
        user_id: int,
        payload: OrderCheckoutCreate,
        items: list[CartItem],
    ) -> Order:
        subtotal = sum(
            (item.product.base_price * item.quantity for item in items),
            Decimal("0.00"),
        )
        discount = Decimal("0.00")
        return Order(
            order_number=self._generate_order_number(),
            user_id=user_id,
            status=OrderStatus.NEW,
            subtotal_amount=subtotal,
            discount_amount=discount,
            total_amount=subtotal - discount,
            contact_name=payload.contact_name,
            contact_phone=payload.contact_phone,
            delivery_address=payload.delivery_address,
            delivery_comment=payload.delivery_comment,
        )

    def _generate_order_number(self) -> str:
        return f"ORD-{token_hex(6).upper()}"
