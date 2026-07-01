import logging
from collections.abc import Mapping
from datetime import UTC, datetime
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
    ManualPaymentStatus,
    Order,
    OrderItem,
    OrderStatus,
    ProductStatus,
    ProductVariant,
)
from app.events.names import ORDER_CREATED, ORDER_SHIPPED, ORDER_STATUS_CHANGED, PROMO_USED
from app.events.payloads import (
    order_created_payload,
    order_shipped_payload,
    order_status_changed_payload,
    promo_used_payload,
)
from app.modules.analytics.service import AnalyticsTracker
from app.modules.audit.service import AuditService, NoopAuditService
from app.modules.customer_notifications.service import CustomerServiceNotificationEventPublisher
from app.modules.idempotency.service import IdempotencyClaim, IdempotencyService
from app.modules.manual_payments.service import ManualPaymentsService
from app.modules.notifications.service import NotificationsEventPublisher
from app.modules.orders.repository import OrdersRepository
from app.modules.orders.schemas import OrderCheckoutCreate, OrderList, OrderRead, OrderStatusUpdate
from app.modules.promo_codes.service import PromoCodeCalculation, PromoCodesService

logger = logging.getLogger(__name__)


class OrderEventPublisher(Protocol):
    async def emit(self, name: str, payload: Mapping[str, object]) -> None:
        """Emit an internal post-commit order event."""


class InternalOrderEventPublisher:
    """Post-commit notification event publisher."""

    def __init__(
        self,
        session: AsyncSession,
        notifications_publisher: OrderEventPublisher | None = None,
        customer_notifications_publisher: OrderEventPublisher | None = None,
    ) -> None:
        self.session = session
        self.notifications_publisher = notifications_publisher or NotificationsEventPublisher(
            session
        )
        self.customer_notifications_publisher = (
            customer_notifications_publisher or CustomerServiceNotificationEventPublisher(session)
        )

    async def emit(self, name: str, payload: Mapping[str, object]) -> None:
        for publisher_name, publisher in (
            ("seller", self.notifications_publisher),
            ("customer", self.customer_notifications_publisher),
        ):
            try:
                await publisher.emit(name, payload)
            except Exception:
                logger.warning(
                    "Failed to process %s post-commit order event %s",
                    publisher_name,
                    name,
                    exc_info=True,
                )
                await self._rollback_failed_publisher(publisher_name, name)

    async def _rollback_failed_publisher(self, publisher_name: str, event_name: str) -> None:
        try:
            await self.session.rollback()
        except Exception:
            logger.warning(
                "Failed to reset session after %s post-commit order event %s",
                publisher_name,
                event_name,
                exc_info=True,
            )


class OrdersService:
    """Order checkout and order management endpoints."""

    def __init__(
        self,
        session: AsyncSession,
        event_publisher: OrderEventPublisher | None = None,
        promo_codes_service: PromoCodesService | None = None,
        analytics_tracker: AnalyticsTracker | None = None,
        audit_service: AuditService | None = None,
        manual_payments_service: ManualPaymentsService | None = None,
        idempotency_service: IdempotencyService | None = None,
    ) -> None:
        self.session = session
        self.repository = OrdersRepository(session)
        self.event_publisher = event_publisher or InternalOrderEventPublisher(session)
        self.promo_codes_service = promo_codes_service or PromoCodesService(session)
        self.analytics_tracker = analytics_tracker
        self.audit_service = audit_service or NoopAuditService()
        self.manual_payments_service = manual_payments_service or ManualPaymentsService(session)
        self.idempotency_service = idempotency_service or IdempotencyService(session)

    async def checkout_current_user_cart(
        self,
        user_id: int,
        payload: OrderCheckoutCreate,
        *,
        idempotency_key: str | None = None,
    ) -> OrderRead:
        post_commit_events: list[tuple[str, dict[str, object]]] = []
        post_commit_analytics: list[tuple[str, dict[str, object]]] = []
        idempotency_claim: IdempotencyClaim | None = None
        try:
            if idempotency_key:
                idempotency_claim = await self.idempotency_service.begin(
                    user_id=user_id,
                    scope="orders.checkout",
                    key=idempotency_key,
                    request_hash=IdempotencyService.hash_payload(
                        payload.model_dump(mode="json", by_alias=True)
                    ),
                )
                if idempotency_claim.replay_response is not None:
                    return OrderRead.model_validate(idempotency_claim.replay_response)

            cart = await self.repository.get_cart_for_checkout(user_id)
            self._validate_cart_not_empty(cart)
            assert cart is not None
            checkout_items = self._selected_cart_items(cart)
            payment_settings = await self.manual_payments_service.require_checkout_settings()

            variants_by_id = await self.repository.lock_variants_by_ids(
                item.product_variant_id for item in checkout_items
            )
            self._validate_checkout_items(checkout_items, variants_by_id)

            subtotal = self._calculate_subtotal(checkout_items)
            promo_calculation = await self._validate_promo_code(
                user_id=user_id,
                code=payload.promo_code,
                subtotal=subtotal,
            )
            order = self._build_order(
                user_id=user_id,
                payload=payload,
                subtotal=subtotal,
                promo_calculation=promo_calculation,
            )
            self.repository.add(order)
            await self.session.flush()
            await self.manual_payments_service.create_for_checkout(
                order,
                payment_settings=payment_settings,
            )

            if promo_calculation is not None:
                self.promo_codes_service.record_usage_for_checkout(
                    promo_code_id=promo_calculation.promo_code.id,
                    user_id=user_id,
                    order_id=order.id,
                )

            for item in checkout_items:
                variant = variants_by_id[item.product_variant_id]
                subtotal = item.product.base_price * item.quantity
                is_returnable = item.product.is_returnable
                variant.stock_quantity -= item.quantity
                self.repository.add(
                    OrderItem(
                        order_id=order.id,
                        product_id=item.product_id,
                        product_variant_id=item.product_variant_id,
                        product=item.product,
                        product_variant=variant,
                        product_name=item.product.name,
                        variant_size=variant.size,
                        variant_size_grid=item.product.size_grid,
                        variant_color=variant.color,
                        variant_sku=variant.sku,
                        unit_price=item.product.base_price,
                        quantity=item.quantity,
                        subtotal=subtotal,
                        is_returnable=is_returnable if is_returnable is not None else True,
                    )
                )

            await self.repository.clear_cart_items(cart.id, (item.id for item in checkout_items))
            await self.session.flush()

            created_order = await self.repository.get_by_id(order.id)
            if created_order is None:
                raise AppError("Order not found", status.HTTP_404_NOT_FOUND)
            response = OrderRead.model_validate(created_order)
            post_commit_events.append((ORDER_CREATED, order_created_payload(created_order)))
            post_commit_analytics.append(
                (
                    "checkout.started",
                    {
                        "user_id": user_id,
                        "order_id": created_order.id,
                        "promo_code_id": created_order.promo_code_id,
                    },
                )
            )
            post_commit_analytics.append(
                (
                    "order.created",
                    {
                        "user_id": user_id,
                        "order_id": created_order.id,
                        "promo_code_id": created_order.promo_code_id,
                        "total_amount": str(created_order.total_amount),
                    },
                )
            )
            if created_order.promo_code_id is not None:
                post_commit_events.append((PROMO_USED, promo_used_payload(created_order)))
                post_commit_analytics.append(
                    (
                        "promo.used",
                        {
                            "user_id": user_id,
                            "order_id": created_order.id,
                            "promo_code_id": created_order.promo_code_id,
                            "promo_code": created_order.promo_code_code,
                        },
                    )
                )
            self.idempotency_service.complete(
                idempotency_claim,
                response_body=response.model_dump(mode="json"),
                response_status_code=status.HTTP_201_CREATED,
            )
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

        for event_name, event_payload in post_commit_events:
            await self._emit_post_commit_event(event_name, event_payload)
        for event_name, event_payload in post_commit_analytics:
            await self._track_event(
                event_name,
                user_id=int(event_payload["user_id"]),
                order_id=int(event_payload["order_id"]),
                promo_code_id=event_payload.get("promo_code_id"),
                metadata=event_payload,
            )
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

    async def list_orders(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        status: OrderStatus | None = None,
        user_id: int | None = None,
        search: str | None = None,
    ) -> OrderList:
        orders = await self.repository.list_all(
            limit=limit,
            offset=offset,
            status=status,
            user_id=user_id,
            search=search,
        )
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
        actor_user_id: int | None = None,
    ) -> OrderRead:
        order = await self.repository.get_by_id(order_id)
        if order is None:
            raise AppError("Order not found", status.HTTP_404_NOT_FOUND)

        previous_status = order.status
        if (
            order.manual_payment is not None
            and order.manual_payment.status
            in {ManualPaymentStatus.PENDING, ManualPaymentStatus.SUBMITTED}
            and payload.status != previous_status
        ):
            raise AppError(
                "Use the manual payment approve or reject action for this order",
                status.HTTP_409_CONFLICT,
            )
        before_data = self.audit_service.snapshot(order, ("status", "delivered_at"))
        order.status = payload.status
        if order.status == OrderStatus.DELIVERED and order.delivered_at is None:
            order.delivered_at = datetime.now(UTC)
        post_commit_events: list[tuple[str, dict[str, object]]] = []
        if previous_status != order.status:
            await self.audit_service.record_action(
                actor_user_id=actor_user_id,
                action="order.status_changed",
                entity_type="order",
                entity_id=order.id,
                before_data=before_data,
                after_data=self.audit_service.snapshot(order, ("status", "delivered_at")),
            )
            post_commit_events.append(
                (
                    ORDER_STATUS_CHANGED,
                    order_status_changed_payload(order, previous_status=previous_status),
                )
            )
            if order.status == OrderStatus.SHIPPED:
                post_commit_events.append((ORDER_SHIPPED, order_shipped_payload(order)))

        response = OrderRead.model_validate(order)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("Order update failed", status.HTTP_409_CONFLICT) from exc

        for event_name, event_payload in post_commit_events:
            await self._emit_post_commit_event(event_name, event_payload)

        return response

    async def _emit_post_commit_event(
        self,
        event_name: str,
        event_payload: Mapping[str, object],
    ) -> None:
        try:
            await self.event_publisher.emit(event_name, event_payload)
        except Exception:
            logger.warning(
                "Failed to process post-commit order event %s",
                event_name,
                exc_info=True,
            )
            try:
                await self.session.rollback()
            except Exception:
                logger.warning(
                    "Failed to reset session after post-commit order event %s",
                    event_name,
                    exc_info=True,
                )

    async def _track_event(
        self,
        event_name: str,
        *,
        user_id: int,
        order_id: int,
        promo_code_id: object | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        if self.analytics_tracker is None:
            return
        try:
            await self.analytics_tracker.track(
                event_name,
                user_id=user_id,
                order_id=order_id,
                promo_code_id=promo_code_id if isinstance(promo_code_id, int) else None,
                metadata=metadata,
            )
        except Exception:
            logger.warning("Failed to track order analytics event %s", event_name, exc_info=True)

    def _validate_cart_not_empty(self, cart: Cart | None) -> None:
        if cart is None or not cart.items:
            raise AppError("Cart is empty", status.HTTP_400_BAD_REQUEST)

    def _selected_cart_items(self, cart: Cart) -> list[CartItem]:
        items = [item for item in cart.items if item.is_selected]
        if not items:
            raise AppError("No selected cart items", status.HTTP_400_BAD_REQUEST)
        return items

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
        subtotal: Decimal,
        promo_calculation: PromoCodeCalculation | None,
    ) -> Order:
        discount = Decimal("0.00")
        total = subtotal
        promo_code_id = None
        promo_code_code = None
        if promo_calculation is not None:
            discount = promo_calculation.discount_amount
            total = promo_calculation.total_amount
            promo_code_id = promo_calculation.promo_code.id
            promo_code_code = promo_calculation.promo_code.code

        return Order(
            order_number=self._generate_order_number(),
            user_id=user_id,
            status=OrderStatus.NEW,
            subtotal_amount=subtotal,
            discount_amount=discount,
            promo_code_id=promo_code_id,
            promo_code_code=promo_code_code,
            total_amount=total,
            contact_name=payload.contact_name,
            contact_phone=payload.contact_phone,
            delivery_method=payload.delivery_method,
            delivery_address=payload.delivery_address,
            delivery_comment=payload.delivery_comment,
        )

    async def _validate_promo_code(
        self,
        *,
        user_id: int,
        code: str | None,
        subtotal: Decimal,
    ) -> PromoCodeCalculation | None:
        if code is None:
            return None
        normalized_code = code.strip().upper()
        if not normalized_code:
            raise AppError("Promo code not found", status.HTTP_404_NOT_FOUND)
        return await self.promo_codes_service.validate_for_checkout(
            user_id=user_id,
            code=normalized_code,
            subtotal_amount=subtotal,
            for_update=True,
        )

    def _calculate_subtotal(self, items: list[CartItem]) -> Decimal:
        return sum(
            (item.product.base_price * item.quantity for item in items),
            Decimal("0.00"),
        )

    def _generate_order_number(self) -> str:
        return f"ORD-{token_hex(6).upper()}"
