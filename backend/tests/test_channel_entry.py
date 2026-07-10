from __future__ import annotations

import json
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.common.deps import get_current_user
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import TelegramChannel, TelegramChannelEntryMessage, User, UserRole
from app.main import create_app
from app.modules.channel_entry.router import get_channel_entry_service, get_uploads_service
from app.modules.channel_entry.schemas import (
    ChannelEntryPreviewRequest,
    ChannelEntryPublishRequest,
    TelegramChannelCreate,
    TelegramChannelRead,
)
from app.modules.channel_entry.service import (
    ChannelEntryService,
    build_mini_app_direct_url,
    sanitize_telegram_error,
    validate_channel_chat_id,
)
from app.modules.telegram.service import (
    TelegramChannelEntryResult,
    TelegramDeliveryError,
    TelegramPhotoUpload,
    TelegramService,
)
from app.modules.uploads.service import UploadsService
from app.modules.uploads.storage import LocalStorageService


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


class FakeAuditService:
    def __init__(self) -> None:
        self.actions: list[dict[str, object]] = []

    async def record_action(self, **kwargs: object) -> None:
        self.actions.append(kwargs)

    def snapshot(self, instance: object, fields: tuple[str, ...]) -> dict[str, object]:
        return {field: getattr(instance, field) for field in fields}


class FakeChannelEntryRepository:
    def __init__(self) -> None:
        self.next_channel_id = 1
        self.next_message_id = 1
        self.channels: dict[int, TelegramChannel] = {}
        self.messages: dict[int, TelegramChannelEntryMessage] = {}

    async def list_active_channels(self) -> list[TelegramChannel]:
        return [channel for channel in self.channels.values() if channel.is_active]

    async def get_channel_by_id(self, channel_id: int) -> TelegramChannel | None:
        return self.channels.get(channel_id)

    async def get_active_channel_by_id(self, channel_id: int) -> TelegramChannel | None:
        channel = self.channels.get(channel_id)
        return channel if channel is not None and channel.is_active else None

    async def get_channel_by_chat_id(self, chat_id: str) -> TelegramChannel | None:
        for channel in self.channels.values():
            if channel.chat_id == chat_id:
                return channel
        return None

    def add_channel(self, channel: TelegramChannel) -> None:
        channel.id = self.next_channel_id
        self.next_channel_id += 1
        channel.created_at = _now()
        channel.updated_at = _now()
        self.channels[channel.id] = channel

    def add_message(self, message: TelegramChannelEntryMessage) -> None:
        message.id = self.next_message_id
        self.next_message_id += 1
        message.created_at = _now()
        message.updated_at = _now()
        if message.channel_id is not None:
            message.channel = self.channels.get(message.channel_id)
        self.messages[message.id] = message

    async def get_message_by_id(self, message_id: int) -> TelegramChannelEntryMessage | None:
        return self.messages.get(message_id)

    async def list_messages(
        self,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[TelegramChannelEntryMessage], int]:
        items = list(self.messages.values())
        return items[offset : offset + limit], len(items)


class FakeTelegramService:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []
        self.pinned: list[dict[str, object]] = []
        self.raise_send: TelegramDeliveryError | None = None
        self.raise_pin: TelegramDeliveryError | None = None

    async def send_channel_entry_message(
        self,
        chat_id: str,
        text: str,
        button_text: str,
        button_url: str,
        *,
        button_style: str | None = None,
        photos: list[TelegramPhotoUpload] | None = None,
        disable_notification: bool = False,
    ) -> TelegramChannelEntryResult:
        if self.raise_send is not None:
            raise self.raise_send
        self.sent.append(
            {
                "chat_id": chat_id,
                "text": text,
                "button_text": button_text,
                "button_url": button_url,
                "button_style": button_style,
                "photos": photos or [],
                "disable_notification": disable_notification,
            }
        )
        media_message_ids = [400 + index for index, _ in enumerate(photos or [])]
        return TelegramChannelEntryResult(message_id=321, media_message_ids=media_message_ids)

    async def pin_chat_message(
        self,
        chat_id: str,
        message_id: int,
        *,
        disable_notification: bool = True,
    ) -> None:
        if self.raise_pin is not None:
            raise self.raise_pin
        self.pinned.append(
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "disable_notification": disable_notification,
            }
        )


class RecordingTelegramService(TelegramService):
    def __init__(self) -> None:
        super().__init__(bot_token="secret-token")
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.multipart_calls: list[
            tuple[str, dict[str, str], dict[str, tuple[str, bytes, str]]]
        ] = []
        self.reject_style_once = False

    async def _post(self, method: str, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append((method, payload))
        reply_markup = payload.get("reply_markup")
        if (
            self.reject_style_once
            and isinstance(reply_markup, dict)
            and "style" in reply_markup["inline_keyboard"][0][0]
        ):
            self.reject_style_once = False
            return {"ok": False, "error_code": 400, "description": "unsupported style field"}
        if method == "sendMessage":
            return {"ok": True, "result": {"message_id": 55}}
        return {"ok": True, "result": True}

    async def _post_multipart(
        self,
        method: str,
        *,
        data: dict[str, str],
        files: dict[str, tuple[str, bytes, str]],
    ) -> dict[str, object]:
        self.multipart_calls.append((method, data, files))
        if method == "sendMediaGroup":
            media = json.loads(data["media"])
            return {
                "ok": True,
                "result": [{"message_id": 70 + index} for index, _ in enumerate(media)],
            }
        reply_markup = json.loads(data.get("reply_markup", "{}"))
        has_style = reply_markup.get("inline_keyboard", [[{}]])[0][0].get("style")
        if self.reject_style_once and has_style:
            self.reject_style_once = False
            return {"ok": False, "error_code": 400, "description": "unsupported style field"}
        return {"ok": True, "result": {"message_id": 66}}


class FakeRouteService:
    def get_config(self):
        return {
            "bot_username": "CheckYouStyleBot",
            "mini_app_direct_url": "https://t.me/CheckYouStyleBot?startapp=channel_pin",
            "mini_app_url": "https://mini.stylexac.ru/",
            "start_param": "channel_pin",
            "short_name": "",
            "has_customer_bot_token": True,
            "setup_hint": (
                "Используется Main Mini App link. Проверьте в BotFather, "
                "что для @CheckYouStyleBot настроен Main Mini App URL: https://mini.stylexac.ru/."
            ),
        }

    async def create_channel(self, payload: TelegramChannelCreate, *, actor: User):
        del actor
        return TelegramChannelRead(
            id=1,
            title=payload.title,
            chat_id=payload.chat_id,
            is_active=True,
            last_checked_at=None,
            last_check_status=None,
            last_check_error=None,
            created_by_user_id=1,
            created_at=_now(),
            updated_at=_now(),
        )

    async def publish(self, *_: object, **__: object) -> None:
        return None


@pytest.fixture(autouse=True)
def _disable_background_workers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "customer_campaign_worker_enabled", False)
    monkeypatch.setattr(settings, "manual_payment_expiration_worker_enabled", False)


def test_direct_link_builder_uses_bot_username_with_or_without_at() -> None:
    assert (
        build_mini_app_direct_url(
            bot_username="@CheckYouStyleBot",
            short_name="",
            start_param="channel_pin",
        )
        == "https://t.me/CheckYouStyleBot?startapp=channel_pin"
    )
    assert (
        build_mini_app_direct_url(
            bot_username="CheckYouStyleBot",
            short_name="",
            start_param="channel_pin",
        )
        == "https://t.me/CheckYouStyleBot?startapp=channel_pin"
    )


def test_direct_link_builder_supports_short_name_and_url_encoded_start_param() -> None:
    assert (
        build_mini_app_direct_url(
            bot_username="CheckYouStyleBot",
            short_name="shop",
            start_param="channel pin/тест",
        )
        == "https://t.me/CheckYouStyleBot/shop?startapp=channel%20pin%2F%D1%82%D0%B5%D1%81%D1%82"
    )


def test_config_route_returns_generated_link_and_never_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_customer_bot_token", "secret-token")
    app = _app_with_user(_user(UserRole.SELLER))
    app.dependency_overrides[get_channel_entry_service] = lambda: FakeRouteService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/channel-entry/config")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["mini_app_direct_url"] == "https://t.me/CheckYouStyleBot?startapp=channel_pin"
    assert body["has_customer_bot_token"] is True
    assert "secret-token" not in json.dumps(body, ensure_ascii=False)


def test_channel_create_requires_seller_or_admin() -> None:
    app = _app_with_user(_user(UserRole.USER))
    app.dependency_overrides[get_channel_entry_service] = lambda: FakeRouteService()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/channel-entry/channels",
                json={"title": "Test", "chat_id": "@checktsplatform"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_seller_can_create_channel_route() -> None:
    app = _app_with_user(_user(UserRole.SELLER))
    app.dependency_overrides[get_channel_entry_service] = lambda: FakeRouteService()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/channel-entry/channels",
                json={"title": "Test", "chat_id": "@checktsplatform"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["chat_id"] == "@checktsplatform"


def test_channel_chat_id_validation_accepts_public_username_and_numeric_id() -> None:
    assert validate_channel_chat_id("@checktsplatform") == "@checktsplatform"
    assert validate_channel_chat_id("-1001234567890") == "-1001234567890"


def test_publish_requires_seller_or_admin() -> None:
    app = _app_with_user(_user(UserRole.USER))
    app.dependency_overrides[get_channel_entry_service] = lambda: FakeRouteService()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/channel-entry/publish",
                json={"chat_id": "@checktsplatform", "text": "text"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_publish_route_rejects_empty_text() -> None:
    app = _app_with_user(_user(UserRole.SELLER))
    app.dependency_overrides[get_channel_entry_service] = lambda: FakeRouteService()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/channel-entry/publish",
                json={"chat_id": "@checktsplatform", "text": ""},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_publish_rejects_missing_channel_or_chat_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _, _, _ = _service(monkeypatch)

    with pytest.raises(AppError, match="Выберите сохраненный канал"):
        await service.publish(
            ChannelEntryPublishRequest(text="Откройте магазин прямо в Telegram."),
            actor=_user(UserRole.SELLER),
        )


@pytest.mark.asyncio
async def test_telegram_service_sends_url_inline_keyboard() -> None:
    telegram = RecordingTelegramService()

    result = await telegram.send_channel_entry_message(
        "@checktsplatform",
        "Откройте магазин прямо в Telegram.",
        "Открыть",
        "https://t.me/CheckYouStyleBot?startapp=channel_pin",
        disable_notification=True,
    )

    assert result.message_id == 55
    assert result.media_message_ids == []
    method, payload = telegram.calls[0]
    assert method == "sendMessage"
    assert payload["reply_markup"] == {
        "inline_keyboard": [
            [
                {
                    "text": "Открыть",
                    "url": "https://t.me/CheckYouStyleBot?startapp=channel_pin",
                }
            ]
        ]
    }
    assert "web_app" not in json.dumps(payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("button_style", ["primary", "success", "danger"])
async def test_telegram_service_sends_supported_button_styles(button_style: str) -> None:
    telegram = RecordingTelegramService()

    await telegram.send_channel_entry_message(
        "@checktsplatform",
        "Откройте магазин.",
        "Открыть",
        "https://t.me/CheckYouStyleBot?startapp=channel_pin",
        button_style=button_style,
    )

    button = telegram.calls[0][1]["reply_markup"]["inline_keyboard"][0][0]
    assert button["style"] == button_style


@pytest.mark.asyncio
async def test_telegram_service_default_style_is_omitted() -> None:
    telegram = RecordingTelegramService()

    await telegram.send_channel_entry_message(
        "@checktsplatform",
        "Откройте магазин.",
        "Открыть",
        "https://t.me/CheckYouStyleBot?startapp=channel_pin",
        button_style="default",
    )

    button = telegram.calls[0][1]["reply_markup"]["inline_keyboard"][0][0]
    assert "style" not in button


@pytest.mark.asyncio
async def test_telegram_service_retries_styled_button_without_style() -> None:
    telegram = RecordingTelegramService()
    telegram.reject_style_once = True

    result = await telegram.send_channel_entry_message(
        "@checktsplatform",
        "Откройте магазин.",
        "Открыть",
        "https://t.me/CheckYouStyleBot?startapp=channel_pin",
        button_style="primary",
    )

    assert result.message_id == 55
    assert len(telegram.calls) == 2
    fallback_button = telegram.calls[1][1]["reply_markup"]["inline_keyboard"][0][0]
    assert "style" not in fallback_button


@pytest.mark.asyncio
async def test_telegram_service_sends_one_photo_with_caption_and_keyboard() -> None:
    telegram = RecordingTelegramService()

    result = await telegram.send_channel_entry_message(
        "@checktsplatform",
        "Подпись",
        "Открыть",
        "https://t.me/CheckYouStyleBot?startapp=channel_pin",
        button_style="success",
        photos=[TelegramPhotoUpload(b"one", "one.jpg", "image/jpeg")],
    )

    assert result == TelegramChannelEntryResult(message_id=66, media_message_ids=[66])
    method, data, files = telegram.multipart_calls[0]
    assert method == "sendPhoto"
    assert data["caption"] == "Подпись"
    assert json.loads(data["reply_markup"])["inline_keyboard"][0][0]["style"] == "success"
    assert files["photo"][1] == b"one"


@pytest.mark.asyncio
@pytest.mark.parametrize("photo_count", [2, 3, 4])
async def test_telegram_service_sends_album_then_entry_message(photo_count: int) -> None:
    telegram = RecordingTelegramService()
    photos = [
        TelegramPhotoUpload(str(index).encode(), f"{index}.jpg", "image/jpeg")
        for index in range(photo_count)
    ]

    result = await telegram.send_channel_entry_message(
        "@checktsplatform",
        "Текст публикации",
        "Открыть",
        "https://t.me/CheckYouStyleBot?startapp=channel_pin",
        photos=photos,
    )

    assert result.message_id == 55
    assert result.media_message_ids == list(range(70, 70 + photo_count))
    assert telegram.multipart_calls[0][0] == "sendMediaGroup"
    assert len(telegram.multipart_calls[0][2]) == photo_count
    assert telegram.calls[0][0] == "sendMessage"


@pytest.mark.asyncio
async def test_publish_persists_message_and_pins_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, repository, telegram, audit = _service(monkeypatch)

    response = await service.publish(
        ChannelEntryPublishRequest(
            chat_id="@checktsplatform",
            text="Откройте магазин прямо в Telegram.",
            button_text="Открыть",
            pin=True,
        ),
        actor=_user(UserRole.SELLER),
    )

    assert response.ok is True
    assert response.item.telegram_message_id == 321
    assert response.item.is_pinned is True
    assert repository.messages[response.item.id].button_url == (
        "https://t.me/CheckYouStyleBot?startapp=channel_pin"
    )
    assert telegram.sent[0]["button_url"] == "https://t.me/CheckYouStyleBot?startapp=channel_pin"
    assert telegram.sent[0]["button_style"] == "default"
    assert telegram.pinned == [
        {"chat_id": "@checktsplatform", "message_id": 321, "disable_notification": True}
    ]
    assert {item["action"] for item in audit.actions} >= {
        "channel_entry.message_published",
        "channel_entry.message_pinned",
    }


@pytest.mark.asyncio
async def test_publish_without_pin_does_not_call_pin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _, telegram, _ = _service(monkeypatch)

    response = await service.publish(
        ChannelEntryPublishRequest(
            chat_id="@checktsplatform",
            text="Откройте магазин прямо в Telegram.",
            pin=False,
        ),
        actor=_user(UserRole.SELLER),
    )

    assert response.ok is True
    assert telegram.sent
    assert telegram.pinned == []


@pytest.mark.asyncio
async def test_multiple_photo_publication_pins_entry_message_and_preserves_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _, telegram, _ = _service(monkeypatch)
    photo_paths = ["channel_entry/one.jpg", "channel_entry/two.jpg"]

    response = await service.publish(
        ChannelEntryPublishRequest(
            chat_id="@checktsplatform",
            text="Альбом",
            button_style="danger",
            photo_paths=photo_paths,
            pin=True,
        ),
        actor=_user(UserRole.SELLER),
    )
    history = await service.history(limit=20, offset=0)

    assert telegram.pinned == [
        {"chat_id": "@checktsplatform", "message_id": 321, "disable_notification": True}
    ]
    assert response.item.telegram_media_message_ids == [400, 401]
    assert history.items[0].photo_paths == photo_paths
    assert history.items[0].button_style == "danger"
    assert history.items[0].telegram_media_message_ids == [400, 401]


def test_channel_entry_request_rejects_more_than_four_photos() -> None:
    with pytest.raises(ValidationError):
        ChannelEntryPublishRequest(
            chat_id="@checktsplatform",
            text="Альбом",
            photo_paths=[f"channel_entry/{index}.jpg" for index in range(5)],
        )


def test_existing_channel_entry_request_uses_compatible_defaults() -> None:
    request = ChannelEntryPreviewRequest(chat_id="@checktsplatform", text="Старый клиент")

    assert request.button_style == "default"
    assert request.photo_paths == []


def test_channel_entry_photo_upload_rejects_invalid_image(tmp_path: Path) -> None:
    app = _app_with_user(_user(UserRole.SELLER))
    upload_service = UploadsService(DummySession(), storage=LocalStorageService(tmp_path))  # type: ignore[arg-type]
    app.dependency_overrides[get_uploads_service] = lambda: upload_service
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/channel-entry/photos",
                files={"file": ("bad.txt", BytesIO(b"not an image"), "text/plain")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "Invalid file extension" in response.text


def test_telegram_errors_are_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telegram_customer_bot_token", "secret-token")
    error = TelegramDeliveryError(
        "Bad Request: chat not found https://api.telegram.org/botsecret-token/sendMessage",
        status_code=400,
    )

    message = sanitize_telegram_error(error, operation="publish")

    assert message == "Канал не найден. Проверьте @username или chat_id."
    assert "secret-token" not in message
    assert "api.telegram.org" not in message


def test_channel_entry_migration_and_model_contract() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260627_0038_add_telegram_channel_entry.py"
    )
    content = migration_path.read_text(encoding="utf-8")

    assert "telegram_channels" in content
    assert "telegram_channel_entry_messages" in content
    assert "uq_telegram_channels_chat_id" in content
    assert "button_url" in content
    assert TelegramChannel.__table__.c.chat_id.unique is True
    assert TelegramChannelEntryMessage.__table__.c.button_url.type.length == 1024
    assert TelegramChannelEntryMessage.__table__.c.telegram_message_id.nullable is True
    media_migration = migration_path.with_name(
        "20260710_0052_add_channel_entry_media_and_style.py"
    ).read_text(encoding="utf-8")
    assert "button_style" in media_migration
    assert "photo_paths" in media_migration
    assert "telegram_media_message_ids" in media_migration
    assert TelegramChannelEntryMessage.__table__.c.button_style.default.arg == "default"
    assert TelegramChannelEntryMessage.__table__.c.photo_paths.nullable is False


def _service(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[ChannelEntryService, FakeChannelEntryRepository, FakeTelegramService, FakeAuditService]:
    monkeypatch.setattr(settings, "telegram_customer_bot_username", "@CheckYouStyleBot")
    monkeypatch.setattr(settings, "telegram_customer_bot_token", "secret-token")
    monkeypatch.setattr(settings, "telegram_mini_app_short_name", "")
    monkeypatch.setattr(settings, "telegram_channel_entry_start_param", "channel_pin")
    repository = FakeChannelEntryRepository()
    telegram = FakeTelegramService()
    audit = FakeAuditService()
    service = ChannelEntryService(
        DummySession(),
        repository=repository,
        telegram_service=telegram,  # type: ignore[arg-type]
        audit_service=audit,  # type: ignore[arg-type]
        storage=FakeStorage(),  # type: ignore[arg-type]
        now_factory=_now,
    )
    return service, repository, telegram, audit


class FakeStorage:
    def read_bytes(self, relative_path: str) -> bytes:
        return relative_path.encode()


def _app_with_user(user: User):
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    return app


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


def _now() -> datetime:
    return datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
