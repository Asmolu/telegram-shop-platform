import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.common.deps import get_current_user
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import (
    Cart,
    CartItem,
    CouponUsage,
    DiscountType,
    ManualPayment,
    ManualPaymentCurrency,
    ManualPaymentMethod,
    ManualPaymentStatus,
    Notification,
    NotificationStatus,
    Order,
    OrderDeliveryMethod,
    OrderItem,
    OrderStatus,
    Product,
    ProductImage,
    ProductSizeGrid,
    ProductSizeGroup,
    ProductStatus,
    ProductVariant,
    PromoCode,
    SellerPaymentSettings,
    User,
    UserRole,
)
from app.events.names import ORDER_CREATED, ORDER_SHIPPED, ORDER_STATUS_CHANGED, PROMO_USED
from app.main import create_app
from app.modules.notifications.service import NotificationsEventPublisher, NotificationsService
from app.modules.orders.numbering import ORDER_NUMBER_MAX, format_order_number
from app.modules.orders.router import get_orders_service
from app.modules.orders.schemas import OrderCheckoutCreate, OrderItemRead, OrderStatusUpdate
from app.modules.orders.service import InternalOrderEventPublisher, OrdersService
from app.modules.promo_codes.service import PromoCodeCalculation
from app.modules.settings.router import get_settings_service
from app.modules.settings.schemas import PaymentSuccessBannerSettingsRead
from app.modules.telegram.service import TelegramDeliveryError


class DummySession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def flush(self) -> None:
        return None

    async def refresh(self, _: object) -> None:
        return None


class FakeOrderEventPublisher:
    def __init__(self, session: DummySession | None = None) -> None:
        self.session = session
        self.events: list[tuple[str, dict[str, object]]] = []
        self.commit_states: list[bool] = []

    async def emit(self, name: str, payload: dict[str, object]) -> None:
        self.events.append((name, payload))
        if self.session is not None:
            self.commit_states.append(self.session.committed)


class FailingOrderEventPublisher:
    async def emit(self, name: str, payload: dict[str, object]) -> None:
        raise RuntimeError(f"{name} delivery failed")


class FakeAnalyticsTracker:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    async def track(self, event_name: str, **payload: object) -> None:
        self.events.append((event_name, payload))


class FakeAuditService:
    def __init__(self) -> None:
        self.logs: list[dict[str, object]] = []

    async def record_action(self, **payload: object) -> None:
        self.logs.append(payload)

    def snapshot(self, instance: object, fields: tuple[str, ...]) -> dict[str, object]:
        return {field: getattr(instance, field) for field in fields}


class FakePromoCodesService:
    def __init__(
        self,
        *,
        error: AppError | None = None,
        discount_amount: Decimal = Decimal("10.00"),
        discount_type: DiscountType = DiscountType.FIXED,
    ) -> None:
        self.error = error
        self.discount_amount = discount_amount
        self.discount_type = discount_type
        self.usages: list[CouponUsage] = []

    async def validate_for_checkout(
        self,
        *,
        user_id: int,
        code: str,
        subtotal_amount: Decimal,
        for_update: bool,
    ) -> PromoCodeCalculation:
        assert user_id == 1
        assert code == "SAVE10"
        assert for_update is True
        if self.error is not None:
            raise self.error

        promo_code = PromoCode(
            id=7,
            code=code,
            discount_type=self.discount_type,
            discount_value=self.discount_amount,
            is_active=True,
            starts_at=None,
            ends_at=None,
            usage_limit=None,
            per_user_limit=None,
            created_at=_now(),
            updated_at=_now(),
        )
        return PromoCodeCalculation(
            promo_code=promo_code,
            subtotal_amount=subtotal_amount,
            discount_amount=self.discount_amount,
            total_amount=subtotal_amount - self.discount_amount,
        )

    def record_usage_for_checkout(
        self,
        *,
        promo_code_id: int,
        user_id: int,
        order_id: int,
    ) -> None:
        self.usages.append(
            CouponUsage(
                promo_code_id=promo_code_id,
                user_id=user_id,
                order_id=order_id,
                used_at=_now(),
            )
        )


class FakeManualPaymentsService:
    def __init__(self, *, enabled: bool = True) -> None:
        self.settings = SellerPaymentSettings(
            id=1,
            seller_phone_e164="+79999999999",
            seller_phone_display="+7 (999) 999-99-99",
            seller_bank_name="Bank",
            seller_recipient_name="Ada L.",
            is_manual_sbp_enabled=enabled,
            created_at=_now(),
            updated_at=_now(),
        )

    async def require_checkout_settings(self) -> SellerPaymentSettings:
        if not self.settings.is_manual_sbp_enabled:
            raise AppError("Manual SBP payment is not configured")
        return self.settings

    async def create_for_checkout(
        self,
        order: Order,
        *,
        payment_settings: SellerPaymentSettings,
    ) -> ManualPayment:
        payment = ManualPayment(
            id=order.id,
            order_id=order.id,
            order=order,
            method=ManualPaymentMethod.SBP_PHONE,
            amount=order.total_amount,
            currency=ManualPaymentCurrency.RUB,
            seller_phone_e164=payment_settings.seller_phone_e164,
            seller_phone_display=payment_settings.seller_phone_display,
            seller_bank_name=payment_settings.seller_bank_name,
            seller_recipient_name=payment_settings.seller_recipient_name,
            payment_comment=f"Заказ #{order.id}",
            status=ManualPaymentStatus.PENDING,
            expires_at=_now(),
            created_at=_now(),
            updated_at=_now(),
        )
        order.manual_payment = payment
        return payment


class FakeIdempotencyService:
    def __init__(self) -> None:
        self.records: dict[tuple[int, str, str], dict[str, object]] = {}
        self.locks: dict[tuple[int, str, str], asyncio.Lock] = {}

    async def begin(
        self,
        *,
        user_id: int,
        scope: str,
        key: str,
        request_hash: str,
    ) -> SimpleNamespace:
        record_key = (user_id, scope, key)
        lock = self.locks.setdefault(record_key, asyncio.Lock())
        await lock.acquire()
        record = self.records.get(record_key)
        if record is None:
            record = {
                "request_hash": request_hash,
                "response_body": None,
                "lock": lock,
            }
            self.records[record_key] = record
            return SimpleNamespace(record=record, replay_response=None)
        if record["request_hash"] != request_hash:
            lock.release()
            raise AppError(
                "Idempotency-Key was already used with different request payload",
                409,
            )
        response_body = record["response_body"]
        lock.release()
        return SimpleNamespace(record=record, replay_response=response_body)

    def complete(
        self,
        claim: SimpleNamespace | None,
        *,
        response_body: dict[str, object],
        response_status_code: int,
    ) -> None:
        del response_status_code
        if claim is None or claim.record is None:
            return
        claim.record["response_body"] = response_body
        claim.record["lock"].release()


class FakeUserBlocksService:
    def __init__(self, *, blocked_user_ids: set[int] | None = None) -> None:
        self.blocked_user_ids = blocked_user_ids or set()

    async def assert_user_not_blocked(self, user_id: int) -> None:
        if user_id in self.blocked_user_ids:
            raise AppError("Ваш аккаунт ограничен. Свяжитесь с продавцом.", 403)


class FakeOrdersRepository:
    def __init__(self) -> None:
        self.carts: dict[int, Cart] = {}
        self.orders: dict[int, Order] = {}
        self.variants: dict[int, ProductVariant] = {}
        self.next_order_id = 1
        self.next_order_sequence = 1
        self.next_order_item_id = 1
        self.banner_settings = SellerPaymentSettings(
            id=1,
            payment_success_banner_enabled=False,
            payment_success_banner_image_path=None,
            created_at=_now(),
            updated_at=_now(),
        )

    async def next_order_number(self) -> str:
        try:
            order_number = format_order_number(self.next_order_sequence)
        except ValueError as exc:
            raise AppError("Order number sequence exhausted", 409) from exc
        self.next_order_sequence += 1
        return order_number

    async def get_cart_for_checkout(self, user_id: int) -> Cart | None:
        return self.carts.get(user_id)

    async def lock_variants_by_ids(self, variant_ids: list[int]) -> dict[int, ProductVariant]:
        return {variant_id: self.variants[variant_id] for variant_id in variant_ids}

    async def list_for_user(self, *, user_id: int, limit: int, offset: int) -> list[Order]:
        del limit, offset
        return [order for order in self.orders.values() if order.user_id == user_id]

    async def list_all(
        self,
        *,
        limit: int,
        offset: int,
        status: OrderStatus | None = None,
        user_id: int | None = None,
        search: str | None = None,
    ) -> list[Order]:
        del limit, offset
        orders = list(self.orders.values())
        if status is not None:
            orders = [order for order in orders if order.status == status]
        if user_id is not None:
            orders = [order for order in orders if order.user_id == user_id]
        if search is not None:
            orders = [
                order
                for order in orders
                if search in order.order_number or search == str(order.id)
            ]
        return orders

    async def get_by_id(self, order_id: int) -> Order | None:
        return self.orders.get(order_id)

    async def get_for_user(self, *, user_id: int, order_id: int) -> Order | None:
        order = self.orders.get(order_id)
        if order is None or order.user_id != user_id:
            return None
        return order

    async def get_payment_success_banner_settings(self) -> SellerPaymentSettings | None:
        return self.banner_settings

    async def get_pending_payment_success_banner_order(self, *, user_id: int) -> Order | None:
        orders = [
            order
            for order in self.orders.values()
            if order.user_id == user_id
            and order.payment_success_banner_seen_at is None
            and order.manual_payment is not None
            and order.manual_payment.status == ManualPaymentStatus.APPROVED
        ]
        return sorted(orders, key=lambda order: order.id, reverse=True)[0] if orders else None

    async def get_paid_order_for_user_for_banner(
        self,
        *,
        user_id: int,
        order_id: int,
        for_update: bool = False,
    ) -> Order | None:
        del for_update
        order = self.orders.get(order_id)
        if (
            order is None
            or order.user_id != user_id
            or order.manual_payment is None
            or order.manual_payment.status != ManualPaymentStatus.APPROVED
        ):
            return None
        return order

    def add(self, instance: Order | OrderItem) -> None:
        if isinstance(instance, Order):
            instance.id = self.next_order_id
            self.next_order_id += 1
            instance.created_at = _now()
            instance.updated_at = _now()
            instance.items = []
            self.orders[instance.id] = instance
            return

        instance.id = self.next_order_item_id
        self.next_order_item_id += 1
        instance.created_at = _now()
        order = self.orders[instance.order_id]
        order.items.append(instance)

    async def clear_cart(self, cart_id: int) -> None:
        for cart in self.carts.values():
            if cart.id == cart_id:
                cart.items = []
                return

    async def clear_cart_items(self, cart_id: int, item_ids: list[int]) -> None:
        selected_ids = set(item_ids)
        for cart in self.carts.values():
            if cart.id == cart_id:
                cart.items = [item for item in cart.items if item.id not in selected_ids]
                return


class FakeNotificationsRepository:
    def __init__(self) -> None:
        self.notifications: dict[int, Notification] = {}
        self.next_notification_id = 1

    def add(self, notification: Notification) -> None:
        notification.id = self.next_notification_id
        self.next_notification_id += 1
        notification.created_at = _now()
        notification.updated_at = _now()
        self.notifications[notification.id] = notification

    async def get_by_id(self, notification_id: int) -> Notification | None:
        return self.notifications.get(notification_id)


class FailingTelegramService:
    async def send_seller_notification(
        self,
        message: str,
        *,
        parse_mode: str | None = None,
    ) -> None:
        del parse_mode
        del message
        raise TelegramDeliveryError("Telegram unavailable")


@pytest.mark.asyncio
async def test_checkout_from_valid_cart(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "public_mini_app_base_url", "https://mini.stylexac.ru/")
    monkeypatch.setattr(settings, "public_seller_panel_base_url", "https://seller.stylexac.ru/")
    monkeypatch.setattr(settings, "public_uploads_url", "https://api.stylexac.ru/uploads/")
    service, repository, session, events = _orders_service()

    order = await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())

    assert order.order_number == "ORD-000001"
    assert order.user_id == 1
    assert order.status == OrderStatus.NEW
    assert order.delivery_method == OrderDeliveryMethod.CDEK
    assert order.delivery_price == Decimal("0.00")
    assert order.total_amount == Decimal("119.80")
    assert order.items[0].product_name == "Hoodie"
    assert order.items[0].variant_size == "M"
    assert order.items[0].variant_size_grid == ProductSizeGrid.CLOTHING_ALPHA
    assert order.items[0].variant_sku == "HOODIE-M-BLK"
    assert order.items[0].is_returnable is True
    assert order.manual_payment is not None
    assert order.manual_payment.status == ManualPaymentStatus.PENDING
    assert repository.variants[1].stock_quantity == 3
    assert repository.carts[1].items == []
    assert session.committed is True
    assert len(events.events) == 1
    event_name, event_payload = events.events[0]
    assert event_name == ORDER_CREATED
    assert event_payload["order_id"] == 1
    assert event_payload["order_number"] == order.order_number
    assert event_payload["status"] == "NEW"
    assert event_payload["user_id"] == 1
    assert event_payload["subtotal_amount"] == "119.80"
    assert event_payload["discount_amount"] == "0.00"
    assert event_payload["total_amount"] == "119.80"
    assert event_payload["promo_code_id"] is None
    assert event_payload["promo_code"] is None
    assert event_payload["customer"]["user_id"] == 1
    assert event_payload["items"][0]["product_title"] == "Hoodie"
    assert event_payload["items"][0]["product_id"] == 1
    assert event_payload["items"][0]["product_link"] == "https://mini.stylexac.ru/product/1"
    assert event_payload["items"][0]["product_image_url"] == (
        "https://api.stylexac.ru/uploads/products/hoodie.webp"
    )
    assert event_payload["items"][0]["variant_color"] == "Black"
    assert event_payload["items"][0]["variant_sku"] == "HOODIE-M-BLK"
    assert event_payload["items"][0]["quantity"] == 2
    assert event_payload["contact"]["name"] == "Ada Lovelace"
    assert event_payload["delivery_price"] == "0.00"
    assert event_payload["contact"]["delivery_method"] == "CDEK"
    assert event_payload["contact"]["delivery_method_label"] == "СДЭК"
    assert event_payload["seller_panel_url"] == "https://seller.stylexac.ru/orders"
    assert events.commit_states == [True]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("measurements", "expected_comment"),
    [
        ({}, None),
        ({"height_cm": "181"}, "Рост: 181"),
        ({"weight_kg": "76.5"}, "Вес: 76.5"),
        ({"height_cm": "181", "weight_kg": "76.5"}, "Рост: 181\nВес: 76.5"),
    ],
    ids=["neither", "height-only", "weight-only", "both"],
)
async def test_checkout_supports_optional_measurement_snapshots(
    measurements: dict[str, str],
    expected_comment: str | None,
) -> None:
    service, _, _, _ = _orders_service()
    payload = _checkout_payload_json()
    payload.pop("height_cm")
    payload.pop("weight_kg")
    payload["delivery_comment"] = None
    payload.update(measurements)

    order = await service.checkout_current_user_cart(
        user_id=1,
        payload=OrderCheckoutCreate.model_validate(payload),
    )

    assert order.delivery_comment == expected_comment


@pytest.mark.asyncio
async def test_checkout_assigns_sequential_human_order_numbers() -> None:
    service, repository, _, _ = _orders_service()

    first = await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())
    repository.carts[1] = _cart(user_id=1)
    repository.variants = {
        item.product_variant_id: item.product_variant
        for item in repository.carts[1].items
    }
    second = await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())

    assert first.order_number == "ORD-000001"
    assert second.order_number == "ORD-000002"
    assert all(
        order.order_number.startswith("ORD-") and len(order.order_number) == 10
        for order in (first, second)
    )


@pytest.mark.asyncio
async def test_checkout_rejects_exhausted_order_number_sequence() -> None:
    service, repository, session, _ = _orders_service()
    repository.next_order_sequence = ORDER_NUMBER_MAX + 1

    with pytest.raises(AppError, match="Order number sequence exhausted"):
        await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())

    assert session.rolled_back is True
    assert repository.orders == {}


@pytest.mark.asyncio
async def test_checkout_copies_look_source_metadata_to_order_items() -> None:
    product = _product()
    variant = _variant()
    source_cart_item = CartItem(
        id=1,
        cart_id=1,
        product_id=product.id,
        product_variant_id=variant.id,
        product=product,
        product_variant=variant,
        quantity=1,
        is_selected=True,
        source_type="LOOK",
        source_look_id=15,
        source_look_slug="linen-summer",
        source_look_title="Linen Summer",
        source_look_image_url="/uploads/looks/linen-summer.webp",
        source_group_id="look-group-1",
        created_at=_now(),
        updated_at=_now(),
    )
    service, repository, _, _ = _orders_service(cart_items=[source_cart_item])

    order = await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())

    item = order.items[0]
    assert item.source_type == "LOOK"
    assert item.source_look_id == 15
    assert item.source_look_slug == "linen-summer"
    assert item.source_look_title == "Linen Summer"
    assert item.source_look_image_url == "/uploads/looks/linen-summer.webp"
    assert item.source_group_id == "look-group-1"
    assert repository.orders[order.id].items[0].source_look_title == "Linen Summer"


@pytest.mark.asyncio
async def test_order_read_keeps_look_title_slug_snapshot_after_source_look_rename() -> None:
    product = _product()
    variant = _variant()
    source_cart_item = CartItem(
        id=1,
        cart_id=1,
        product_id=product.id,
        product_variant_id=variant.id,
        product=product,
        product_variant=variant,
        quantity=1,
        is_selected=True,
        source_type="LOOK",
        source_look_id=15,
        source_look_slug="original-look",
        source_look_title="Original Look",
        source_look_image_url="/uploads/looks/original.webp",
        source_group_id="look-group-snapshot",
        created_at=_now(),
        updated_at=_now(),
    )
    service, repository, _, _ = _orders_service(cart_items=[source_cart_item])

    created = await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())
    source_cart_item.source_look_slug = "renamed-look"
    source_cart_item.source_look_title = "Renamed Look"
    detail = await service.get_current_user_order(user_id=1, order_id=created.id)

    assert detail.items[0].source_look_slug == "original-look"
    assert detail.items[0].source_look_title == "Original Look"
    assert repository.orders[created.id].items[0].source_look_slug == "original-look"


@pytest.mark.asyncio
async def test_checkout_with_same_idempotency_key_returns_original_order() -> None:
    idempotency_service = FakeIdempotencyService()
    service, repository, _, events = _orders_service(idempotency_service=idempotency_service)

    first = await service.checkout_current_user_cart(
        user_id=1,
        payload=_checkout_payload(),
        idempotency_key="checkout-key-1",
    )
    second = await service.checkout_current_user_cart(
        user_id=1,
        payload=_checkout_payload(),
        idempotency_key="checkout-key-1",
    )

    assert first.id == second.id == 1
    assert len(repository.orders) == 1
    assert repository.variants[1].stock_quantity == 3
    assert [event[0] for event in events.events] == [ORDER_CREATED]


@pytest.mark.asyncio
async def test_concurrent_checkout_with_same_idempotency_key_creates_one_order() -> None:
    idempotency_service = FakeIdempotencyService()
    service, repository, _, events = _orders_service(idempotency_service=idempotency_service)

    first, second = await asyncio.gather(
        service.checkout_current_user_cart(
            user_id=1,
            payload=_checkout_payload(),
            idempotency_key="checkout-key-concurrent",
        ),
        service.checkout_current_user_cart(
            user_id=1,
            payload=_checkout_payload(),
            idempotency_key="checkout-key-concurrent",
        ),
    )

    assert first.id == second.id == 1
    assert len(repository.orders) == 1
    assert repository.variants[1].stock_quantity == 3
    assert repository.carts[1].items == []
    assert [event[0] for event in events.events] == [ORDER_CREATED]


@pytest.mark.asyncio
async def test_checkout_same_idempotency_key_with_different_payload_returns_conflict() -> None:
    idempotency_service = FakeIdempotencyService()
    service, repository, _, _ = _orders_service(idempotency_service=idempotency_service)
    payload = _checkout_payload()
    changed_payload = OrderCheckoutCreate.model_validate(
        {
            **_checkout_payload_json(),
            "contact_phone": "+79990001122",
        }
    )

    await service.checkout_current_user_cart(
        user_id=1,
        payload=payload,
        idempotency_key="checkout-key-conflict",
    )
    with pytest.raises(AppError, match="different request payload") as exc_info:
        await service.checkout_current_user_cart(
            user_id=1,
            payload=changed_payload,
            idempotency_key="checkout-key-conflict",
        )

    assert exc_info.value.status_code == 409
    assert len(repository.orders) == 1
    assert repository.variants[1].stock_quantity == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("delivery_method", list(OrderDeliveryMethod))
async def test_checkout_stores_each_supported_delivery_method(
    delivery_method: OrderDeliveryMethod,
) -> None:
    service, _, _, _ = _orders_service()
    payload = _checkout_payload_json()
    payload["delivery_method"] = delivery_method.value

    order = await service.checkout_current_user_cart(
        user_id=1,
        payload=OrderCheckoutCreate.model_validate(payload),
    )

    assert order.delivery_method == delivery_method


@pytest.mark.asyncio
async def test_checkout_with_pickup_requires_address() -> None:
    payload = _checkout_payload_json()
    payload["delivery_method"] = OrderDeliveryMethod.PICKUP.value
    payload["delivery_address"] = ""

    with pytest.raises(ValidationError):
        OrderCheckoutCreate.model_validate(payload)


@pytest.mark.asyncio
async def test_checkout_with_paid_delivery_requires_address() -> None:
    payload = _checkout_payload_json()
    payload["delivery_method"] = OrderDeliveryMethod.ROUTE_TAXI.value
    payload["delivery_address"] = " "

    with pytest.raises(ValidationError):
        OrderCheckoutCreate.model_validate(payload)


@pytest.mark.asyncio
async def test_checkout_stores_delivery_price_snapshot_and_total_includes_delivery() -> None:
    service, repository, _, events = _orders_service()
    payload = _checkout_payload_json()
    payload["delivery_method"] = OrderDeliveryMethod.ROUTE_TAXI.value

    order = await service.checkout_current_user_cart(
        user_id=1,
        payload=OrderCheckoutCreate.model_validate(payload),
    )

    assert order.delivery_price == Decimal("200.00")
    assert order.total_amount == Decimal("319.80")
    assert repository.orders[order.id].delivery_price == Decimal("200.00")
    assert events.events[0][1]["delivery_price"] == "200.00"


@pytest.mark.asyncio
async def test_checkout_customer_notifications_emit_after_successful_commit() -> None:
    service, _, session, _ = _orders_service()
    seller_events = FakeOrderEventPublisher(session)
    customer_events = FakeOrderEventPublisher(session)
    service.event_publisher = InternalOrderEventPublisher(
        session,
        notifications_publisher=seller_events,
        customer_notifications_publisher=customer_events,
    )

    await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())

    assert customer_events.events[0][0] == ORDER_CREATED
    assert customer_events.commit_states == [True]


@pytest.mark.asyncio
async def test_checkout_with_valid_promo_code_creates_order_and_coupon_usage() -> None:
    promo_codes_service = FakePromoCodesService(discount_amount=Decimal("20.00"))
    service, repository, session, events = _orders_service(
        promo_codes_service=promo_codes_service,
    )

    order = await service.checkout_current_user_cart(
        user_id=1,
        payload=OrderCheckoutCreate(
            **_checkout_payload_json(),
            promo_code="save10",
        ),
    )

    assert order.subtotal_amount == Decimal("119.80")
    assert order.discount_amount == Decimal("20.00")
    assert order.total_amount == Decimal("99.80")
    assert order.promo_code_id == 7
    assert order.promo_code_code == "SAVE10"
    assert len(promo_codes_service.usages) == 1
    assert promo_codes_service.usages[0].promo_code_id == 7
    assert promo_codes_service.usages[0].order_id == order.id
    assert session.committed is True
    assert repository.carts[1].items == []
    assert [event[0] for event in events.events] == [ORDER_CREATED, PROMO_USED]
    assert order.promo_code == "SAVE10"
    assert order.promo_applied is True
    assert order.discount == Decimal("20.00")
    assert order.total == Decimal("99.80")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("discount_type", "discount_amount", "expected_total"),
    [
        (DiscountType.PERCENT, Decimal("11.98"), Decimal("107.82")),
        (DiscountType.FIXED, Decimal("25.00"), Decimal("94.80")),
    ],
)
async def test_checkout_with_valid_promo_discount_types_applies_discount(
    discount_type: DiscountType,
    discount_amount: Decimal,
    expected_total: Decimal,
) -> None:
    service, _, _, _ = _orders_service(
        promo_codes_service=FakePromoCodesService(
            discount_type=discount_type,
            discount_amount=discount_amount,
        ),
    )

    order = await service.checkout_current_user_cart(
        user_id=1,
        payload=OrderCheckoutCreate(
            **_checkout_payload_json(),
            promo_code="save10",
        ),
    )

    assert order.subtotal_amount == Decimal("119.80")
    assert order.discount_amount == discount_amount
    assert order.total_amount == expected_total
    assert order.promo_code_code == "SAVE10"


@pytest.mark.asyncio
async def test_checkout_promo_discount_does_not_discount_delivery() -> None:
    service, _, _, _ = _orders_service(
        promo_codes_service=FakePromoCodesService(discount_amount=Decimal("119.80")),
    )
    payload = _checkout_payload_json()
    payload["delivery_method"] = OrderDeliveryMethod.ROUTE_TAXI.value

    order = await service.checkout_current_user_cart(
        user_id=1,
        payload=OrderCheckoutCreate(
            **payload,
            promo_code="save10",
        ),
    )

    assert order.subtotal_amount == Decimal("119.80")
    assert order.discount_amount == Decimal("119.80")
    assert order.delivery_price == Decimal("200.00")
    assert order.total_amount == Decimal("200.00")


@pytest.mark.asyncio
async def test_checkout_tracks_order_created_analytics_event() -> None:
    tracker = FakeAnalyticsTracker()
    service, _, _, _ = _orders_service(analytics_tracker=tracker)

    order = await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())

    assert "checkout.started" in [event_name for event_name, _ in tracker.events]
    assert (
        "order.created",
        {
            "user_id": 1,
            "order_id": order.id,
            "promo_code_id": None,
            "metadata": {
                "user_id": 1,
                "order_id": order.id,
                "promo_code_id": None,
                "total_amount": "119.80",
            },
        },
    ) in tracker.events


@pytest.mark.asyncio
async def test_checkout_with_promo_tracks_promo_used_analytics_event() -> None:
    tracker = FakeAnalyticsTracker()
    service, _, _, _ = _orders_service(
        promo_codes_service=FakePromoCodesService(discount_amount=Decimal("20.00")),
        analytics_tracker=tracker,
    )

    order = await service.checkout_current_user_cart(
        user_id=1,
        payload=OrderCheckoutCreate(
            **_checkout_payload_json(),
            promo_code="save10",
        ),
    )

    assert (
        "promo.used",
        {
            "user_id": 1,
            "order_id": order.id,
            "promo_code_id": 7,
            "metadata": {
                "user_id": 1,
                "order_id": order.id,
                "promo_code_id": 7,
                "promo_code": "SAVE10",
            },
        },
    ) in tracker.events


@pytest.mark.asyncio
async def test_telegram_send_failure_does_not_rollback_successful_checkout() -> None:
    service, _, session, _ = _orders_service()
    notifications_service = NotificationsService(
        session,
        telegram_service=FailingTelegramService(),
    )
    notifications_repository = FakeNotificationsRepository()
    notifications_service.repository = notifications_repository
    service.event_publisher = NotificationsEventPublisher(session, notifications_service)

    order = await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())

    assert order.id == 1
    assert session.committed is True
    assert session.rolled_back is False
    assert notifications_repository.notifications[1].status == NotificationStatus.FAILED


@pytest.mark.asyncio
async def test_checkout_with_invalid_promo_code_fails_without_partial_order() -> None:
    promo_codes_service = FakePromoCodesService(
        error=AppError("Promo code is inactive"),
    )
    service, repository, session, events = _orders_service(
        promo_codes_service=promo_codes_service,
    )

    with pytest.raises(AppError, match="Promo code is inactive"):
        await service.checkout_current_user_cart(
            user_id=1,
            payload=OrderCheckoutCreate(
                **_checkout_payload_json(),
                promo_code="SAVE10",
            ),
        )

    assert repository.orders == {}
    assert repository.variants[1].stock_quantity == 5
    assert repository.carts[1].items != []
    assert promo_codes_service.usages == []
    assert session.rolled_back is True
    assert events.events == []


@pytest.mark.asyncio
async def test_reject_empty_cart_checkout() -> None:
    service, repository, session, events = _orders_service(cart_items=[])

    with pytest.raises(AppError, match="Cart is empty"):
        await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())

    assert repository.orders == {}
    assert session.rolled_back is True
    assert events.events == []


@pytest.mark.asyncio
async def test_reject_checkout_when_no_cart_items_selected() -> None:
    product = _product()
    variant = _variant()
    service, repository, session, events = _orders_service(
        cart_items=[
            CartItem(
                id=1,
                cart_id=1,
                product_id=product.id,
                product_variant_id=variant.id,
                product=product,
                product_variant=variant,
                quantity=1,
                is_selected=False,
                created_at=_now(),
                updated_at=_now(),
            )
        ],
    )

    with pytest.raises(AppError, match="No selected cart items"):
        await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())

    assert repository.orders == {}
    assert repository.variants[1].stock_quantity == 5
    assert session.rolled_back is True
    assert events.events == []


@pytest.mark.asyncio
async def test_reject_inactive_product_checkout() -> None:
    service, repository, _, _ = _orders_service(product_status=ProductStatus.DRAFT)

    with pytest.raises(AppError, match="Product is not active"):
        await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())

    assert repository.orders == {}
    assert repository.variants[1].stock_quantity == 5


@pytest.mark.asyncio
async def test_reject_inactive_variant_checkout() -> None:
    service, repository, _, _ = _orders_service(variant_is_active=False)

    with pytest.raises(AppError, match="Product variant is not active"):
        await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())

    assert repository.orders == {}
    assert repository.variants[1].stock_quantity == 5


@pytest.mark.asyncio
async def test_reject_insufficient_stock_checkout() -> None:
    service, repository, _, _ = _orders_service(stock_quantity=1)

    with pytest.raises(AppError, match="Insufficient stock"):
        await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())

    assert repository.orders == {}
    assert repository.variants[1].stock_quantity == 1


@pytest.mark.asyncio
async def test_stock_deducted_after_successful_checkout() -> None:
    service, repository, _, _ = _orders_service(stock_quantity=7)

    await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())

    assert repository.variants[1].stock_quantity == 5


@pytest.mark.asyncio
async def test_checkout_requires_enabled_manual_payment_settings() -> None:
    service, repository, session, _ = _orders_service(manual_payments_enabled=False)

    with pytest.raises(AppError, match="Manual SBP payment is not configured"):
        await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())

    assert repository.orders == {}
    assert repository.variants[1].stock_quantity == 5
    assert session.rolled_back is True


@pytest.mark.asyncio
async def test_cart_cleared_after_successful_checkout() -> None:
    service, repository, _, _ = _orders_service()

    await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())

    assert repository.carts[1].items == []


@pytest.mark.asyncio
async def test_checkout_uses_selected_cart_items_and_preserves_unselected() -> None:
    first_product = _product()
    first_variant = _variant()
    second_product = _product(product_id=2, name="Sneakers", base_price=Decimal("80.00"))
    second_variant = _variant(
        variant_id=2,
        product_id=2,
        size="42",
        color="White",
        sku="SNEAKERS-42-WHT",
        stock_quantity=5,
    )
    cart_items = [
        CartItem(
            id=1,
            cart_id=1,
            product_id=first_product.id,
            product_variant_id=first_variant.id,
            product=first_product,
            product_variant=first_variant,
            quantity=1,
            is_selected=True,
            created_at=_now(),
            updated_at=_now(),
        ),
        CartItem(
            id=2,
            cart_id=1,
            product_id=second_product.id,
            product_variant_id=second_variant.id,
            product=second_product,
            product_variant=second_variant,
            quantity=3,
            is_selected=False,
            created_at=_now(),
            updated_at=_now(),
        ),
    ]
    service, repository, _, _ = _orders_service(cart_items=cart_items)

    order = await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())

    assert order.subtotal_amount == Decimal("59.90")
    assert order.total_amount == Decimal("59.90")
    assert [item.product_id for item in order.items] == [1]
    assert repository.variants[1].stock_quantity == 4
    assert repository.variants[2].stock_quantity == 5
    assert [item.id for item in repository.carts[1].items] == [2]


@pytest.mark.asyncio
async def test_order_item_snapshot_is_immutable() -> None:
    service, repository, _, _ = _orders_service()

    order = await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())
    repository.carts[1] = _cart(user_id=1)
    repository.carts[1].items[0].product.name = "Renamed Hoodie"
    repository.carts[1].items[0].product.base_price = Decimal("10.00")
    repository.carts[1].items[0].product.size_grid = ProductSizeGrid.SHOES_RU
    repository.variants[1].size = "L"
    repository.variants[1].sku = "CHANGED"

    assert order.items[0].product_name == "Hoodie"
    assert order.items[0].variant_size == "M"
    assert order.items[0].variant_size_grid == ProductSizeGrid.CLOTHING_ALPHA
    assert order.items[0].variant_color == "Black"
    assert order.items[0].variant_sku == "HOODIE-M-BLK"
    assert order.items[0].unit_price == Decimal("59.90")


@pytest.mark.asyncio
async def test_checkout_accepts_active_unlisted_product() -> None:
    service, _, _, _ = _orders_service(product_is_listed=False)

    order = await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())

    assert order.items[0].product_id == 1
    assert order.status == OrderStatus.NEW


@pytest.mark.asyncio
async def test_checkout_snapshots_order_item_returnability() -> None:
    service, repository, _, _ = _orders_service(product_is_returnable=False)

    order = await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())
    repository.orders[order.id].items[0].product.is_returnable = True

    assert order.items[0].is_returnable is False
    assert repository.orders[order.id].items[0].is_returnable is False


@pytest.mark.asyncio
async def test_order_response_contains_rich_item_and_total_fields() -> None:
    promo_codes_service = FakePromoCodesService(discount_amount=Decimal("20.00"))
    service, _, _, _ = _orders_service(promo_codes_service=promo_codes_service)

    order = await service.checkout_current_user_cart(
        user_id=1,
        payload=OrderCheckoutCreate(
            **_checkout_payload_json(),
            promo_code="save10",
        ),
    )
    body = order.model_dump()
    item = body["items"][0]

    assert body["subtotal"] == Decimal("119.80")
    assert body["discount"] == Decimal("20.00")
    assert body["total"] == Decimal("99.80")
    assert body["promo_code"] == "SAVE10"
    assert body["promo_applied"] is True
    assert item["product_title"] == "Hoodie"
    assert item["product_brand"] == "ICON STORE"
    assert item["variant_color"] == "Black"
    assert item["item_total"] == Decimal("119.80")
    assert item["is_returnable"] is True
    assert item["product_thumbnail_path"] == "products/hoodie.webp"
    assert item["product_thumbnail_url"] == "/uploads/products/hoodie.webp"


def test_order_item_read_prefers_product_thumbnail_derivative() -> None:
    product = _product()
    product.images[0].thumbnail_path = "products/hoodie.thumbnail.webp"
    product.images[0].card_path = "products/hoodie.card.webp"
    item = OrderItem(
        id=1,
        order_id=1,
        product_id=product.id,
        product_variant_id=1,
        product_name=product.name,
        variant_size="M",
        variant_size_grid=ProductSizeGrid.CLOTHING_ALPHA,
        variant_color="Black",
        variant_sku="HOODIE-M-BLK",
        unit_price=Decimal("59.90"),
        quantity=1,
        subtotal=Decimal("59.90"),
        created_at=_now(),
    )
    item.product = product

    read = OrderItemRead.model_validate(item)

    assert read.product_thumbnail_path == "products/hoodie.thumbnail.webp"
    assert read.product_thumbnail_url == "/uploads/products/hoodie.thumbnail.webp"


@pytest.mark.asyncio
async def test_user_can_list_own_orders() -> None:
    service, repository, _, _ = _orders_service()
    repository.orders[2] = _order(order_id=2, user_id=2)
    await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())

    orders = await service.list_current_user_orders(user_id=1)

    assert [order.user_id for order in orders.items] == [1]
    assert orders.items[0].delivery_method == OrderDeliveryMethod.CDEK
    assert orders.items[0].return_eligibility is not None
    assert orders.items[0].return_eligibility.eligible is False


@pytest.mark.asyncio
async def test_customer_order_list_includes_compact_return_eligibility() -> None:
    service, repository, _, _ = _orders_service()
    delivered = _order(order_id=10, user_id=1, status_value=OrderStatus.DELIVERED)
    delivered.delivered_at = _now()
    repository.orders[10] = delivered

    orders = await service.list_current_user_orders(user_id=1)

    summary = orders.items[0].return_eligibility
    assert summary is not None
    assert summary.eligible is True
    assert summary.reason_code is None
    assert summary.return_request_id is None
    assert summary.deadline_at == _now() + timedelta(hours=24)


@pytest.mark.asyncio
async def test_old_order_without_delivery_method_remains_readable() -> None:
    service, repository, _, _ = _orders_service()
    legacy_order = _order(order_id=10, user_id=1)
    legacy_order.delivery_method = None
    repository.orders[10] = legacy_order

    order = await service.get_current_user_order(user_id=1, order_id=10)

    assert order.delivery_method is None


@pytest.mark.asyncio
async def test_order_detail_returns_delivery_method() -> None:
    service, repository, _, _ = _orders_service()
    repository.orders[10] = _order(order_id=10, user_id=1)

    customer_order = await service.get_current_user_order(user_id=1, order_id=10)
    seller_order = await service.get_order(order_id=10)

    assert customer_order.delivery_method == OrderDeliveryMethod.CDEK
    assert seller_order.delivery_method == OrderDeliveryMethod.CDEK
    assert customer_order.delivery_price == Decimal("0.00")
    assert seller_order.delivery_price == Decimal("0.00")


@pytest.mark.asyncio
async def test_user_cannot_access_another_users_order() -> None:
    service, repository, _, _ = _orders_service()
    repository.orders[10] = _order(order_id=10, user_id=2)

    with pytest.raises(AppError, match="Order not found"):
        await service.get_current_user_order(user_id=1, order_id=10)


@pytest.mark.asyncio
async def test_seller_admin_can_list_and_update_orders() -> None:
    service, repository, _, events = _orders_service()
    repository.orders[10] = _order(order_id=10, user_id=1)

    orders = await service.list_orders()
    filtered = await service.list_orders(status=OrderStatus.NEW, search="10")
    updated = await service.update_order_status(10, OrderStatusUpdate(status=OrderStatus.SHIPPED))

    assert len(orders.items) == 1
    assert len(filtered.items) == 1
    assert updated.status == OrderStatus.SHIPPED
    assert events.events == [
        (
            ORDER_STATUS_CHANGED,
            {
                "order_id": 10,
                "order_number": "ORD-000010",
                "user_id": 1,
                "previous_status": "NEW",
                "new_status": "SHIPPED",
            },
        ),
        (
            ORDER_SHIPPED,
            {
                "order_id": 10,
                "order_number": "ORD-000010",
                "user_id": 1,
                "status": "SHIPPED",
            },
        ),
    ]


@pytest.mark.asyncio
async def test_order_status_update_to_delivered_sets_delivered_at_once() -> None:
    service, repository, _, _ = _orders_service()
    order = _order(order_id=10, user_id=1)
    repository.orders[10] = order

    delivered = await service.update_order_status(
        10,
        OrderStatusUpdate(status=OrderStatus.DELIVERED),
    )
    first_delivered_at = delivered.delivered_at
    redelivered = await service.update_order_status(
        10,
        OrderStatusUpdate(status=OrderStatus.DELIVERED),
    )

    assert first_delivered_at is not None
    assert redelivered.delivered_at == first_delivered_at
    assert repository.orders[10].delivered_at == first_delivered_at


@pytest.mark.asyncio
async def test_order_status_update_preserves_delivered_at_after_later_status_change() -> None:
    service, repository, _, _ = _orders_service()
    delivered_at = datetime(2026, 5, 28, tzinfo=UTC)
    order = _order(order_id=10, user_id=1, status_value=OrderStatus.DELIVERED)
    order.delivered_at = delivered_at
    repository.orders[10] = order

    updated = await service.update_order_status(
        10,
        OrderStatusUpdate(status=OrderStatus.SHIPPED),
    )

    assert updated.status == OrderStatus.SHIPPED
    assert updated.delivered_at == delivered_at


@pytest.mark.asyncio
async def test_approved_manual_payment_order_status_can_advance() -> None:
    service, repository, _, _ = _orders_service()
    order = _order(order_id=10, user_id=1, status_value=OrderStatus.PROCESSING)
    manual_payments = FakeManualPaymentsService()
    payment = await manual_payments.create_for_checkout(
        order,
        payment_settings=manual_payments.settings,
    )
    payment.status = ManualPaymentStatus.APPROVED
    repository.orders[10] = order

    updated = await service.update_order_status(
        10,
        OrderStatusUpdate(status=OrderStatus.SHIPPED),
    )

    assert updated.status == OrderStatus.SHIPPED
    assert updated.manual_payment is not None
    assert updated.manual_payment.status == ManualPaymentStatus.APPROVED


@pytest.mark.asyncio
async def test_order_status_update_does_not_fail_when_seller_notification_fails() -> None:
    service, repository, session, _ = _orders_service()
    customer_events = FakeOrderEventPublisher(session)
    service.event_publisher = InternalOrderEventPublisher(
        session,
        notifications_publisher=FailingOrderEventPublisher(),
        customer_notifications_publisher=customer_events,
    )
    repository.orders[10] = _order(order_id=10, user_id=1)

    updated = await service.update_order_status(
        10,
        OrderStatusUpdate(status=OrderStatus.PROCESSING),
    )

    assert updated.status == OrderStatus.PROCESSING
    assert customer_events.events == [
        (
            ORDER_STATUS_CHANGED,
            {
                "order_id": 10,
                "order_number": "ORD-000010",
                "user_id": 1,
                "previous_status": "NEW",
                "new_status": "PROCESSING",
            },
        )
    ]
    assert customer_events.commit_states == [True]
    assert session.committed is True


@pytest.mark.asyncio
async def test_order_status_update_does_not_fail_when_customer_publisher_raises() -> None:
    service, repository, session, _ = _orders_service()
    seller_events = FakeOrderEventPublisher(session)
    service.event_publisher = InternalOrderEventPublisher(
        session,
        notifications_publisher=seller_events,
        customer_notifications_publisher=FailingOrderEventPublisher(),
    )
    repository.orders[10] = _order(order_id=10, user_id=1)

    updated = await service.update_order_status(
        10,
        OrderStatusUpdate(status=OrderStatus.DELIVERED),
    )

    assert updated.status == OrderStatus.DELIVERED
    assert seller_events.events[0][0] == ORDER_STATUS_CHANGED
    assert session.committed is True
    assert session.rolled_back is True


@pytest.mark.asyncio
async def test_order_status_update_isolates_direct_post_commit_publisher_failure() -> None:
    service, repository, session, _ = _orders_service()
    service.event_publisher = FailingOrderEventPublisher()
    repository.orders[10] = _order(order_id=10, user_id=1)

    updated = await service.update_order_status(
        10,
        OrderStatusUpdate(status=OrderStatus.PROCESSING),
    )

    assert updated.status == OrderStatus.PROCESSING
    assert session.committed is True
    assert session.rolled_back is True


@pytest.mark.asyncio
async def test_order_status_update_returns_legacy_item_size_grid_fallback() -> None:
    service, repository, _, _ = _orders_service()
    order = _order(order_id=10, user_id=1)
    order.items[0].variant_size_grid = None
    repository.orders[10] = order

    updated = await service.update_order_status(
        10,
        OrderStatusUpdate(status=OrderStatus.PROCESSING),
    )

    assert updated.items[0].variant_size_grid == ProductSizeGrid.CLOTHING_ALPHA


@pytest.mark.asyncio
async def test_order_status_update_records_audit_log() -> None:
    audit_service = FakeAuditService()
    service, repository, _, _ = _orders_service(audit_service=audit_service)
    repository.orders[10] = _order(order_id=10, user_id=1)

    await service.update_order_status(
        10,
        OrderStatusUpdate(status=OrderStatus.PROCESSING),
        actor_user_id=2,
    )

    assert audit_service.logs[0]["actor_user_id"] == 2
    assert audit_service.logs[0]["action"] == "order.status_changed"
    assert audit_service.logs[0]["entity_type"] == "order"
    assert audit_service.logs[0]["entity_id"] == 10


@pytest.mark.asyncio
async def test_pending_payment_success_banner_returns_latest_paid_unseen_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "public_uploads_url", "https://api.stylexac.ru/uploads/")
    service, repository, _, _ = _orders_service()
    repository.banner_settings.payment_success_banner_enabled = True
    repository.banner_settings.payment_success_banner_image_path = "banners/paid.webp"
    older_order = _order(order_id=10, user_id=1)
    newer_order = _order(order_id=11, user_id=1)
    older_order.manual_payment = _approved_payment(older_order)
    newer_order.manual_payment = _approved_payment(newer_order)
    repository.orders[10] = older_order
    repository.orders[11] = newer_order

    banner = await service.get_pending_payment_success_banner(user_id=1)

    assert banner is not None
    assert banner.order_id == 11
    assert banner.order_number == "ORD-000011"
    assert banner.image_path == "banners/paid.webp"
    assert banner.image_url == "https://api.stylexac.ru/uploads/banners/paid.webp"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("enabled", "image_path", "payment_status", "seen_at"),
    [
        (False, "banners/paid.webp", ManualPaymentStatus.APPROVED, None),
        (True, None, ManualPaymentStatus.APPROVED, None),
        (True, "banners/paid.webp", ManualPaymentStatus.PENDING, None),
        (
            True,
            "banners/paid.webp",
            ManualPaymentStatus.APPROVED,
            datetime(2026, 5, 27, tzinfo=UTC),
        ),
    ],
)
async def test_pending_payment_success_banner_requires_enabled_paid_unseen_order(
    enabled: bool,
    image_path: str | None,
    payment_status: ManualPaymentStatus,
    seen_at: datetime | None,
) -> None:
    service, repository, _, _ = _orders_service()
    repository.banner_settings.payment_success_banner_enabled = enabled
    repository.banner_settings.payment_success_banner_image_path = image_path
    order = _order(order_id=10, user_id=1)
    order.manual_payment = _approved_payment(order)
    order.manual_payment.status = payment_status
    order.payment_success_banner_seen_at = seen_at
    repository.orders[10] = order

    assert await service.get_pending_payment_success_banner(user_id=1) is None


@pytest.mark.asyncio
async def test_mark_payment_success_banner_seen_marks_own_paid_order() -> None:
    service, repository, session, _ = _orders_service()
    order = _order(order_id=10, user_id=1)
    order.manual_payment = _approved_payment(order)
    repository.orders[10] = order

    result = await service.mark_payment_success_banner_seen(user_id=1, order_id=10)

    assert result.order_id == 10
    assert result.seen_at == repository.orders[10].payment_success_banner_seen_at
    assert session.committed is True


@pytest.mark.asyncio
async def test_mark_payment_success_banner_seen_rejects_other_user_order() -> None:
    service, repository, _, _ = _orders_service()
    order = _order(order_id=10, user_id=2)
    order.manual_payment = _approved_payment(order)
    repository.orders[10] = order

    with pytest.raises(AppError, match="Order not found"):
        await service.mark_payment_success_banner_seen(user_id=1, order_id=10)


def test_orders_require_authentication() -> None:
    with TestClient(create_app()) as client:
        list_response = client.get("/api/v1/orders")
        checkout_response = client.post("/api/v1/orders/checkout", json=_checkout_payload_json())

    assert list_response.status_code == 401
    assert checkout_response.status_code == 401


@pytest.mark.parametrize("delivery_method", [None, "DRONE"])
def test_checkout_rejects_missing_or_invalid_delivery_method(
    delivery_method: str | None,
) -> None:
    app = create_app()
    payload = _checkout_payload_json()
    if delivery_method is None:
        payload.pop("delivery_method")
    else:
        payload["delivery_method"] = delivery_method

    class UnexpectedCheckoutService:
        async def checkout_current_user_cart(self, *_: object) -> None:
            raise AssertionError("Invalid checkout request reached the service")

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.USER)
    app.dependency_overrides[get_orders_service] = UnexpectedCheckoutService
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/orders/checkout", json=payload)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert any(
        detail["loc"][-1] == "delivery_method"
        for detail in response.json()["detail"]
    )


def test_order_admin_routes_reject_regular_user() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.USER)
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/orders/admin")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}


def test_order_admin_routes_allow_seller_to_update_status() -> None:
    app = create_app()

    class FakeOrdersService:
        async def update_order_status(
            self,
            order_id: int,
            payload: OrderStatusUpdate,
            **_: object,
        ) -> dict:
            del order_id, payload
            return _order_response(status_value="PROCESSING")

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_orders_service] = lambda: FakeOrdersService()
    try:
        with TestClient(app) as client:
            response = client.patch(
                "/api/v1/orders/admin/1/status",
                json={"status": "PROCESSING"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "PROCESSING"
    assert response.json()["items"][0]["variant_size_grid"] == "clothing_alpha"


def test_payment_success_banner_customer_routes_require_authentication() -> None:
    with TestClient(create_app()) as client:
        pending_response = client.get("/api/v1/orders/payment-success-banner/pending")
        seen_response = client.post("/api/v1/orders/1/payment-success-banner/seen")

    assert pending_response.status_code == 401
    assert seen_response.status_code == 401


def test_payment_success_banner_settings_routes_require_seller_or_admin() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.USER)
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/settings/admin/payment-success-banner")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}


def test_payment_success_banner_settings_routes_allow_seller() -> None:
    app = create_app()

    class FakeSettingsService:
        async def get_payment_success_banner_settings(self) -> PaymentSuccessBannerSettingsRead:
            return PaymentSuccessBannerSettingsRead(
                enabled=True,
                image_path="banners/paid.webp",
                image_url="/uploads/banners/paid.webp",
                updated_at=None,
            )

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_settings_service] = lambda: FakeSettingsService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/settings/admin/payment-success-banner")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["enabled"] is True
    assert response.json()["image_path"] == "banners/paid.webp"


def _orders_service(
    *,
    product_status: ProductStatus = ProductStatus.ACTIVE,
    product_is_listed: bool = True,
    product_is_returnable: bool = True,
    variant_is_active: bool = True,
    stock_quantity: int = 5,
    cart_items: list[CartItem] | None = None,
    promo_codes_service: FakePromoCodesService | None = None,
    analytics_tracker: FakeAnalyticsTracker | None = None,
    audit_service: FakeAuditService | None = None,
    manual_payments_enabled: bool = True,
    idempotency_service: FakeIdempotencyService | None = None,
) -> tuple[OrdersService, FakeOrdersRepository, DummySession, FakeOrderEventPublisher]:
    session = DummySession()
    events = FakeOrderEventPublisher(session)
    service = OrdersService(
        session,
        event_publisher=events,
        promo_codes_service=promo_codes_service,
        analytics_tracker=analytics_tracker,
        audit_service=audit_service,
        manual_payments_service=FakeManualPaymentsService(enabled=manual_payments_enabled),
        idempotency_service=idempotency_service,
        users_service=FakeUserBlocksService(),
        now_factory=_now,
    )
    repository = FakeOrdersRepository()
    repository.carts[1] = _cart(
        user_id=1,
        product_status=product_status,
        product_is_listed=product_is_listed,
        product_is_returnable=product_is_returnable,
        variant_is_active=variant_is_active,
        stock_quantity=stock_quantity,
        items=cart_items,
    )
    if repository.carts[1].items:
        repository.variants = {
            item.product_variant_id: item.product_variant
            for item in repository.carts[1].items
        }
    else:
        repository.variants[1] = _variant()
    service.repository = repository
    return service, repository, session, events


def _cart(
    *,
    user_id: int,
    product_status: ProductStatus = ProductStatus.ACTIVE,
    product_is_listed: bool = True,
    product_is_returnable: bool = True,
    variant_is_active: bool = True,
    stock_quantity: int = 5,
    items: list[CartItem] | None = None,
) -> Cart:
    cart = Cart(id=user_id, user_id=user_id, created_at=_now(), updated_at=_now())
    if items is not None:
        cart.items = items
        return cart

    product = _product(
        status=product_status,
        is_listed=product_is_listed,
        is_returnable=product_is_returnable,
    )
    variant = _variant(stock_quantity=stock_quantity, is_active=variant_is_active)
    cart.items = [
        CartItem(
            id=1,
            cart_id=cart.id,
            product_id=product.id,
            product_variant_id=variant.id,
            product=product,
            product_variant=variant,
            quantity=2,
            is_selected=True,
            created_at=_now(),
            updated_at=_now(),
        )
    ]
    return cart


def _order(order_id: int, user_id: int, status_value: OrderStatus = OrderStatus.NEW) -> Order:
    return Order(
        id=order_id,
        order_number=f"ORD-{order_id:06d}",
        user_id=user_id,
        status=status_value,
        subtotal_amount=Decimal("59.90"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("59.90"),
        delivery_price=Decimal("0.00"),
        contact_name="Ada Lovelace",
        contact_phone="+10000000000",
        delivery_method=OrderDeliveryMethod.CDEK,
        delivery_address="Main street",
        delivery_comment=None,
        delivered_at=None,
        items=[
            OrderItem(
                id=1,
                order_id=order_id,
                product_id=1,
                product_variant_id=1,
                product_name="Hoodie",
                variant_size="M",
                variant_size_grid=ProductSizeGrid.CLOTHING_ALPHA,
                variant_sku="HOODIE-M-BLK",
                unit_price=Decimal("59.90"),
                quantity=1,
                subtotal=Decimal("59.90"),
                is_returnable=True,
                created_at=_now(),
            )
        ],
        created_at=_now(),
        updated_at=_now(),
    )


def _product(
    status: ProductStatus = ProductStatus.ACTIVE,
    *,
    product_id: int = 1,
    name: str = "Hoodie",
    base_price: Decimal = Decimal("59.90"),
    is_listed: bool = True,
    is_returnable: bool = True,
) -> Product:
    return Product(
        id=product_id,
        name=name,
        brand="ICON STORE",
        slug=name.lower(),
        description="Warm",
        base_price=base_price,
        size_grid=ProductSizeGrid.CLOTHING_ALPHA,
        size_group=ProductSizeGroup.CLOTHING,
        status=status,
        is_listed=is_listed,
        is_returnable=is_returnable,
        category_id=None,
        images=[
            ProductImage(
                id=product_id,
                product_id=product_id,
                file_path="products/hoodie.webp",
                original_filename="hoodie.webp",
                mime_type="image/webp",
                size_bytes=12,
                alt_text="Hoodie",
                position=0,
                is_primary=True,
                created_at=_now(),
            )
        ],
        created_at=_now(),
        updated_at=_now(),
    )


def _variant(
    *,
    variant_id: int = 1,
    product_id: int = 1,
    size: str = "M",
    color: str = "Black",
    sku: str = "HOODIE-M-BLK",
    stock_quantity: int = 5,
    is_active: bool = True,
) -> ProductVariant:
    return ProductVariant(
        id=variant_id,
        product_id=product_id,
        size=size,
        color=color,
        sku=sku,
        stock_quantity=stock_quantity,
        reserved_quantity=0,
        is_active=is_active,
        created_at=_now(),
        updated_at=_now(),
    )


def _checkout_payload() -> OrderCheckoutCreate:
    return OrderCheckoutCreate.model_validate(_checkout_payload_json())


def _checkout_payload_json() -> dict[str, object]:
    return {
        "contact_name": "Ada Lovelace",
        "contact_phone": "+10000000000",
        "delivery_method": "CDEK",
        "delivery_address": "Main street",
        "delivery_comment": "Door code 42",
        "height_cm": "180",
        "weight_kg": "75.5",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("contact_name", ""), ("contact_name", "   "),
        ("contact_phone", ""), ("contact_phone", "   "),
        ("delivery_address", ""), ("delivery_address", "   "),
        ("height_cm", "abc"), ("height_cm", "0"),
        ("height_cm", "-1"), ("height_cm", "301"),
        ("weight_kg", "abc"), ("weight_kg", "0"),
        ("weight_kg", "-1"), ("weight_kg", "1001"),
    ],
)
def test_checkout_schema_rejects_invalid_non_empty_values(field: str, value: str) -> None:
    payload = _checkout_payload_json()
    payload[field] = value
    with pytest.raises(ValidationError):
        OrderCheckoutCreate.model_validate(payload)


@pytest.mark.parametrize(
    ("measurements", "expected_height", "expected_weight"),
    [
        ({}, None, None),
        ({"height_cm": None, "weight_kg": None}, None, None),
        ({"height_cm": "181"}, 181, None),
        ({"weight_kg": "76.5"}, None, Decimal("76.5")),
        ({"height_cm": "181", "weight_kg": "76.5"}, 181, Decimal("76.5")),
    ],
    ids=["missing", "explicit-null", "height-only", "weight-only", "both"],
)
def test_checkout_schema_accepts_optional_measurements(
    measurements: dict[str, object],
    expected_height: int | None,
    expected_weight: Decimal | None,
) -> None:
    payload = _checkout_payload_json()
    payload.pop("height_cm")
    payload.pop("weight_kg")
    payload.update(measurements)

    parsed = OrderCheckoutCreate.model_validate(payload)

    assert parsed.height_cm == expected_height
    assert parsed.weight_kg == expected_weight


def test_checkout_schema_normalizes_optional_values_and_decimal_weight() -> None:
    payload = _checkout_payload_json()
    payload.update(weight_kg="75.25", telegram_username="  @@buyer  ", customer_comment="  ")
    parsed = OrderCheckoutCreate.model_validate(payload)
    assert parsed.weight_kg == Decimal("75.25")
    assert parsed.telegram_username == "buyer"
    assert parsed.customer_comment is None


def test_checkout_schema_extracts_legacy_measurements() -> None:
    payload = _checkout_payload_json()
    payload.pop("height_cm")
    payload.pop("weight_kg")
    payload["delivery_comment"] = "Рост: 181\nВес: 76,5\nПозвонить"
    parsed = OrderCheckoutCreate.model_validate(payload)
    assert parsed.height_cm == 181
    assert parsed.weight_kg == Decimal("76.5")
    assert parsed.delivery_comment == "Позвонить"


def _order_response(status_value: str = "NEW") -> dict[str, object]:
    now = _now().isoformat()
    return {
        "id": 1,
        "order_number": "ORD-000001",
        "user_id": 1,
        "status": status_value,
        "subtotal_amount": "59.90",
        "discount_amount": "0.00",
        "total_amount": "59.90",
        "delivery_price": "0.00",
        "contact_name": "Ada Lovelace",
        "contact_phone": "+10000000000",
        "delivery_method": "CDEK",
        "delivery_address": "Main street",
        "delivery_comment": None,
        "items": [
            {
                "id": 1,
                "product_id": 1,
                "product_variant_id": 1,
                "product_name": "Hoodie",
                "variant_size": "M",
                "variant_size_grid": "clothing_alpha",
                "variant_color": "Black",
                "variant_sku": "HOODIE-M-BLK",
                "unit_price": "59.90",
                "quantity": 1,
                "subtotal": "59.90",
                "product_thumbnail_path": "products/hoodie.webp",
                "product_thumbnail_url": "/uploads/products/hoodie.webp",
                "created_at": now,
            }
        ],
        "created_at": now,
        "updated_at": now,
    }


def _user(role: UserRole) -> User:
    return User(
        id=1,
        telegram_id=42,
        username="seller",
        first_name="Ada",
        last_name=None,
        phone=None,
        role=role,
        is_active=True,
        created_at=_now(),
        updated_at=_now(),
    )


def _approved_payment(order: Order) -> ManualPayment:
    payment = ManualPayment(
        id=order.id,
        order_id=order.id,
        order=order,
        method=ManualPaymentMethod.SBP_PHONE,
        amount=order.total_amount,
        currency=ManualPaymentCurrency.RUB,
        seller_phone_e164="+79999999999",
        seller_phone_display="+7 (999) 999-99-99",
        payment_comment=f"Заказ #{order.id}",
        status=ManualPaymentStatus.APPROVED,
        expires_at=_now(),
        approved_at=_now(),
        created_at=_now(),
        updated_at=_now(),
    )
    order.manual_payment = payment
    return payment


def _now() -> datetime:
    return datetime(2026, 5, 27, tzinfo=UTC)
