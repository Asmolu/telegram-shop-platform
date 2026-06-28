from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.common.deps import get_current_user
from app.core.config import settings
from app.db.models import (
    CustomerServiceNotificationDeliveryStatus,
    CustomerTelegramSubscription,
    NotificationChannel,
    User,
    UserRole,
)
from app.main import create_app
from app.modules.auth.service import AuthService
from app.modules.customer_notifications.router import get_customer_notifications_service
from app.modules.customer_notifications.schemas import (
    CustomerBotWebhookResponse,
    CustomerServiceNotificationDeliveryList,
    CustomerSubscriptionList,
    CustomerSubscriptionMe,
    CustomerSubscriptionStartLink,
    CustomerSubscriptionUpdate,
    CustomerWriteAccessRequest,
)
from app.modules.customer_notifications.service import CustomerNotificationsService
from app.modules.telegram.router import get_customer_bot_webhook_service
from app.modules.telegram.schemas import TelegramUpdate


class DummySession:
    def __init__(self) -> None:
        self.commits = 0
        self.rolled_back = False
        self.flushed = False

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rolled_back = True

    async def refresh(self, _: object) -> None:
        return None

    async def flush(self) -> None:
        self.flushed = True


class FakeTelegramService:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, dict[str, object] | None]] = []
        self.answered_callbacks: list[tuple[str, str | None]] = []

    async def send_message(
        self,
        chat_id: str,
        message: str,
        *,
        reply_markup: dict[str, object] | None = None,
    ) -> None:
        self.messages.append((chat_id, message, reply_markup))

    async def answer_callback_query(
        self,
        callback_query_id: str,
        *,
        text: str | None = None,
    ) -> None:
        self.answered_callbacks.append((callback_query_id, text))


class FakeAuditService:
    def __init__(self) -> None:
        self.actions: list[dict[str, object]] = []

    async def record_action(self, **kwargs: object) -> None:
        self.actions.append(kwargs)


class FakeUsersRepository:
    def __init__(self, users: list[User] | None = None) -> None:
        self.users = {user.telegram_id: user for user in users or []}

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        return self.users.get(telegram_id)


class FakeCustomerNotificationsRepository:
    def __init__(self) -> None:
        self.next_id = 1
        self.subscriptions: dict[int, CustomerTelegramSubscription] = {}

    def add(self, subscription: CustomerTelegramSubscription) -> None:
        subscription.id = self.next_id
        self.next_id += 1
        subscription.created_at = _now()
        subscription.updated_at = _now()
        self.subscriptions[subscription.telegram_user_id] = subscription

    async def get_by_user_id(self, user_id: int) -> CustomerTelegramSubscription | None:
        for subscription in self.subscriptions.values():
            if subscription.user_id == user_id:
                return subscription
        return None

    async def get_by_telegram_user_id(
        self,
        telegram_user_id: int,
    ) -> CustomerTelegramSubscription | None:
        return self.subscriptions.get(telegram_user_id)

    async def link_unlinked_subscription_to_user(
        self,
        *,
        user_id: int,
        telegram_user_id: int,
    ) -> CustomerTelegramSubscription | None:
        linked = await self.get_by_user_id(user_id)
        if linked is not None:
            return linked
        subscription = await self.get_by_telegram_user_id(telegram_user_id)
        if subscription is None or subscription.user_id is not None:
            return None
        subscription.user_id = user_id
        return subscription


@pytest.mark.asyncio
async def test_customer_bot_start_private_chat_creates_subscription_and_links_user() -> None:
    service, repository, telegram, audit = _service(users=[_user()])

    response = await service.handle_start(_message_update("/start").message, start_payload="")

    subscription = repository.subscriptions[42]
    assert response.handled is True
    assert response.result == "started"
    assert subscription.user_id == 1
    assert subscription.telegram_user_id == 42
    assert subscription.telegram_chat_id == 100
    assert subscription.chat_type == "private"
    assert subscription.has_chat is True
    assert subscription.service_opt_in is True
    assert subscription.marketing_opt_in is True
    assert subscription.marketing_opted_in_at == _now()
    assert subscription.marketing_opted_out_at is None
    assert telegram.messages[0][0] == "100"
    assert telegram.messages[0][1] == "Уведомления подключены. Сообщения по заказам включены."
    assert "Telegram-" not in telegram.messages[0][1]
    assert telegram.messages[0][2] is None
    assert audit.actions


@pytest.mark.asyncio
async def test_customer_bot_start_group_does_not_create_valid_recipient() -> None:
    service, repository, telegram, _ = _service(users=[_user()])

    response = await service.handle_start(
        _message_update("/start", chat_id=-100, chat_type="supergroup").message,
        start_payload="",
    )

    assert response.handled is True
    assert response.result == "private_chat_required"
    assert repository.subscriptions == {}
    assert telegram.messages[0][0] == "-100"


@pytest.mark.asyncio
async def test_customer_bot_stop_disables_service_and_marketing() -> None:
    service, repository, _, _ = _service(users=[_user()])
    await service.handle_start(_message_update("/start").message, start_payload="")
    repository.subscriptions[42].marketing_opt_in = True

    response = await service.handle_stop(_message_update("/stop").message)

    subscription = repository.subscriptions[42]
    assert response.handled is True
    assert response.result == "stopped"
    assert subscription.service_opt_in is False
    assert subscription.marketing_opt_in is False
    assert subscription.last_stop_at == _now()


@pytest.mark.asyncio
async def test_customer_bot_settings_returns_safe_settings_message() -> None:
    service, _, telegram, _ = _service(users=[_user()])
    await service.handle_start(_message_update("/start").message, start_payload="")
    telegram.messages.clear()

    response = await service.handle_settings(_message_update("/settings").message)

    assert response.handled is True
    assert response.result == "settings_sent"
    assert "Настройки уведомлений" in telegram.messages[0][1]
    assert "token" not in telegram.messages[0][1].lower()
    assert telegram.messages[0][2] is not None


@pytest.mark.asyncio
async def test_customer_bot_callbacks_update_service_and_marketing_opt_in() -> None:
    service, repository, telegram, _ = _service(users=[_user()])
    await service.handle_start(_message_update("/start").message, start_payload="")

    service_response = await service.handle_callback_query(
        _callback_update("customer_notifications:service:off").callback_query
    )
    marketing_response = await service.handle_callback_query(
        _callback_update("customer_notifications:marketing:on").callback_query
    )

    subscription = repository.subscriptions[42]
    assert service_response.result == "service_disabled"
    assert marketing_response.result == "marketing_enabled"
    assert subscription.service_opt_in is False
    assert subscription.marketing_opt_in is True
    assert telegram.answered_callbacks == [
        ("callback-id", "Настройки обновлены."),
        ("callback-id", "Настройки обновлены."),
    ]


@pytest.mark.asyncio
async def test_mini_app_patch_marketing_toggle_still_works_with_active_chat() -> None:
    service, repository, _, _ = _service(users=[_user()])
    await service.handle_start(_message_update("/start").message, start_payload="")
    repository.subscriptions[42].marketing_opt_in = False
    repository.subscriptions[42].marketing_opted_in_at = None

    response = await service.update_my_subscription(
        user=_user(),
        payload=CustomerSubscriptionUpdate(marketing_opt_in=True),
    )

    subscription = repository.subscriptions[42]
    assert response.marketing_opt_in is True
    assert subscription.marketing_opt_in is True
    assert subscription.marketing_opted_in_at == _now()
    assert subscription.opt_in_source == "mini_app_profile"


@pytest.mark.asyncio
async def test_mini_app_write_access_grant_creates_service_only_sendable_subscription() -> None:
    service, repository, _, _ = _service(users=[_user()])

    response = await service.record_write_access_result(
        user=_user(),
        payload=CustomerWriteAccessRequest(
            granted=True,
            source="mini_app_request_write_access",
        ),
    )

    subscription = repository.subscriptions[42]
    assert response.service_notifications_available is True
    assert response.availability_status == "available"
    assert response.has_chat is False
    assert response.write_access_granted is True
    assert subscription.user_id == 1
    assert subscription.telegram_user_id == 42
    assert subscription.telegram_chat_id is None
    assert subscription.has_chat is False
    assert subscription.write_access_granted is True
    assert subscription.write_access_granted_at == _now()
    assert subscription.write_access_denied_at is None
    assert subscription.service_opt_in is True
    assert subscription.marketing_opt_in is False
    assert subscription.opt_in_source == "mini_app_request_write_access"


@pytest.mark.asyncio
async def test_mini_app_write_access_denial_does_not_enable_sendability() -> None:
    service, repository, _, _ = _service(users=[_user()])

    response = await service.record_write_access_result(
        user=_user(),
        payload=CustomerWriteAccessRequest(
            granted=False,
            source="mini_app_request_write_access",
        ),
    )

    subscription = repository.subscriptions[42]
    assert response.service_notifications_available is False
    assert response.availability_status == "permission_denied"
    assert response.write_access_granted is False
    assert subscription.write_access_granted is False
    assert subscription.write_access_denied_at == _now()
    assert subscription.service_opt_in is False
    assert subscription.marketing_opt_in is False


@pytest.mark.asyncio
async def test_write_access_grant_does_not_clear_existing_blocked_state() -> None:
    service, repository, _, _ = _service(users=[_user()])
    repository.add(
        CustomerTelegramSubscription(
            user_id=1,
            telegram_user_id=42,
            telegram_chat_id=None,
            chat_type="unknown",
            has_chat=False,
            service_opt_in=False,
            marketing_opt_in=False,
            blocked_at=_now(),
            last_delivery_error="Forbidden: bot was blocked by the user",
        )
    )

    response = await service.record_write_access_result(
        user=_user(),
        payload=CustomerWriteAccessRequest(granted=True),
    )

    subscription = repository.subscriptions[42]
    assert response.service_notifications_available is False
    assert response.availability_status == "bot_blocked"
    assert subscription.write_access_granted is True
    assert subscription.service_opt_in is True
    assert subscription.blocked_at == _now()
    assert subscription.last_delivery_error == "Forbidden: bot was blocked by the user"


@pytest.mark.asyncio
async def test_mini_app_write_access_links_subscription_created_by_start_before_auth() -> None:
    service, repository, _, _ = _service(users=[])
    await service.handle_start(_message_update("/start").message, start_payload="")
    assert repository.subscriptions[42].user_id is None

    service.users_repository = FakeUsersRepository([_user()])
    response = await service.record_write_access_result(
        user=_user(),
        payload=CustomerWriteAccessRequest(granted=True),
    )

    subscription = repository.subscriptions[42]
    assert subscription.user_id == 1
    assert subscription.has_chat is True
    assert subscription.telegram_chat_id == 100
    assert response.service_notifications_available is True


@pytest.mark.asyncio
async def test_start_after_mini_app_auth_keeps_real_private_chat_target() -> None:
    service, repository, _, _ = _service(users=[_user()])
    await service.get_my_subscription(_user())

    response = await service.handle_start(
        _message_update("/start notifications").message,
        start_payload="notifications",
    )

    subscription = repository.subscriptions[42]
    assert response.result == "started_with_payload"
    assert subscription.user_id == 1
    assert subscription.telegram_chat_id == 100
    assert subscription.has_chat is True
    assert subscription.service_opt_in is True
    assert subscription.marketing_opt_in is True


@pytest.mark.asyncio
async def test_telegram_login_auto_links_existing_unlinked_customer_subscription() -> None:
    session = DummySession()
    auth_service = AuthService(session)  # type: ignore[arg-type]
    repository = FakeCustomerNotificationsRepository()
    repository.add(
        CustomerTelegramSubscription(
            user_id=None,
            telegram_user_id=42,
            telegram_chat_id=100,
            chat_type="private",
            has_chat=True,
            service_opt_in=True,
            marketing_opt_in=True,
        )
    )
    auth_service.customer_notifications_repository = repository  # type: ignore[assignment]

    await auth_service._link_customer_subscription(_user())  # noqa: SLF001

    assert repository.subscriptions[42].user_id == 1
    assert session.commits == 1


def test_customer_bot_webhook_route_rejects_missing_or_wrong_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_customer_webhook_secret", "secret")
    app = create_app()
    app.dependency_overrides[get_customer_bot_webhook_service] = lambda: FakeWebhookService()
    try:
        with TestClient(app) as client:
            missing = client.post(
                "/api/v1/telegram/customer-bot/webhook",
                json=_telegram_update_payload(),
            )
            wrong = client.post(
                "/api/v1/telegram/customer-bot/webhook",
                headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
                json=_telegram_update_payload(),
            )
    finally:
        app.dependency_overrides.clear()

    assert missing.status_code == 403
    assert wrong.status_code == 403


def test_customer_bot_webhook_route_accepts_secret_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telegram_customer_webhook_secret", "secret")
    fake_service = FakeWebhookService()
    app = create_app()
    app.dependency_overrides[get_customer_bot_webhook_service] = lambda: fake_service
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/telegram/customer-bot/webhook",
                headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
                json=_telegram_update_payload(),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"ok": True, "handled": True, "result": "started"}
    assert fake_service.update is not None


def test_mini_app_get_subscription_route_returns_current_user_state() -> None:
    app = _app_with_current_user(_user())
    app.dependency_overrides[get_customer_notifications_service] = lambda: FakeApiService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/customer-notifications/me/subscription")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["has_chat"] is False
    assert response.json()["bot_start_link"] == "https://t.me/customerbot?start=notifications"


def test_mini_app_patch_subscription_respects_missing_chat_state() -> None:
    app = _app_with_current_user(_user())
    app.dependency_overrides[get_customer_notifications_service] = lambda: FakeApiService()
    try:
        with TestClient(app) as client:
            response = client.patch(
                "/api/v1/customer-notifications/me/subscription",
                json={"marketing_opt_in": True},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["has_chat"] is False
    assert response.json()["marketing_opt_in"] is False


def test_mini_app_write_access_route_requires_authenticated_user() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/customer-notifications/me/write-access",
            json={"granted": True, "source": "mini_app_request_write_access"},
        )

    assert response.status_code == 401


def test_mini_app_write_access_route_returns_updated_subscription_state() -> None:
    app = _app_with_current_user(_user())
    fake_service = FakeApiService()
    app.dependency_overrides[get_customer_notifications_service] = lambda: fake_service
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/customer-notifications/me/write-access",
                json={"granted": True, "source": "mini_app_request_write_access"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["service_notifications_available"] is True
    assert fake_service.write_access_payload == {
        "granted": True,
        "source": "mini_app_request_write_access",
    }


def test_mini_app_write_access_route_rejects_raw_init_data() -> None:
    app = _app_with_current_user(_user())
    app.dependency_overrides[get_customer_notifications_service] = lambda: FakeApiService()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/customer-notifications/me/write-access",
                json={
                    "granted": True,
                    "source": "mini_app_request_write_access",
                    "initData": "raw-secret-init-data",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_seller_can_list_customer_notification_subscriptions() -> None:
    app = _app_with_current_user(_user(role=UserRole.SELLER))
    app.dependency_overrides[get_customer_notifications_service] = lambda: FakeApiService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/customer-notifications/subscriptions")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["telegram_chat_id_masked"] == "***0100"


def test_user_cannot_list_customer_notification_subscriptions() -> None:
    app = _app_with_current_user(_user(role=UserRole.USER))
    app.dependency_overrides[get_customer_notifications_service] = lambda: FakeApiService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/customer-notifications/subscriptions")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_seller_can_list_customer_service_notification_deliveries() -> None:
    app = _app_with_current_user(_user(role=UserRole.SELLER))
    app.dependency_overrides[get_customer_notifications_service] = lambda: FakeApiService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/customer-notifications/service-deliveries")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["event_name"] == "order.created.customer"
    assert "telegram_chat_id" not in response.json()["items"][0]


def test_user_cannot_list_customer_service_notification_deliveries() -> None:
    app = _app_with_current_user(_user(role=UserRole.USER))
    app.dependency_overrides[get_customer_notifications_service] = lambda: FakeApiService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/customer-notifications/service-deliveries")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_unauthenticated_cannot_list_customer_notification_subscriptions() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/customer-notifications/subscriptions")

    assert response.status_code == 401


class FakeWebhookService:
    def __init__(self) -> None:
        self.update: TelegramUpdate | None = None

    async def handle_update(self, update: TelegramUpdate) -> CustomerBotWebhookResponse:
        self.update = update
        return CustomerBotWebhookResponse(handled=True, result="started")


class FakeApiService:
    def __init__(self) -> None:
        self.write_access_payload: dict[str, object] | None = None

    async def get_my_subscription(self, _: User) -> CustomerSubscriptionMe:
        return _me_subscription()

    async def update_my_subscription(
        self,
        *,
        user: User,
        payload: CustomerSubscriptionUpdate,
    ) -> CustomerSubscriptionMe:
        del user, payload
        return _me_subscription()

    async def record_write_access_result(
        self,
        *,
        user: User,
        payload: CustomerWriteAccessRequest,
    ) -> CustomerSubscriptionMe:
        del user
        self.write_access_payload = payload.model_dump()
        return _me_subscription(available=payload.granted, write_access_granted=payload.granted)

    async def create_start_link(self, _: User) -> CustomerSubscriptionStartLink:
        return CustomerSubscriptionStartLink(
            bot_start_link="https://t.me/customerbot?start=notifications",
            start_command="/start notifications",
        )

    async def list_subscriptions(self, **_: object) -> CustomerSubscriptionList:
        return CustomerSubscriptionList(
            items=[
                {
                    "id": 1,
                    "user_id": 1,
                    "telegram_user_id": 42,
                    "telegram_chat_id_masked": "***0100",
                    "telegram_username": "buyer",
                    "telegram_first_name": "Ada",
                    "telegram_last_name": None,
                    "chat_type": "private",
                    "has_chat": True,
                    "write_access_granted": False,
                    "service_opt_in": True,
                    "marketing_opt_in": False,
                    "blocked_at": None,
                    "write_access_granted_at": None,
                    "write_access_denied_at": None,
                    "last_start_at": _now(),
                    "last_stop_at": None,
                    "last_settings_at": None,
                    "last_delivery_error": None,
                    "created_at": _now(),
                    "updated_at": _now(),
                }
            ],
            meta={"limit": 20, "offset": 0, "total": 1},
        )

    async def list_service_deliveries(self, **_: object) -> CustomerServiceNotificationDeliveryList:
        return CustomerServiceNotificationDeliveryList(
            items=[
                {
                    "id": 1,
                    "user_id": 1,
                    "order_id": 10,
                    "subscription_id": 5,
                    "event_name": "order.created.customer",
                    "channel": NotificationChannel.TELEGRAM,
                    "status": CustomerServiceNotificationDeliveryStatus.SENT,
                    "telegram_message_id": 123,
                    "error_code": None,
                    "error_message": None,
                    "retry_after_seconds": None,
                    "sent_at": _now(),
                    "created_at": _now(),
                    "updated_at": _now(),
                }
            ],
            meta={"limit": 20, "offset": 0, "total": 1},
        )


def _service(
    *,
    users: list[User] | None = None,
) -> tuple[
    CustomerNotificationsService,
    FakeCustomerNotificationsRepository,
    FakeTelegramService,
    FakeAuditService,
]:
    telegram = FakeTelegramService()
    audit = FakeAuditService()
    service = CustomerNotificationsService(
        DummySession(),
        telegram_service=telegram,
        audit_service=audit,
        now_factory=_now,
    )
    repository = FakeCustomerNotificationsRepository()
    service.repository = repository
    service.users_repository = FakeUsersRepository(users)
    return service, repository, telegram, audit


def _app_with_current_user(user: User):
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def _user(role: UserRole = UserRole.USER) -> User:
    return User(
        id=1,
        telegram_id=42,
        username="buyer",
        first_name="Ada",
        last_name=None,
        phone=None,
        role=role,
        is_active=True,
        created_at=_now(),
        updated_at=_now(),
    )


def _me_subscription(
    *,
    available: bool = False,
    write_access_granted: bool = False,
) -> CustomerSubscriptionMe:
    return CustomerSubscriptionMe(
        has_chat=available and not write_access_granted,
        write_access_granted=write_access_granted,
        service_notifications_available=available,
        availability_status="available" if available else "permission_required",
        availability_reason=None if available else "no_private_chat_or_write_access",
        service_opt_in=available,
        marketing_opt_in=False,
        blocked_at=None,
        write_access_granted_at=_now() if write_access_granted else None,
        write_access_denied_at=None,
        telegram_username=None,
        bot_start_link="https://t.me/customerbot?start=notifications",
        start_command="/start notifications",
    )


def _message_update(
    text: str,
    *,
    chat_id: int = 100,
    chat_type: str = "private",
) -> TelegramUpdate:
    return TelegramUpdate.model_validate(
        {
            "message": {
                "message_id": 10,
                "text": text,
                "chat": {"id": chat_id, "type": chat_type},
                "from": {
                    "id": 42,
                    "username": "buyer",
                    "first_name": "Ada",
                    "last_name": "Lovelace",
                },
            },
        }
    )


def _callback_update(callback_data: str) -> TelegramUpdate:
    return TelegramUpdate.model_validate(
        {
            "callback_query": {
                "id": "callback-id",
                "from": {"id": 42, "username": "buyer", "first_name": "Ada"},
                "message": {
                    "message_id": 11,
                    "text": "settings",
                    "chat": {"id": 100, "type": "private"},
                },
                "data": callback_data,
            },
        }
    )


def _telegram_update_payload() -> dict[str, object]:
    return {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "text": "/start",
            "chat": {"id": 100, "type": "private"},
            "from": {"id": 42, "username": "buyer", "first_name": "Ada"},
        },
    }


def _now() -> datetime:
    return datetime(2026, 6, 4, 12, 0, tzinfo=UTC)
