import logging
from datetime import UTC, datetime

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.errors import AppError
from app.core.log_sanitization import (
    SensitiveDataLogFilter,
    redact_sensitive_path,
    redact_sensitive_text,
)
from app.db.models import PendingSellerRegistration, SellerRegistrationStatus
from app.main import create_app
from app.modules.seller_auth.callbacks import build_seller_registration_callback_data
from app.modules.seller_auth.schemas import SellerRegistrationStartRequest
from app.modules.seller_auth.service import SellerAuthService
from app.modules.telegram.router import get_seller_bot_webhook_service
from app.modules.telegram.schemas import SellerBotWebhookResponse, TelegramUpdate
from app.modules.telegram.service import SellerBotWebhookService


class DummySession:
    def __init__(self) -> None:
        self.commits = 0
        self.rolled_back = False
        self.added: list[object] = []

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rolled_back = True

    async def refresh(self, _: object) -> None:
        return None

    def add(self, instance: object) -> None:
        self.added.append(instance)


class FakeTelegramService:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []
        self.reply_markups: list[dict[str, object]] = []

    async def send_message(
        self,
        chat_id: str,
        message: str,
        *,
        reply_markup: dict[str, object] | None = None,
    ) -> None:
        self.messages.append((chat_id, message))
        if reply_markup is not None:
            self.reply_markups.append(reply_markup)


class FakeAuditService:
    async def record_action(self, **_: object) -> None:
        return None


class FakeSellerAuthRepository:
    def __init__(self) -> None:
        self.next_registration_id = 1
        self.registrations: dict[int, PendingSellerRegistration] = {}

    def add_pending_registration(self, registration: PendingSellerRegistration) -> None:
        registration.id = self.next_registration_id
        self.next_registration_id += 1
        registration.created_at = _now()
        registration.updated_at = _now()
        self.registrations[registration.id] = registration

    def add_seller_credential(self, _: object) -> None:
        return None

    def add_user(self, _: object) -> None:
        return None

    async def get_credential_by_email(self, _: str) -> None:
        return None

    async def get_active_pending_by_email(
        self,
        *,
        email: str,
        now: datetime,
    ) -> PendingSellerRegistration | None:
        for registration in self.registrations.values():
            if (
                registration.email == email
                and registration.status
                in {
                    SellerRegistrationStatus.PENDING,
                    SellerRegistrationStatus.AWAITING_APPROVAL,
                    SellerRegistrationStatus.APPROVED,
                }
                and registration.expires_at > now
            ):
                return registration
        return None

    async def get_pending_by_id(self, registration_id: int) -> PendingSellerRegistration | None:
        return self.registrations.get(registration_id)

    async def get_pending_by_start_token_hash(
        self,
        token_hash: str,
    ) -> PendingSellerRegistration | None:
        for registration in self.registrations.values():
            if registration.bot_start_token_hash == token_hash:
                return registration
        return None

    async def get_user_by_telegram_id(self, _: int) -> None:
        return None


@pytest.mark.asyncio
async def test_seller_bot_webhook_links_registration_and_requests_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, repository, telegram = _webhook_service()
    started = await service.seller_auth_service.start_registration(_start_payload())

    response = await service.handle_update(
        TelegramUpdate.model_validate(
            {
                "update_id": 1,
                "message": {
                    "message_id": 10,
                    "text": "/start seller_start-token",
                    "chat": {"id": 100, "type": "private"},
                    "from": {
                        "id": 99,
                        "username": "sellername",
                        "first_name": "Ada",
                        "last_name": "Lovelace",
                    },
                },
            }
        )
    )

    registration = repository.registrations[started.registration_id]
    assert response.handled is True
    assert response.result == "registration_linked"
    assert registration.telegram_user_id == 99
    assert registration.telegram_chat_id == 100
    assert registration.status == SellerRegistrationStatus.AWAITING_APPROVAL
    assert registration.verification_code_hash is None
    assert telegram.messages[0][0] == "-100"
    assert "seller@example.com" in telegram.messages[0][1]
    assert telegram.reply_markups[0]["inline_keyboard"]


@pytest.mark.asyncio
async def test_seller_bot_confirm_callback_sends_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, repository, telegram = _webhook_service()
    started = await service.seller_auth_service.start_registration(_start_payload())
    await service.handle_update(_telegram_start_update())
    telegram.messages.clear()

    response = await service.handle_update(
        _callback_update(
            build_seller_registration_callback_data(
                action="approve",
                registration_id=started.registration_id,
            )
        )
    )

    registration = repository.registrations[started.registration_id]
    assert response.handled is True
    assert response.result == "registration_approved"
    assert registration.status == SellerRegistrationStatus.APPROVED
    assert telegram.messages == [
        ("100", "Код подтверждения: 123456. Введите его в Seller Panel."),
        ("-100", "Регистрация продавца подтверждена. Код отправлен продавцу."),
    ]


@pytest.mark.asyncio
async def test_seller_bot_reject_callback_sends_failure_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, repository, telegram = _webhook_service()
    started = await service.seller_auth_service.start_registration(_start_payload())
    await service.handle_update(_telegram_start_update())
    telegram.messages.clear()

    response = await service.handle_update(
        _callback_update(
            build_seller_registration_callback_data(
                action="reject",
                registration_id=started.registration_id,
            )
        )
    )

    registration = repository.registrations[started.registration_id]
    assert response.handled is True
    assert response.result == "registration_rejected"
    assert registration.status == SellerRegistrationStatus.REJECTED
    assert telegram.messages == [
        ("100", "Регистрация не удалась."),
        ("-100", "Регистрация продавца отклонена."),
    ]


@pytest.mark.asyncio
async def test_seller_bot_webhook_ignores_non_start_messages() -> None:
    service, _, telegram = _webhook_service()

    response = await service.handle_update(
        TelegramUpdate.model_validate(
            {
                "message": {
                    "text": "hello",
                    "chat": {"id": 100, "type": "private"},
                    "from": {"id": 99, "username": "sellername"},
                }
            }
        )
    )

    assert response.handled is False
    assert response.result == "ignored"
    assert telegram.messages == []


@pytest.mark.asyncio
async def test_block_seller_command_uses_internal_seller_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, seller_bot, telegram = _seller_command_webhook_service()

    response = await service.handle_update(_seller_group_command_update("/block_seller 5"))

    assert response.handled is True
    assert response.result == "seller_blocked"
    assert seller_bot.blocked_user_ids == [5]
    assert telegram.messages == [("-100", "Seller #5 has been blocked.")]


@pytest.mark.asyncio
async def test_new_product_caption_command_is_routed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, seller_bot, telegram = _seller_command_webhook_service()

    response = await service.handle_update(_seller_group_product_command_update())

    assert response.handled is True
    assert response.result == "bot_product_draft_created"
    assert seller_bot.product_messages == ["White Hoodie"]
    assert telegram.messages == [("-100", "Product draft created.")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("command_text", "expected_fragment"),
    [
        ("/block_seller", "Usage: /block_seller <Seller ID>. Get Seller ID with /sellers."),
        (
            "/block_seller nope",
            "Usage: /block_seller <Seller ID>. Get Seller ID with /sellers.",
        ),
        ("/block_seller 6902459394", "Telegram ID"),
        ("/block_seller 999999999999999999999999", "outside the supported range"),
    ],
)
async def test_block_seller_invalid_id_is_handled_without_seller_lookup(
    monkeypatch: pytest.MonkeyPatch,
    command_text: str,
    expected_fragment: str,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, seller_bot, telegram = _seller_command_webhook_service()

    response = await service.handle_update(_seller_group_command_update(command_text))

    assert response.handled is True
    assert response.result == "seller_command_error"
    assert seller_bot.blocked_user_ids == []
    assert expected_fragment in telegram.messages[0][1]


@pytest.mark.asyncio
async def test_seller_bot_webhook_sends_error_for_expired_token() -> None:
    telegram = FakeTelegramService()

    class FakeSellerAuthService:
        telegram_service = telegram

        async def handle_telegram_start(self, _: object) -> None:
            raise AppError("Seller registration expired", status.HTTP_400_BAD_REQUEST)

    service = SellerBotWebhookService(
        seller_auth_service=FakeSellerAuthService(),
        telegram_service=telegram,
    )

    response = await service.handle_update(
        TelegramUpdate.model_validate(
            {
                "message": {
                    "text": "/start seller_expired",
                    "chat": {"id": 100, "type": "private"},
                    "from": {"id": 99, "username": "sellername"},
                }
            }
        )
    )

    assert response.handled is True
    assert response.result == "registration_error"
    assert telegram.messages == [
        ("100", "Ссылка регистрации истекла. Начните регистрацию заново в Seller Panel.")
    ]


def test_seller_bot_webhook_route_requires_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telegram_seller_webhook_secret", "secret")
    app = create_app()
    app.dependency_overrides[get_seller_bot_webhook_service] = lambda: FakeWebhookService()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/telegram/seller-bot/webhook/wrong",
                json=_telegram_update_payload(),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_seller_bot_webhook_route_requires_secret_header_on_safe_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_webhook_secret", "secret")
    app = create_app()
    app.dependency_overrides[get_seller_bot_webhook_service] = lambda: FakeWebhookService()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/telegram/seller-bot/webhook",
                json=_telegram_update_payload(),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_seller_bot_webhook_route_accepts_secret_header_without_path_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_webhook_secret", "secret")
    fake_service = FakeWebhookService()
    app = create_app()
    app.dependency_overrides[get_seller_bot_webhook_service] = lambda: fake_service
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/telegram/seller-bot/webhook",
                headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
                json=_telegram_update_payload(),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"ok": True, "handled": True, "result": "registration_linked"}
    assert fake_service.update is not None


def test_seller_bot_webhook_route_accepts_secret_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_webhook_secret", "secret")
    fake_service = FakeWebhookService()
    app = create_app()
    app.dependency_overrides[get_seller_bot_webhook_service] = lambda: fake_service
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/telegram/seller-bot/webhook/secret",
                headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
                json=_telegram_update_payload(),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"ok": True, "handled": True, "result": "registration_linked"}
    assert fake_service.update is not None
    assert fake_service.update.message is not None
    assert fake_service.update.message.from_user is not None
    assert fake_service.update.message.from_user.username == "sellername"


def test_seller_bot_webhook_route_returns_200_for_oversized_block_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    monkeypatch.setattr(settings, "telegram_seller_webhook_secret", "secret")
    service, seller_bot, telegram = _seller_command_webhook_service()
    app = create_app()
    app.dependency_overrides[get_seller_bot_webhook_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/telegram/seller-bot/webhook",
                headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
                json=_seller_group_command_payload("/block_seller 999999999999999999999999"),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"ok": True, "handled": True, "result": "seller_command_error"}
    assert seller_bot.blocked_user_ids == []
    assert "outside the supported range" in telegram.messages[0][1]


def test_seller_bot_webhook_secret_path_is_redacted_from_logs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_webhook_secret", "secret")

    redacted = redact_sensitive_path("/api/v1/telegram/seller-bot/webhook/secret")

    assert redacted == "/api/v1/telegram/seller-bot/webhook/<secret>"


def test_sensitive_tokens_are_redacted_from_log_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telegram_bot_token", "seller-bot-token")
    monkeypatch.setattr(settings, "telegram_webapp_bot_token", "webapp-bot-token")
    monkeypatch.setattr(settings, "telegram_seller_webhook_secret", "seller-webhook-secret")

    redacted = redact_sensitive_text(
        "POST https://api.telegram.org/botseller-bot-token/sendMessage "
        "webapp-bot-token /api/v1/telegram/seller-bot/webhook/seller-webhook-secret"
    )

    assert "seller-bot-token" not in redacted
    assert "webapp-bot-token" not in redacted
    assert "seller-webhook-secret" not in redacted
    assert "/bot<redacted>/sendMessage" in redacted
    assert "/api/v1/telegram/seller-bot/webhook/<secret>" in redacted


def test_log_filter_redacts_uvicorn_access_args(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telegram_seller_webhook_secret", "seller-webhook-secret")
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='127.0.0.1 - "POST %s HTTP/1.1" 200',
        args=("/api/v1/telegram/seller-bot/webhook/seller-webhook-secret",),
        exc_info=None,
    )

    SensitiveDataLogFilter().filter(record)

    message = record.getMessage()
    assert "seller-webhook-secret" not in message
    assert "/api/v1/telegram/seller-bot/webhook/<secret>" in message


class FakeWebhookService:
    def __init__(self) -> None:
        self.update: TelegramUpdate | None = None

    async def handle_update(self, update: TelegramUpdate) -> SellerBotWebhookResponse:
        self.update = update
        return SellerBotWebhookResponse(handled=True, result="registration_linked")


class FakeSellerBotCommandService:
    def __init__(self) -> None:
        self.blocked_user_ids: list[int] = []
        self.unblocked_user_ids: list[int] = []
        self.product_messages: list[str] = []

    async def format_sellers_command(self, *, chat_id: int) -> str:
        return f"Seller list for {chat_id}"

    async def block_seller_command(
        self,
        *,
        chat_id: int,
        target_user_id: int,
        actor_telegram_user_id: int | None,
        actor_username: str | None,
    ) -> str:
        self.blocked_user_ids.append(target_user_id)
        return f"Seller #{target_user_id} has been blocked."

    async def unblock_seller_command(
        self,
        *,
        chat_id: int,
        target_user_id: int,
        actor_telegram_user_id: int | None,
        actor_username: str | None,
    ) -> str:
        self.unblocked_user_ids.append(target_user_id)
        return f"Seller #{target_user_id} has been unblocked."

    async def create_quick_product_draft_command(
        self,
        *,
        chat_id: int,
        message,
        actor_telegram_user_id: int | None,
        actor_username: str | None,
    ) -> str:
        del chat_id, actor_telegram_user_id, actor_username
        title_line = (message.caption or "").splitlines()[1]
        self.product_messages.append(title_line.split(":", 1)[1].strip())
        return "Product draft created."


def _webhook_service() -> tuple[
    SellerBotWebhookService,
    FakeSellerAuthRepository,
    FakeTelegramService,
]:
    telegram = FakeTelegramService()
    seller_auth_service = SellerAuthService(
        DummySession(),
        telegram_service=telegram,
        audit_service=FakeAuditService(),
        token_factory=lambda: "start-token",
        code_factory=lambda: "123456",
        now_factory=_now,
    )
    repository = FakeSellerAuthRepository()
    seller_auth_service.repository = repository
    return (
        SellerBotWebhookService(
            seller_auth_service=seller_auth_service,
            telegram_service=telegram,
        ),
        repository,
        telegram,
    )


def _seller_command_webhook_service() -> tuple[
    SellerBotWebhookService,
    FakeSellerBotCommandService,
    FakeTelegramService,
]:
    telegram = FakeTelegramService()

    class FakeSellerAuthService:
        telegram_service = telegram

    seller_bot = FakeSellerBotCommandService()
    return (
        SellerBotWebhookService(
            seller_auth_service=FakeSellerAuthService(),
            seller_bot_service=seller_bot,
            telegram_service=telegram,
        ),
        seller_bot,
        telegram,
    )


def _start_payload() -> SellerRegistrationStartRequest:
    return SellerRegistrationStartRequest(
        email="seller@example.com",
        password="Password1",
        telegram_username="@sellername",
    )


def _telegram_update_payload() -> dict[str, object]:
    return {
        "update_id": 1,
        "message": {
            "text": "/start seller_token",
            "chat": {"id": 100, "type": "private"},
            "from": {"id": 99, "username": "sellername", "first_name": "Ada"},
        },
    }


def _seller_group_command_payload(text: str) -> dict[str, object]:
    return {
        "update_id": 10,
        "message": {
            "message_id": 20,
            "text": text,
            "chat": {"id": -100, "type": "supergroup"},
            "from": {"id": 500, "username": "approver"},
        },
    }


def _seller_group_command_update(text: str) -> TelegramUpdate:
    return TelegramUpdate.model_validate(_seller_group_command_payload(text))


def _seller_group_product_command_update() -> TelegramUpdate:
    return TelegramUpdate.model_validate(
        {
            "update_id": 11,
            "message": {
                "message_id": 21,
                "caption": "/new_product\nНазвание: White Hoodie\nЦена: 1990",
                "photo": [{"file_id": "photo", "width": 1200, "height": 1500}],
                "chat": {"id": -100, "type": "supergroup"},
                "from": {"id": 500, "username": "operator"},
            },
        }
    )


def _telegram_start_update() -> TelegramUpdate:
    return TelegramUpdate.model_validate(
        {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "text": "/start seller_start-token",
                "chat": {"id": 100, "type": "private"},
                "from": {
                    "id": 99,
                    "username": "sellername",
                    "first_name": "Ada",
                    "last_name": "Lovelace",
                },
            },
        }
    )


def _callback_update(callback_data: str, *, chat_id: int = -100) -> TelegramUpdate:
    return TelegramUpdate.model_validate(
        {
            "update_id": 2,
            "callback_query": {
                "id": "callback-id",
                "from": {"id": 500, "username": "approver"},
                "message": {
                    "message_id": 11,
                    "text": "approval",
                    "chat": {"id": chat_id, "type": "supergroup"},
                },
                "data": callback_data,
            },
        }
    )


def _now() -> datetime:
    return datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
