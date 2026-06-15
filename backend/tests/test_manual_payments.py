from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.common.deps import get_current_user
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import (
    ManualPayment,
    ManualPaymentCurrency,
    ManualPaymentMethod,
    ManualPaymentStatus,
    Order,
    OrderDeliveryMethod,
    OrderItem,
    OrderStatus,
    ProductVariant,
    SellerPaymentSettings,
    User,
    UserRole,
)
from app.events.names import (
    MANUAL_PAYMENT_APPROVED,
    MANUAL_PAYMENT_EXPIRED,
    MANUAL_PAYMENT_REJECTED,
    MANUAL_PAYMENT_SUBMITTED,
)
from app.main import create_app
from app.modules.manual_payments.phone import normalize_russian_phone
from app.modules.manual_payments.router import get_manual_payments_service
from app.modules.manual_payments.schemas import SellerPaymentSettingsUpdate
from app.modules.manual_payments.service import ManualPaymentEventPublisher, ManualPaymentsService
from app.modules.telegram.service import TelegramDeliveryError

NOW = datetime(2026, 6, 14, 12, 0, tzinfo=UTC)


class DummySession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.rollback_count = 0
        self.on_commit: Callable[[], None] | None = None

    async def commit(self) -> None:
        self.commit_count += 1
        if self.on_commit is not None:
            self.on_commit()

    async def rollback(self) -> None:
        self.rollback_count += 1

    async def refresh(self, _: object) -> None:
        return None


class FakeRepository:
    def __init__(self) -> None:
        self.settings: SellerPaymentSettings | None = None
        self.payments: dict[int, ManualPayment] = {}
        self.variants: dict[int, ProductVariant] = {}
        self.users: dict[int, User] = {}
        self.next_payment_id = 1
        self.populate_existing_ids: list[int] = []

    async def get_settings(self) -> SellerPaymentSettings | None:
        return self.settings

    async def get_for_order_owner(
        self,
        *,
        order_id: int,
        user_id: int,
        for_update: bool = False,
    ) -> ManualPayment | None:
        del for_update
        payment = next(
            (item for item in self.payments.values() if item.order_id == order_id),
            None,
        )
        if payment is None or payment.order.user_id != user_id:
            return None
        return payment

    async def get_by_id(
        self,
        payment_id: int,
        *,
        for_update: bool = False,
        populate_existing: bool = False,
    ) -> ManualPayment | None:
        del for_update
        payment = self.payments.get(payment_id)
        if payment is not None and populate_existing:
            self.populate_existing_ids.append(payment_id)
            payment.updated_at = NOW + timedelta(seconds=len(self.populate_existing_ids))
        return payment

    async def list_all(self, **_: object) -> list[ManualPayment]:
        return list(self.payments.values())

    async def list_due_ids(self, *, now: datetime, limit: int) -> list[int]:
        return [
            payment.id
            for payment in list(self.payments.values())[:limit]
            if payment.status in {ManualPaymentStatus.PENDING, ManualPaymentStatus.SUBMITTED}
            and payment.expires_at <= now
        ]

    async def lock_variants_by_ids(
        self,
        variant_ids,
    ) -> dict[int, ProductVariant]:
        return {variant_id: self.variants[variant_id] for variant_id in variant_ids}

    async def get_user_by_telegram_id(self, telegram_id: int) -> User | None:
        return self.users.get(telegram_id)

    def add(self, instance: ManualPayment | SellerPaymentSettings) -> None:
        if isinstance(instance, SellerPaymentSettings):
            instance.created_at = NOW
            instance.updated_at = NOW
            self.settings = instance
            return
        instance.id = self.next_payment_id
        self.next_payment_id += 1
        instance.created_at = NOW
        instance.updated_at = NOW
        self.payments[instance.id] = instance


class FakeEventPublisher:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[tuple[str, dict[str, object]]] = []

    async def emit(self, name: str, payload: dict[str, object]) -> None:
        if self.fail:
            raise RuntimeError("Telegram unavailable")
        self.events.append((name, payload))


class FakeTelegramService:
    def __init__(
        self,
        *,
        bot_token: str | None = "seller-bot-token",
        seller_chat_id: str | None = "-100",
        fail: bool = False,
        message_id: int | None = None,
        fail_edit: bool = False,
    ) -> None:
        self.bot_token = bot_token
        self.seller_chat_id = seller_chat_id
        self.fail = fail
        self.message_id = message_id
        self.fail_edit = fail_edit
        self.messages: list[tuple[str, str, dict[str, object] | None]] = []
        self.edits: list[tuple[str, int, str, dict[str, object] | None]] = []

    async def send_message(
        self,
        chat_id: str,
        message: str,
        *,
        reply_markup: dict[str, object] | None = None,
    ) -> int | None:
        if self.fail:
            raise RuntimeError("Telegram unavailable")
        self.messages.append((chat_id, message, reply_markup))
        return self.message_id

    async def edit_message_text(
        self,
        chat_id: str,
        message_id: int,
        message: str,
        *,
        reply_markup: dict[str, object] | None = None,
    ) -> None:
        if self.fail_edit:
            raise TelegramDeliveryError("Telegram edit failed")
        self.edits.append((chat_id, message_id, message, reply_markup))


class FakeAuditService:
    def __init__(self) -> None:
        self.logs: list[dict[str, object]] = []

    async def record_action(self, **payload: object) -> None:
        self.logs.append(payload)


class FakeStorage:
    def __init__(self) -> None:
        self.saved: list[str] = []
        self.deleted: list[str] = []

    def save_bytes(self, _: bytes, *, folder: str, suffix: str) -> str:
        path = f"{folder}/receipt{suffix}"
        self.saved.append(path)
        return path

    def delete(self, path: str) -> None:
        self.deleted.append(path)


class FakeUploadsService:
    def __init__(self, storage: FakeStorage, *, error: AppError | None = None) -> None:
        self.storage = storage
        self.error = error

    async def validate_and_read_image(self, _: object) -> SimpleNamespace:
        if self.error is not None:
            raise self.error
        return SimpleNamespace(content=b"image", extension=".png")


@pytest.mark.parametrize("value", ["+7 (999) 999-99-99", "+79999999999", "89999999999"])
def test_normalize_russian_phone(value: str) -> None:
    assert normalize_russian_phone(value) == (
        "+79999999999",
        "+7 (999) 999-99-99",
    )


def test_reject_invalid_russian_phone() -> None:
    with pytest.raises(ValueError):
        normalize_russian_phone("+1 555 0100")


@pytest.mark.asyncio
async def test_get_empty_and_save_payment_settings() -> None:
    service, repository, session, _, audit, _ = _service()

    empty = await service.get_settings()
    saved = await service.update_settings(
        SellerPaymentSettingsUpdate(
            is_manual_sbp_enabled=True,
            seller_phone="8 999 999-99-99",
            seller_bank_name=" Sberbank ",
            seller_recipient_name=" Ivan I. ",
        ),
        actor_user_id=9,
    )

    assert empty.is_manual_sbp_enabled is False
    assert saved.seller_phone_e164 == "+79999999999"
    assert saved.seller_phone_display == "+7 (999) 999-99-99"
    assert saved.seller_bank_name == "Sberbank"
    assert repository.settings is not None
    assert session.commit_count == 1
    assert audit.logs[0]["action"] == "manual_payment.settings_updated"


@pytest.mark.asyncio
async def test_invalid_or_missing_phone_cannot_enable_settings() -> None:
    service, _, _, _, _, _ = _service()

    with pytest.raises(AppError, match="Payment phone is required"):
        await service.update_settings(
            SellerPaymentSettingsUpdate(is_manual_sbp_enabled=True),
            actor_user_id=1,
        )
    with pytest.raises(AppError, match="Invalid Russian payment phone"):
        await service.update_settings(
            SellerPaymentSettingsUpdate(
                is_manual_sbp_enabled=True,
                seller_phone="123",
            ),
            actor_user_id=1,
        )


@pytest.mark.asyncio
async def test_checkout_payment_snapshots_settings_and_expires_in_30_minutes() -> None:
    service, repository, _, _, _, _ = _service(with_settings=True)
    order, variant = _order_and_variant()
    repository.variants[variant.id] = variant

    payment = await service.create_for_checkout(order)
    repository.settings.seller_phone_e164 = "+78888888888"

    assert payment.amount == order.total_amount
    assert payment.status == ManualPaymentStatus.PENDING
    assert payment.expires_at == NOW + timedelta(minutes=30)
    assert payment.seller_phone_e164 == "+79999999999"
    assert payment.payment_comment == "Заказ #10"


@pytest.mark.asyncio
async def test_submit_is_owner_only_and_idempotent() -> None:
    service, repository, session, events, _, _ = _service(with_payment=True)

    with pytest.raises(AppError, match="Payment not found"):
        await service.submit(order_id=10, user_id=2)

    first = await service.submit(order_id=10, user_id=1)
    second = await service.submit(order_id=10, user_id=1)

    assert first.status == ManualPaymentStatus.SUBMITTED
    assert second.submitted_at == first.submitted_at
    assert session.commit_count == 1
    assert repository.populate_existing_ids == [1]
    assert [event[0] for event in events.events] == [MANUAL_PAYMENT_SUBMITTED]


@pytest.mark.asyncio
async def test_payment_read_and_receipt_upload_are_owner_only() -> None:
    service, _, _, _, _, _ = _service(with_payment=True)

    with pytest.raises(AppError, match="Payment not found"):
        await service.get_for_customer(order_id=10, user_id=2)
    with pytest.raises(AppError, match="Payment not found"):
        await service.upload_receipt(order_id=10, user_id=2, file=object())


@pytest.mark.asyncio
async def test_approve_moves_order_to_processing_without_releasing_stock() -> None:
    service, repository, _, events, audit, _ = _service(with_payment=True)
    payment = repository.payments[1]
    variant = repository.variants[1]

    result = await service.approve(1, actor_user_id=9)

    assert result.status == ManualPaymentStatus.APPROVED
    assert result.order_status == OrderStatus.PROCESSING
    assert payment.order.status == OrderStatus.PROCESSING
    assert variant.stock_quantity == 3
    assert payment.stock_released_at is None
    assert events.events[0][0] == MANUAL_PAYMENT_APPROVED
    assert audit.logs[0]["actor_user_id"] == 9


@pytest.mark.asyncio
async def test_reject_releases_stock_once_and_is_idempotent() -> None:
    service, repository, session, events, _, _ = _service(with_payment=True)
    payment = repository.payments[1]
    variant = repository.variants[1]

    first = await service.reject(1, actor_user_id=9, reject_reason="No payment")
    second = await service.reject(1, actor_user_id=9, reject_reason="No payment")

    assert first.status == ManualPaymentStatus.REJECTED
    assert second.status == ManualPaymentStatus.REJECTED
    assert payment.order.status == OrderStatus.CANCELLED
    assert variant.stock_quantity == 5
    assert payment.stock_released_at == NOW
    assert session.commit_count == 1
    assert repository.populate_existing_ids == [1]
    assert [event[0] for event in events.events] == [MANUAL_PAYMENT_REJECTED]


@pytest.mark.asyncio
async def test_terminal_payment_transitions_are_rejected() -> None:
    service, repository, _, _, _, _ = _service(with_payment=True)
    await service.reject(1, actor_user_id=9)

    with pytest.raises(AppError, match="cannot be approved"):
        await service.approve(1, actor_user_id=9)

    repository.payments[1].status = ManualPaymentStatus.APPROVED
    with pytest.raises(AppError, match="cannot be rejected"):
        await service.reject(1, actor_user_id=9)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "initial_status",
    [ManualPaymentStatus.PENDING, ManualPaymentStatus.SUBMITTED],
)
async def test_expiration_releases_stock_once_and_skips_approved_payment(
    initial_status: ManualPaymentStatus,
) -> None:
    service, repository, session, events, _, _ = _service(
        with_payment=True,
        payment_expires_at=NOW - timedelta(seconds=1),
    )
    payment = repository.payments[1]
    payment.status = initial_status
    variant = repository.variants[1]

    assert await service.expire_due_payment(1) is True
    assert await service.expire_due_payment(1) is False
    assert payment.status == ManualPaymentStatus.EXPIRED
    assert payment.order.status == OrderStatus.CANCELLED
    assert variant.stock_quantity == 5
    assert session.commit_count == 1
    assert repository.populate_existing_ids == [1]
    assert [event[0] for event in events.events] == [MANUAL_PAYMENT_EXPIRED]

    payment.status = ManualPaymentStatus.APPROVED
    assert await service.expire_due_payment(1) is False


@pytest.mark.asyncio
async def test_submit_after_deadline_expires_payment() -> None:
    service, repository, _, events, _, _ = _service(
        with_payment=True,
        payment_expires_at=NOW - timedelta(seconds=1),
    )

    with pytest.raises(AppError, match="Payment has expired"):
        await service.submit(order_id=10, user_id=1)

    assert repository.payments[1].status == ManualPaymentStatus.EXPIRED
    assert repository.variants[1].stock_quantity == 5
    assert events.events[0][0] == MANUAL_PAYMENT_EXPIRED


@pytest.mark.asyncio
async def test_receipt_upload_replaces_old_file_without_submitting() -> None:
    service, repository, _, _, _, storage = _service(with_payment=True)
    payment = repository.payments[1]
    payment.receipt_image_path = "payment_receipts/old.png"

    result = await service.upload_receipt(order_id=10, user_id=1, file=object())

    assert result.status == ManualPaymentStatus.PENDING
    assert result.receipt_image_path == "payment_receipts/receipt.png"
    assert repository.populate_existing_ids == [1]
    assert storage.deleted == ["payment_receipts/old.png"]


@pytest.mark.asyncio
async def test_invalid_receipt_is_rejected() -> None:
    service, _, _, _, _, _ = _service(
        with_payment=True,
        upload_error=AppError("Invalid image content"),
    )

    with pytest.raises(AppError, match="Invalid image content"):
        await service.upload_receipt(order_id=10, user_id=1, file=object())


@pytest.mark.asyncio
async def test_notification_failure_does_not_rollback_payment_state() -> None:
    service, repository, session, _, _, _ = _service(with_payment=True, event_failure=True)

    result = await service.submit(order_id=10, user_id=1)

    assert result.status == ManualPaymentStatus.SUBMITTED
    assert repository.payments[1].status == ManualPaymentStatus.SUBMITTED
    assert session.commit_count == 1
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_submit_attempts_configured_seller_bot_notification() -> None:
    service, _, _, _, _, _ = _service(with_payment=True)
    telegram = FakeTelegramService()
    service.event_publisher = ManualPaymentEventPublisher(
        service.session,
        telegram_service=telegram,
        customer_publisher=FakeEventPublisher(),
    )

    result = await service.submit(order_id=10, user_id=1)

    assert result.status == ManualPaymentStatus.SUBMITTED
    assert result.delivery_method == OrderDeliveryMethod.CDEK
    assert len(telegram.messages) == 1
    assert "ORD-00000010" in telegram.messages[0][1]
    assert "Способ доставки: СДЭК" in telegram.messages[0][1]


@pytest.mark.asyncio
async def test_seller_bot_send_failure_does_not_rollback_submit() -> None:
    service, repository, session, _, _, _ = _service(with_payment=True)
    service.event_publisher = ManualPaymentEventPublisher(
        service.session,
        telegram_service=FakeTelegramService(fail=True),
        customer_publisher=FakeEventPublisher(),
    )

    result = await service.submit(order_id=10, user_id=1)

    assert result.status == ManualPaymentStatus.SUBMITTED
    assert repository.payments[1].status == ManualPaymentStatus.SUBMITTED
    assert session.commit_count == 1
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_missing_seller_bot_configuration_does_not_break_submit() -> None:
    service, repository, session, _, _, _ = _service(with_payment=True)
    telegram = FakeTelegramService(bot_token=None, seller_chat_id=None)
    service.event_publisher = ManualPaymentEventPublisher(
        service.session,
        telegram_service=telegram,
        customer_publisher=FakeEventPublisher(),
    )

    result = await service.submit(order_id=10, user_id=1)

    assert result.status == ManualPaymentStatus.SUBMITTED
    assert repository.payments[1].status == ManualPaymentStatus.SUBMITTED
    assert telegram.messages == []
    assert session.rollback_count == 0


@pytest.mark.asyncio
async def test_submitted_event_sends_seller_group_review_buttons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    telegram = FakeTelegramService()
    publisher = ManualPaymentEventPublisher(
        DummySession(),
        telegram_service=telegram,
        customer_publisher=FakeEventPublisher(),
    )

    await publisher.emit(
        MANUAL_PAYMENT_SUBMITTED,
        {
            "payment_id": 17,
            "order_id": 10,
            "order_number": "ORD-10",
            "user_id": 1,
            "customer_username": "customer",
            "customer_phone": "+79990000000",
            "delivery_method": "CDEK",
            "delivery_method_label": "СДЭК",
            "amount": "180.00",
            "payment_comment": "Заказ #10",
            "expires_at": (NOW + timedelta(minutes=30)).isoformat(),
            "has_receipt": True,
        },
    )

    assert telegram.messages[0][0] == "-100"
    assert "ORD-10" in telegram.messages[0][1]
    assert "Способ доставки: СДЭК" in telegram.messages[0][1]
    keyboard = telegram.messages[0][2]
    assert keyboard is not None
    buttons = keyboard["inline_keyboard"][0]
    assert buttons[0]["callback_data"] == "manual_payment:approve:17"
    assert buttons[1]["callback_data"] == "manual_payment:reject:17"
    assert buttons[0]["text"] == "✅ Подтвердить"
    assert buttons[1]["text"] == "❌ Отклонить"


@pytest.mark.asyncio
async def test_submitted_event_stores_seller_group_message_reference() -> None:
    service, repository, _, _, _, _ = _service(with_payment=True)
    telegram = FakeTelegramService(message_id=701)
    publisher = ManualPaymentEventPublisher(
        service.session,
        telegram_service=telegram,
        customer_publisher=FakeEventPublisher(),
    )
    publisher.repository = repository

    await publisher.emit(MANUAL_PAYMENT_SUBMITTED, service._event_payload(repository.payments[1]))

    payment = repository.payments[1]
    assert payment.seller_telegram_chat_id == -100
    assert payment.seller_telegram_message_id == 701


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "expected_text"),
    [
        ("approve", "✅ Оплата подтверждена"),
        ("reject", "❌ Оплата отклонена"),
    ],
)
async def test_seller_panel_decision_edits_original_group_message(
    action: str,
    expected_text: str,
) -> None:
    service, repository, _, _, audit, _ = _service(with_payment=True)
    payment = repository.payments[1]
    payment.seller_telegram_chat_id = -100
    payment.seller_telegram_message_id = 702
    telegram = FakeTelegramService()
    service.event_publisher = ManualPaymentEventPublisher(
        service.session,
        telegram_service=telegram,
        customer_publisher=FakeEventPublisher(),
    )
    service.audit_service = audit

    if action == "approve":
        await service.approve(1, actor_user_id=9)
    else:
        await service.reject(1, actor_user_id=9, reject_reason="Неверная сумма")

    assert telegram.edits
    assert expected_text in telegram.edits[0][2]
    assert telegram.edits[0][3] == {"inline_keyboard": []}


@pytest.mark.asyncio
async def test_group_message_edit_failure_sends_follow_up_without_rollback() -> None:
    service, repository, session, _, _, _ = _service(with_payment=True)
    payment = repository.payments[1]
    payment.seller_telegram_chat_id = -100
    payment.seller_telegram_message_id = 703
    telegram = FakeTelegramService(fail_edit=True)
    service.event_publisher = ManualPaymentEventPublisher(
        service.session,
        telegram_service=telegram,
        customer_publisher=FakeEventPublisher(),
    )

    result = await service.approve(1, actor_user_id=9)

    assert result.status == ManualPaymentStatus.APPROVED
    assert telegram.messages
    assert "✅ Оплата подтверждена" in telegram.messages[-1][1]
    assert session.rollback_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "is_active", "expected_user_id"),
    [
        (UserRole.SELLER, True, 7),
        (UserRole.ADMIN, True, 7),
        (UserRole.USER, True, None),
        (UserRole.SELLER, False, None),
    ],
)
async def test_bot_payment_actor_must_be_active_seller_or_admin(
    role: UserRole,
    is_active: bool,
    expected_user_id: int | None,
) -> None:
    service, repository, _, _, _, _ = _service()
    repository.users[700] = User(
        id=7,
        telegram_id=700,
        username="seller",
        first_name="Seller",
        last_name=None,
        role=role,
        is_active=is_active,
        created_at=NOW,
        updated_at=NOW,
    )

    assert await service.actor_user_id_for_telegram(700) == expected_user_id


def test_manual_payment_routes_require_authentication() -> None:
    with TestClient(create_app()) as client:
        customer_response = client.get("/api/v1/orders/1/payment")
        seller_response = client.get("/api/v1/seller/payments")
        settings_response = client.get("/api/v1/seller/settings/payment")

    assert customer_response.status_code == 401
    assert seller_response.status_code == 401
    assert settings_response.status_code == 401


def test_seller_payment_routes_reject_regular_user() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _user()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/seller/payments")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_manual_payment_mutation_routes_return_fresh_success_responses() -> None:
    service, _, _, _, _, _ = _service(with_payment=True)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_manual_payments_service] = lambda: service
    try:
        with TestClient(app) as client:
            receipt_response = client.post(
                "/api/v1/orders/10/payment/receipt",
                files={"file": ("receipt.png", b"image", "image/png")},
            )
            submit_response = client.post("/api/v1/orders/10/payment/submit")
            approve_response = client.post("/api/v1/seller/payments/1/approve")
    finally:
        app.dependency_overrides.clear()

    assert receipt_response.status_code == 200
    assert receipt_response.json()["receipt_image_path"] == "payment_receipts/receipt.png"
    assert submit_response.status_code == 200
    assert submit_response.json()["status"] == "SUBMITTED"
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "APPROVED"
    assert approve_response.json()["order_status"] == "PROCESSING"


def test_manual_payment_reject_route_returns_fresh_success_response() -> None:
    service, _, _, _, _, _ = _service(with_payment=True)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_manual_payments_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/seller/payments/1/reject",
                json={"reject_reason": "No payment"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert response.json()["order_status"] == "CANCELLED"


def _service(
    *,
    with_settings: bool = False,
    with_payment: bool = False,
    payment_expires_at: datetime | None = None,
    upload_error: AppError | None = None,
    event_failure: bool = False,
) -> tuple[
    ManualPaymentsService,
    FakeRepository,
    DummySession,
    FakeEventPublisher,
    FakeAuditService,
    FakeStorage,
]:
    session = DummySession()
    events = FakeEventPublisher(fail=event_failure)
    audit = FakeAuditService()
    storage = FakeStorage()
    uploads = FakeUploadsService(storage, error=upload_error)
    service = ManualPaymentsService(
        session,
        event_publisher=events,
        audit_service=audit,
        uploads_service=uploads,
        storage=storage,
        now_factory=lambda: NOW,
    )
    repository = FakeRepository()
    service.repository = repository

    def expire_payment_updated_at() -> None:
        for payment in repository.payments.values():
            payment.__dict__.pop("updated_at", None)

    session.on_commit = expire_payment_updated_at
    if with_settings or with_payment:
        repository.settings = _settings()
    if with_payment:
        order, variant = _order_and_variant()
        payment = _payment(
            order,
            expires_at=payment_expires_at or NOW + timedelta(minutes=30),
        )
        repository.payments[payment.id] = payment
        repository.variants[variant.id] = variant
    return service, repository, session, events, audit, storage


def _settings() -> SellerPaymentSettings:
    return SellerPaymentSettings(
        id=1,
        seller_phone_e164="+79999999999",
        seller_phone_display="+7 (999) 999-99-99",
        seller_bank_name="Sberbank",
        seller_recipient_name="Ivan I.",
        is_manual_sbp_enabled=True,
        created_at=NOW,
        updated_at=NOW,
    )


def _user(role: UserRole = UserRole.USER) -> User:
    return User(
        id=1,
        telegram_id=100,
        username="customer",
        first_name="Ivan",
        last_name=None,
        role=role,
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
    )


def _order_and_variant() -> tuple[Order, ProductVariant]:
    user = User(
        id=1,
        telegram_id=100,
        username="customer",
        first_name="Ivan",
        last_name=None,
        role=UserRole.USER,
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
    )
    item = OrderItem(
        id=1,
        order_id=10,
        product_id=1,
        product_variant_id=1,
        product_name="Hoodie",
        variant_size="M",
        variant_sku="HOODIE-M",
        unit_price=Decimal("100.00"),
        quantity=2,
        subtotal=Decimal("200.00"),
        created_at=NOW,
    )
    order = Order(
        id=10,
        order_number="ORD-00000010",
        user_id=1,
        user=user,
        status=OrderStatus.NEW,
        subtotal_amount=Decimal("200.00"),
        discount_amount=Decimal("20.00"),
        total_amount=Decimal("180.00"),
        contact_name="Ivan Ivanov",
        contact_phone="+79990000000",
        delivery_method=OrderDeliveryMethod.CDEK,
        delivery_address="Moscow",
        delivery_comment=None,
        items=[item],
        created_at=NOW,
        updated_at=NOW,
    )
    variant = ProductVariant(
        id=1,
        product_id=1,
        size="M",
        sku="HOODIE-M",
        stock_quantity=3,
        reserved_quantity=0,
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
    )
    return order, variant


def _payment(order: Order, *, expires_at: datetime) -> ManualPayment:
    payment = ManualPayment(
        id=1,
        order_id=order.id,
        order=order,
        method=ManualPaymentMethod.SBP_PHONE,
        amount=order.total_amount,
        currency=ManualPaymentCurrency.RUB,
        seller_phone_e164="+79999999999",
        seller_phone_display="+7 (999) 999-99-99",
        seller_bank_name="Sberbank",
        seller_recipient_name="Ivan I.",
        payment_comment="Заказ #10",
        status=ManualPaymentStatus.PENDING,
        expires_at=expires_at,
        created_at=NOW,
        updated_at=NOW,
    )
    order.manual_payment = payment
    return payment
