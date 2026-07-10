from __future__ import annotations

import mimetypes
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PageMeta
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import TelegramChannel, TelegramChannelEntryMessage, User
from app.modules.audit.service import AuditService, NoopAuditService
from app.modules.channel_entry.repository import ChannelEntryRepository
from app.modules.channel_entry.schemas import (
    ChannelCheckRequest,
    ChannelCheckResponse,
    ChannelEntryConfigRead,
    ChannelEntryHistoryRead,
    ChannelEntryPreviewRead,
    ChannelEntryPreviewRequest,
    ChannelEntryPublishRead,
    ChannelEntryPublishRequest,
    TelegramChannelCreate,
    TelegramChannelEntryMessageRead,
    TelegramChannelRead,
    TelegramChannelUpdate,
)
from app.modules.telegram.service import TelegramDeliveryError, TelegramPhotoUpload, TelegramService
from app.modules.uploads.storage import LocalStorageService

USERNAME_CHAT_ID_RE = re.compile(r"^@[A-Za-z0-9_]{5,64}$")
NUMERIC_CHANNEL_CHAT_ID_RE = re.compile(r"^-100[0-9]{5,20}$")
BOT_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")
TELEGRAM_ERROR_MESSAGE_MAX_LENGTH = 500
CHANNEL_ENTRY_PHOTO_FOLDER = "channel_entry/"

ACTION_CHANNEL_CREATED = "channel_entry.channel_created"
ACTION_CHANNEL_UPDATED = "channel_entry.channel_updated"
ACTION_CHANNEL_DISABLED = "channel_entry.channel_disabled"
ACTION_MESSAGE_PUBLISHED = "channel_entry.message_published"
ACTION_MESSAGE_PUBLISH_FAILED = "channel_entry.message_publish_failed"
ACTION_MESSAGE_PINNED = "channel_entry.message_pinned"
ACTION_MESSAGE_PIN_FAILED = "channel_entry.message_pin_failed"

CHANNEL_AUDIT_FIELDS = (
    "title",
    "chat_id",
    "is_active",
    "last_checked_at",
    "last_check_status",
    "last_check_error",
)
MESSAGE_AUDIT_FIELDS = (
    "channel_id",
    "chat_id",
    "button_text",
    "button_url",
    "telegram_message_id",
    "is_pinned",
    "published_at",
    "pinned_at",
    "last_error",
)


class ChannelEntryService:
    """Business logic for Telegram channel entry messages from Seller Panel."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        repository: ChannelEntryRepository | None = None,
        telegram_service: TelegramService | None = None,
        audit_service: AuditService | NoopAuditService | None = None,
        storage: LocalStorageService | None = None,
        now_factory: Any | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or ChannelEntryRepository(session)
        self.telegram_service = telegram_service or TelegramService(
            bot_token=settings.telegram_customer_bot_token,
        )
        self.audit_service = audit_service or AuditService(session)
        self.storage = storage or LocalStorageService()
        self.now_factory = now_factory or (lambda: datetime.now(UTC))

    def get_config(self) -> ChannelEntryConfigRead:
        bot_username = normalize_bot_username(settings.telegram_customer_bot_username)
        start_param = settings.telegram_channel_entry_start_param.strip() or "channel_pin"
        short_name = normalize_short_name(settings.telegram_mini_app_short_name)
        mini_app_direct_url = build_mini_app_direct_url(
            bot_username=bot_username,
            short_name=short_name,
            start_param=start_param,
        )
        mini_app_url = _mini_app_url_for_display()
        if short_name:
            setup_hint = (
                f"Используется Mini App short name {short_name}. Проверьте в BotFather, "
                f"что для @{bot_username} настроен Mini App URL: {mini_app_url}."
            )
        else:
            setup_hint = (
                "Используется Main Mini App link. Проверьте в BotFather, "
                f"что для @{bot_username} настроен Main Mini App URL: {mini_app_url}."
            )
        return ChannelEntryConfigRead(
            bot_username=bot_username,
            mini_app_direct_url=mini_app_direct_url,
            mini_app_url=mini_app_url,
            start_param=start_param,
            short_name=short_name,
            has_customer_bot_token=bool(settings.telegram_customer_bot_token),
            setup_hint=setup_hint,
        )

    async def list_channels(self) -> list[TelegramChannelRead]:
        channels = await self.repository.list_active_channels()
        return [TelegramChannelRead.model_validate(channel) for channel in channels]

    async def create_channel(
        self,
        payload: TelegramChannelCreate,
        *,
        actor: User,
    ) -> TelegramChannelRead:
        chat_id = validate_channel_chat_id(payload.chat_id)
        channel = TelegramChannel(
            title=payload.title.strip(),
            chat_id=chat_id,
            is_active=True,
            created_by_user_id=actor.id,
        )
        self.repository.add_channel(channel)
        try:
            await self._flush_if_supported()
            await self.audit_service.record_action(
                actor_user_id=actor.id,
                action=ACTION_CHANNEL_CREATED,
                entity_type="telegram_channel",
                entity_id=channel.id,
                after_data=self.audit_service.snapshot(channel, CHANNEL_AUDIT_FIELDS),
                commit=False,
            )
            await self.session.commit()
            await self._refresh_if_supported(channel)
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(
                "Канал с таким chat_id уже сохранен.",
                status.HTTP_409_CONFLICT,
            ) from exc
        return TelegramChannelRead.model_validate(channel)

    async def update_channel(
        self,
        channel_id: int,
        payload: TelegramChannelUpdate,
        *,
        actor: User,
    ) -> TelegramChannelRead:
        channel = await self._get_channel_or_404(channel_id)
        before_data = self.audit_service.snapshot(channel, CHANNEL_AUDIT_FIELDS)

        if "title" in payload.model_fields_set and payload.title is not None:
            channel.title = payload.title.strip()
        if "chat_id" in payload.model_fields_set and payload.chat_id is not None:
            channel.chat_id = validate_channel_chat_id(payload.chat_id)
        if "is_active" in payload.model_fields_set and payload.is_active is not None:
            channel.is_active = payload.is_active

        try:
            await self.audit_service.record_action(
                actor_user_id=actor.id,
                action=ACTION_CHANNEL_UPDATED,
                entity_type="telegram_channel",
                entity_id=channel.id,
                before_data=before_data,
                after_data=self.audit_service.snapshot(channel, CHANNEL_AUDIT_FIELDS),
                commit=False,
            )
            await self.session.commit()
            await self._refresh_if_supported(channel)
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(
                "Канал с таким chat_id уже сохранен.",
                status.HTTP_409_CONFLICT,
            ) from exc
        return TelegramChannelRead.model_validate(channel)

    async def disable_channel(self, channel_id: int, *, actor: User) -> None:
        channel = await self._get_channel_or_404(channel_id)
        before_data = self.audit_service.snapshot(channel, CHANNEL_AUDIT_FIELDS)
        channel.is_active = False
        await self.audit_service.record_action(
            actor_user_id=actor.id,
            action=ACTION_CHANNEL_DISABLED,
            entity_type="telegram_channel",
            entity_id=channel.id,
            before_data=before_data,
            after_data=self.audit_service.snapshot(channel, CHANNEL_AUDIT_FIELDS),
            commit=False,
        )
        await self._commit("Не удалось отключить канал.")

    async def check_channel(self, payload: ChannelCheckRequest) -> ChannelCheckResponse:
        chat_id = validate_channel_chat_id(payload.chat_id)
        channel = await self.repository.get_channel_by_chat_id(chat_id)
        now = self._now()
        chat: dict[str, object] | None = None

        try:
            chat = await self.telegram_service.get_chat(chat_id)
            member = await self.telegram_service.get_bot_member_status(chat_id)
        except TelegramDeliveryError as exc:
            message = sanitize_telegram_error(exc)
            if channel is not None:
                channel.last_checked_at = now
                channel.last_check_status = "failed"
                channel.last_check_error = message
                await self._commit("Не удалось сохранить результат проверки канала.")
            return ChannelCheckResponse(
                ok=False,
                chat_id=chat_id,
                title=_string_or_none(chat.get("title") if chat else None),
                type=_string_or_none(chat.get("type") if chat else None),
                username=_string_or_none(chat.get("username") if chat else None),
                can_post_estimate=None,
                can_pin_estimate=None,
                message=message,
            )

        can_post, can_pin, rights_message, ok = _estimate_member_rights(member)
        if channel is not None:
            channel.last_checked_at = now
            channel.last_check_status = "ok" if ok else "failed"
            channel.last_check_error = None if ok else rights_message
            await self._commit("Не удалось сохранить результат проверки канала.")

        return ChannelCheckResponse(
            ok=ok,
            chat_id=chat_id,
            title=_string_or_none(chat.get("title")),
            type=_string_or_none(chat.get("type")),
            username=_string_or_none(chat.get("username")),
            can_post_estimate=can_post,
            can_pin_estimate=can_pin,
            message=rights_message,
        )

    async def preview(self, payload: ChannelEntryPreviewRequest) -> ChannelEntryPreviewRead:
        resolved = await self._resolve_target(payload.channel_id, payload.chat_id)
        button_url = self._button_url()
        warnings: list[str] = []
        if not settings.telegram_customer_bot_token:
            warnings.append("Не настроен TELEGRAM_CUSTOMER_BOT_TOKEN.")
        if payload.chat_id and payload.channel_id is None:
            warnings.append("Канал введен вручную и не будет сохранен в список каналов.")
        return ChannelEntryPreviewRead(
            text=payload.text.strip(),
            button_text=payload.button_text.strip(),
            button_style=payload.button_style,
            button_url=button_url,
            photo_paths=payload.photo_paths,
            photo_urls=[settings.public_upload_url_for(path) for path in payload.photo_paths],
            selected_chat_id=resolved.chat_id,
            warnings=warnings,
        )

    async def publish(
        self,
        payload: ChannelEntryPublishRequest,
        *,
        actor: User,
    ) -> ChannelEntryPublishRead:
        resolved = await self._resolve_target(payload.channel_id, payload.chat_id)
        button_url = self._button_url()
        photos = self._load_channel_entry_photos(payload.photo_paths)
        message = TelegramChannelEntryMessage(
            channel_id=resolved.channel_id,
            chat_id=resolved.chat_id,
            text=payload.text.strip(),
            button_text=payload.button_text.strip(),
            button_url=button_url,
            is_pinned=False,
            created_by_user_id=actor.id,
        )
        self.repository.add_message(message)
        await self._commit("Не удалось создать запись публикации.")
        await self._refresh_if_supported(message)

        try:
            telegram_message_id = await self.telegram_service.send_channel_entry_message(
                resolved.chat_id,
                message.text,
                message.button_text,
                message.button_url,
                button_style=payload.button_style,
                photos=photos,
                disable_notification=payload.disable_notification,
            )
        except TelegramDeliveryError as exc:
            message.last_error = sanitize_telegram_error(exc, operation="publish")
            await self._audit_message(
                actor=actor,
                action=ACTION_MESSAGE_PUBLISH_FAILED,
                message=message,
            )
            await self._commit("Не удалось сохранить ошибку публикации.")
            raise AppError(message.last_error, status.HTTP_502_BAD_GATEWAY) from exc

        message.telegram_message_id = telegram_message_id
        message.published_at = self._now()
        message.last_error = None
        await self._audit_message(
            actor=actor,
            action=ACTION_MESSAGE_PUBLISHED,
            message=message,
        )

        pin_status = "not_requested"
        if payload.pin:
            pin_status = await self._pin_message(
                message,
                actor=actor,
                fail_soft=True,
            )

        await self._commit("Не удалось сохранить результат публикации.")
        await self._refresh_if_supported(message)

        if pin_status == "failed":
            return ChannelEntryPublishRead(
                ok=False,
                status="published_pin_failed",
                message=message.last_error or "Сообщение опубликовано, но не закреплено.",
                item=TelegramChannelEntryMessageRead.model_validate(message),
            )
        return ChannelEntryPublishRead(
            ok=True,
            status="published",
            message=(
                "Сообщение опубликовано и закреплено."
                if payload.pin
                else "Сообщение опубликовано."
            ),
            item=TelegramChannelEntryMessageRead.model_validate(message),
        )

    async def pin_message(self, message_id: int, *, actor: User) -> TelegramChannelEntryMessageRead:
        message = await self.repository.get_message_by_id(message_id)
        if message is None:
            raise AppError("Публикация не найдена.", status.HTTP_404_NOT_FOUND)
        try:
            await self._pin_message(message, actor=actor, fail_soft=False)
        except AppError:
            await self._commit("Не удалось сохранить ошибку закрепления.")
            raise
        await self._commit("Не удалось сохранить результат закрепления.")
        await self._refresh_if_supported(message)
        return TelegramChannelEntryMessageRead.model_validate(message)

    async def history(self, *, limit: int, offset: int) -> ChannelEntryHistoryRead:
        items, total = await self.repository.list_messages(limit=limit, offset=offset)
        return ChannelEntryHistoryRead(
            items=[TelegramChannelEntryMessageRead.model_validate(item) for item in items],
            meta=PageMeta(limit=limit, offset=offset, total=total),
        )

    async def _pin_message(
        self,
        message: TelegramChannelEntryMessage,
        *,
        actor: User,
        fail_soft: bool,
    ) -> str:
        if message.telegram_message_id is None:
            message.last_error = "Telegram не вернул message_id; закрепление недоступно."
            await self._audit_message(
                actor=actor,
                action=ACTION_MESSAGE_PIN_FAILED,
                message=message,
            )
            if fail_soft:
                return "failed"
            raise AppError(message.last_error, status.HTTP_409_CONFLICT)

        try:
            await self.telegram_service.pin_chat_message(
                message.chat_id,
                int(message.telegram_message_id),
                disable_notification=True,
            )
        except TelegramDeliveryError as exc:
            message.last_error = sanitize_telegram_error(exc, operation="pin")
            await self._audit_message(
                actor=actor,
                action=ACTION_MESSAGE_PIN_FAILED,
                message=message,
            )
            if fail_soft:
                return "failed"
            raise AppError(message.last_error, status.HTTP_502_BAD_GATEWAY) from exc

        message.is_pinned = True
        message.pinned_at = self._now()
        message.last_error = None
        await self._audit_message(
            actor=actor,
            action=ACTION_MESSAGE_PINNED,
            message=message,
        )
        return "pinned"

    async def _resolve_target(
        self,
        channel_id: int | None,
        chat_id: str | None,
    ) -> _ResolvedTarget:
        if channel_id is None and not chat_id:
            raise AppError(
                "Выберите сохраненный канал или укажите chat_id вручную.",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        if channel_id is not None:
            channel = await self.repository.get_active_channel_by_id(channel_id)
            if channel is None:
                raise AppError("Канал не найден.", status.HTTP_404_NOT_FOUND)
            return _ResolvedTarget(channel_id=channel.id, chat_id=channel.chat_id)
        assert chat_id is not None
        return _ResolvedTarget(channel_id=None, chat_id=validate_channel_chat_id(chat_id))

    async def _get_channel_or_404(self, channel_id: int) -> TelegramChannel:
        channel = await self.repository.get_channel_by_id(channel_id)
        if channel is None:
            raise AppError("Канал не найден.", status.HTTP_404_NOT_FOUND)
        return channel

    def _button_url(self) -> str:
        config = self.get_config()
        return config.mini_app_direct_url

    def _load_channel_entry_photos(self, photo_paths: list[str]) -> list[TelegramPhotoUpload]:
        photos: list[TelegramPhotoUpload] = []
        for raw_path in photo_paths:
            path = raw_path.strip()
            if not path.startswith(CHANNEL_ENTRY_PHOTO_FOLDER):
                raise AppError(
                    "РќРµРІРµСЂРЅС‹Р№ РїСѓС‚СЊ С„РѕС‚Рѕ РґР»СЏ РїСѓР±Р»РёРєР°С†РёРё.",
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                )
            try:
                content = self.storage.read_bytes(path)
            except FileNotFoundError as exc:
                raise AppError(
                    "Р¤РѕС‚Рѕ РґР»СЏ РїСѓР±Р»РёРєР°С†РёРё РЅРµ РЅР°Р№РґРµРЅРѕ.",
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                ) from exc
            mime_type = mimetypes.guess_type(path)[0] or "image/jpeg"
            photos.append(
                TelegramPhotoUpload(
                    content=content,
                    filename=Path(path).name or "channel-entry-photo.jpg",
                    mime_type=mime_type,
                )
            )
        return photos

    async def _audit_message(
        self,
        *,
        actor: User,
        action: str,
        message: TelegramChannelEntryMessage,
    ) -> None:
        await self.audit_service.record_action(
            actor_user_id=actor.id,
            action=action,
            entity_type="telegram_channel_entry_message",
            entity_id=message.id,
            after_data=self.audit_service.snapshot(message, MESSAGE_AUDIT_FIELDS),
            metadata={"bot": "customer_bot_1"},
            commit=False,
        )

    async def _flush_if_supported(self) -> None:
        flush = getattr(self.session, "flush", None)
        if callable(flush):
            await flush()

    async def _refresh_if_supported(self, instance: object) -> None:
        refresh = getattr(self.session, "refresh", None)
        if callable(refresh):
            await refresh(instance)

    async def _commit(self, error_message: str) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(error_message, status.HTTP_409_CONFLICT) from exc

    def _now(self) -> datetime:
        return self.now_factory()


class _ResolvedTarget:
    def __init__(self, *, channel_id: int | None, chat_id: str) -> None:
        self.channel_id = channel_id
        self.chat_id = chat_id


def validate_channel_chat_id(value: str) -> str:
    chat_id = value.strip()
    if USERNAME_CHAT_ID_RE.fullmatch(chat_id) or NUMERIC_CHANNEL_CHAT_ID_RE.fullmatch(chat_id):
        return chat_id
    raise AppError(
        "Неверный chat_id. Используйте @username или -100... numeric id.",
        status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


def normalize_bot_username(value: str | None) -> str:
    username = (value or "").strip().lstrip("@")
    if not username:
        raise AppError(
            "Не настроен TELEGRAM_CUSTOMER_BOT_USERNAME.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if BOT_USERNAME_RE.fullmatch(username) is None:
        raise AppError(
            "Неверный TELEGRAM_CUSTOMER_BOT_USERNAME.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return username


def normalize_short_name(value: str | None) -> str:
    return (value or "").strip().strip("/")


def build_mini_app_direct_url(
    *,
    bot_username: str | None = None,
    short_name: str | None = None,
    start_param: str | None = None,
) -> str:
    username = normalize_bot_username(
        bot_username if bot_username is not None else settings.telegram_customer_bot_username
    )
    normalized_short_name = normalize_short_name(
        short_name if short_name is not None else settings.telegram_mini_app_short_name
    )
    normalized_start_param = (
        start_param
        if start_param is not None
        else settings.telegram_channel_entry_start_param
    ).strip()
    if not normalized_start_param:
        normalized_start_param = "channel_pin"

    encoded_start_param = quote(normalized_start_param, safe="")
    if normalized_short_name:
        return (
            f"https://t.me/{username}/{quote(normalized_short_name, safe='')}"
            f"?startapp={encoded_start_param}"
        )
    return f"https://t.me/{username}?startapp={encoded_start_param}"


def sanitize_telegram_error(
    error: TelegramDeliveryError,
    *,
    operation: str | None = None,
) -> str:
    raw_message = str(error) or "Telegram API error"
    lowered = raw_message.lower()
    if error.error_code == "configuration_error" or "token is not configured" in lowered:
        return "Не настроен TELEGRAM_CUSTOMER_BOT_TOKEN."
    if "chat not found" in lowered or "channel not found" in lowered:
        return "Канал не найден. Проверьте @username или chat_id."
    if "invalid chat_id" in lowered or "bad chat id" in lowered:
        return "Неверный chat_id."
    if "bot is not a member" in lowered or "not enough rights to get member" in lowered:
        return "Бот не добавлен в канал."
    if "not an administrator" in lowered or "need administrator" in lowered:
        return "Бот не является администратором канала."
    if operation == "pin" or "pin" in lowered:
        if "not enough rights" in lowered or "can't pin" in lowered or "have no rights" in lowered:
            return "Недостаточно прав для закрепления."
    if operation == "publish" or "send" in lowered or "post" in lowered:
        if "not enough rights" in lowered or "can't send" in lowered or "have no rights" in lowered:
            return "Недостаточно прав для публикации."
    if "forbidden" in lowered:
        return "Бот не добавлен в канал."
    if "bad request" in lowered:
        return "Telegram отклонил запрос. Проверьте канал и права Bot 1."

    message = raw_message
    for secret in (
        settings.telegram_customer_bot_token,
        settings.telegram_bot_token,
        settings.telegram_webapp_bot_token,
    ):
        if secret:
            message = message.replace(secret, "[redacted]")
    message = re.sub(r"https://api\.telegram\.org/[^\s]+", "[telegram-api-url]", message)
    return " ".join(message.split())[:TELEGRAM_ERROR_MESSAGE_MAX_LENGTH]


def _estimate_member_rights(
    member: dict[str, object],
) -> tuple[bool | None, bool | None, str, bool]:
    status_value = str(member.get("status") or "")
    if status_value == "creator":
        return (
            True,
            True,
            "Bot 1 является владельцем канала и может публиковать и закреплять.",
            True,
        )
    if status_value != "administrator":
        return False, False, "Бот не является администратором канала.", False

    can_post = member.get("can_post_messages")
    can_pin = member.get("can_pin_messages")
    can_post_estimate = can_post if isinstance(can_post, bool) else None
    can_pin_estimate = can_pin if isinstance(can_pin, bool) else None
    if can_post_estimate is False:
        return can_post_estimate, can_pin_estimate, "Недостаточно прав для публикации.", False
    if can_pin_estimate is False:
        return can_post_estimate, can_pin_estimate, "Недостаточно прав для закрепления.", False
    return (
        can_post_estimate,
        can_pin_estimate,
        "Bot 1 добавлен и похож на администратора канала.",
        True,
    )


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _mini_app_url_for_display() -> str:
    return f"{settings.public_mini_app_base_url.rstrip('/')}/"
