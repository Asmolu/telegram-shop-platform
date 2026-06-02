from datetime import UTC, datetime

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.errors import AppError
from app.core.log_sanitization import redact_sensitive_path
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


def test_seller_bot_webhook_secret_path_is_redacted_from_logs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_webhook_secret", "secret")

    redacted = redact_sensitive_path("/api/v1/telegram/seller-bot/webhook/secret")

    assert redacted == "/api/v1/telegram/seller-bot/webhook/<secret>"


class FakeWebhookService:
    def __init__(self) -> None:
        self.update: TelegramUpdate | None = None

    async def handle_update(self, update: TelegramUpdate) -> SellerBotWebhookResponse:
        self.update = update
        return SellerBotWebhookResponse(handled=True, result="registration_linked")


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
