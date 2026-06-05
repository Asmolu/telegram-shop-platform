from datetime import UTC, datetime

import pytest

from app.core.config import settings
from app.db.models import (
    CustomerServiceNotificationDelivery,
    CustomerServiceNotificationDeliveryStatus,
    CustomerTelegramSubscription,
    OrderStatus,
)
from app.events.names import (
    ORDER_CANCELLED_CUSTOMER,
    ORDER_CREATED_CUSTOMER,
    ORDER_DELIVERED_CUSTOMER,
    ORDER_PROCESSING_CUSTOMER,
    ORDER_SHIPPED_CUSTOMER,
    ORDER_STATUS_CHANGED_CUSTOMER,
)
from app.modules.customer_notifications.service import (
    CustomerServiceNotificationDeliveryService,
    CustomerTelegramSender,
)
from app.modules.telegram.service import TelegramDeliveryError


class DummySession:
    def __init__(self) -> None:
        self.commits = 0
        self.rolled_back = False

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeDeliveryRepository:
    def __init__(self, subscription: CustomerTelegramSubscription | None = None) -> None:
        self.subscription = subscription
        self.deliveries: list[CustomerServiceNotificationDelivery] = []
        self.next_id = 1

    async def get_by_user_id(self, user_id: int) -> CustomerTelegramSubscription | None:
        if self.subscription is None or self.subscription.user_id != user_id:
            return None
        return self.subscription

    def add_delivery(self, delivery: CustomerServiceNotificationDelivery) -> None:
        delivery.id = self.next_id
        self.next_id += 1
        delivery.created_at = _now()
        delivery.updated_at = _now()
        self.deliveries.append(delivery)


class FakeCustomerSender:
    def __init__(self, error: TelegramDeliveryError | None = None) -> None:
        self.error = error
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, message: str) -> int | None:
        self.messages.append((chat_id, message))
        if self.error is not None:
            raise self.error
        return 123


@pytest.mark.asyncio
async def test_eligible_customer_receives_order_created_service_notification() -> None:
    service, repository, sender, session = _delivery_service(subscription=_subscription())

    delivery = await service.notify_order_created(_order_created_payload())

    assert delivery is not None
    assert delivery.event_name == ORDER_CREATED_CUSTOMER
    assert delivery.status == CustomerServiceNotificationDeliveryStatus.SENT
    assert delivery.telegram_message_id == 123
    assert delivery.sent_at == _now()
    assert sender.messages == [(100, "Заказ создан\n\nЗаказ ORD-00000001 создан. Сумма: 99.80.")]
    assert repository.deliveries == [delivery]
    assert session.rolled_back is False


@pytest.mark.asyncio
async def test_order_created_skips_when_subscription_is_missing() -> None:
    service, _, sender, _ = _delivery_service(subscription=None)

    delivery = await service.notify_order_created(_order_created_payload())

    assert delivery is not None
    assert delivery.status == CustomerServiceNotificationDeliveryStatus.SKIPPED
    assert delivery.error_code == "subscription_missing"
    assert sender.messages == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("subscription_kwargs", "expected_error_code"),
    [
        ({"has_chat": False}, "chat_unavailable"),
        ({"service_opt_in": False}, "service_opt_out"),
        ({"blocked_at": "now"}, "subscription_blocked"),
    ],
)
async def test_order_created_skips_ineligible_subscription_states(
    subscription_kwargs: dict[str, object],
    expected_error_code: str,
) -> None:
    if subscription_kwargs.get("blocked_at") == "now":
        subscription_kwargs["blocked_at"] = _now()
    subscription = _subscription(**subscription_kwargs)
    service, _, sender, _ = _delivery_service(subscription=subscription)

    delivery = await service.notify_order_created(_order_created_payload())

    assert delivery is not None
    assert delivery.status == CustomerServiceNotificationDeliveryStatus.SKIPPED
    assert delivery.error_code == expected_error_code
    assert sender.messages == []


@pytest.mark.asyncio
async def test_telegram_failure_does_not_raise_or_rollback_delivery_flow() -> None:
    service, _, sender, session = _delivery_service(
        subscription=_subscription(),
        sender_error=TelegramDeliveryError("Telegram API request failed"),
    )

    delivery = await service.notify_order_created(_order_created_payload())

    assert delivery is not None
    assert delivery.status == CustomerServiceNotificationDeliveryStatus.FAILED
    assert delivery.error_code == "telegram_error"
    assert sender.messages
    assert session.rolled_back is False


@pytest.mark.asyncio
async def test_telegram_403_marks_subscription_blocked_and_unavailable() -> None:
    subscription = _subscription()
    service, _, _, _ = _delivery_service(
        subscription=subscription,
        sender_error=TelegramDeliveryError(
            "Forbidden: bot was blocked by the user",
            error_code=403,
            status_code=403,
        ),
    )

    delivery = await service.notify_order_created(_order_created_payload())

    assert delivery is not None
    assert delivery.status == CustomerServiceNotificationDeliveryStatus.BLOCKED
    assert delivery.error_code == "blocked"
    assert subscription.blocked_at == _now()
    assert subscription.has_chat is False
    assert subscription.last_delivery_error == "Forbidden: bot was blocked by the user"


@pytest.mark.asyncio
async def test_telegram_429_records_sanitized_rate_limit_metadata() -> None:
    service, _, _, _ = _delivery_service(
        subscription=_subscription(),
        sender_error=TelegramDeliveryError(
            "Too Many Requests: retry after 12",
            error_code=429,
            status_code=429,
            retry_after_seconds=12,
        ),
    )

    delivery = await service.notify_order_created(_order_created_payload())

    assert delivery is not None
    assert delivery.status == CustomerServiceNotificationDeliveryStatus.FAILED
    assert delivery.error_code == "rate_limited"
    assert delivery.retry_after_seconds == 12
    assert "retry_after_seconds=12" in (delivery.error_message or "")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("new_status", "expected_event_name", "expected_message"),
    [
        (
            OrderStatus.PROCESSING.value,
            ORDER_PROCESSING_CUSTOMER,
            "Заказ принят в обработку\n\nЗаказ ORD-00000001 принят в обработку.",
        ),
        (
            OrderStatus.SHIPPED.value,
            ORDER_SHIPPED_CUSTOMER,
            "Заказ отправлен\n\nЗаказ ORD-00000001 отправлен.",
        ),
        (
            OrderStatus.DELIVERED.value,
            ORDER_DELIVERED_CUSTOMER,
            "Заказ доставлен\n\nЗаказ ORD-00000001 доставлен.",
        ),
        (
            OrderStatus.CANCELLED.value,
            ORDER_CANCELLED_CUSTOMER,
            "Заказ отменён\n\nЗаказ ORD-00000001 отменён.",
        ),
        (
            OrderStatus.NEW.value,
            ORDER_STATUS_CHANGED_CUSTOMER,
            "Статус заказа изменён\n\nСтатус заказа ORD-00000001: NEW.",
        ),
    ],
)
async def test_order_status_update_creates_customer_status_notification_when_eligible(
    new_status: str,
    expected_event_name: str,
    expected_message: str,
) -> None:
    service, _, sender, _ = _delivery_service(subscription=_subscription())

    delivery = await service.notify_order_status_changed(
        {
            "order_id": 1,
            "order_number": "ORD-00000001",
            "user_id": 1,
            "previous_status": OrderStatus.PROCESSING.value,
            "new_status": new_status,
        }
    )

    assert delivery is not None
    assert delivery.event_name == expected_event_name
    assert delivery.status == CustomerServiceNotificationDeliveryStatus.SENT
    assert sender.messages == [(100, expected_message)]


def test_customer_telegram_sender_uses_customer_bot_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_customer_bot_token", "customer-token")
    monkeypatch.setattr(settings, "telegram_bot_token", "seller-token")
    monkeypatch.setattr(settings, "telegram_webapp_bot_token", "webapp-token")

    sender = CustomerTelegramSender()

    assert sender.telegram_service.bot_token == "customer-token"


def _delivery_service(
    *,
    subscription: CustomerTelegramSubscription | None,
    sender_error: TelegramDeliveryError | None = None,
) -> tuple[
    CustomerServiceNotificationDeliveryService,
    FakeDeliveryRepository,
    FakeCustomerSender,
    DummySession,
]:
    session = DummySession()
    repository = FakeDeliveryRepository(subscription)
    sender = FakeCustomerSender(error=sender_error)
    service = CustomerServiceNotificationDeliveryService(
        session,
        repository=repository,
        sender=sender,
        now_factory=_now,
    )
    return service, repository, sender, session


def _subscription(
    *,
    has_chat: bool = True,
    service_opt_in: bool = True,
    blocked_at: datetime | None = None,
) -> CustomerTelegramSubscription:
    return CustomerTelegramSubscription(
        id=7,
        user_id=1,
        telegram_user_id=42,
        telegram_chat_id=100,
        telegram_username="buyer",
        telegram_first_name="Ada",
        telegram_last_name=None,
        chat_type="private",
        has_chat=has_chat,
        service_opt_in=service_opt_in,
        marketing_opt_in=True,
        blocked_at=blocked_at,
        created_at=_now(),
        updated_at=_now(),
    )


def _order_created_payload() -> dict[str, object]:
    return {
        "order_id": 1,
        "order_number": "ORD-00000001",
        "user_id": 1,
        "subtotal_amount": "119.80",
        "discount_amount": "20.00",
        "total_amount": "99.80",
        "promo_code_id": 7,
        "promo_code": "SAVE10",
    }


def _now() -> datetime:
    return datetime(2026, 6, 5, 12, 0, tzinfo=UTC)
