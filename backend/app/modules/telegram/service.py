import logging
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core.config import settings
from app.core.errors import AppError
from app.modules.seller_auth.callbacks import parse_seller_registration_callback_data
from app.modules.seller_auth.schemas import SellerTelegramStartRequest
from app.modules.telegram.schemas import SellerBotWebhookResponse, TelegramUpdate

SELLER_START_PREFIX = "seller_"
START_COMMAND_RE = re.compile(
    r"^/start(?:@[A-Za-z0-9_]{5,32})?(?:\s+(?P<payload>\S+))?",
    re.IGNORECASE,
)
COMMAND_RE = re.compile(
    r"^(?P<command>/[A-Za-z_]+)(?:@[A-Za-z0-9_]{5,32})?(?:\s+(?P<args>[\s\S]*))?$"
)
SELLER_ID_RE = re.compile(r"^[0-9]+$")
POSTGRES_INT32_MAX = 2_147_483_647
TELEGRAM_ID_HINT_MAX = 20_000_000_000
TELEGRAM_ID_GUIDANCE_MESSAGE = (
    "Похоже, вы указали Telegram ID. Используйте Seller ID из /sellers, например #5."
)
SELLER_ID_RANGE_MESSAGE = (
    "Seller ID is outside the supported range. Get Seller ID with /sellers."
)
INVALID_START_MESSAGE = (
    "Откройте регистрацию в Seller Panel и отправьте Bot 2 команду /start seller_<token>."
)
PRIVATE_CHAT_REQUIRED_MESSAGE = (
    "Откройте Bot 2 в личном чате и отправьте команду регистрации из Seller Panel."
)
MISSING_USER_MESSAGE = "Не удалось прочитать Telegram аккаунт. Откройте Bot 2 заново."

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TelegramDownloadedFile:
    content: bytes
    file_path: str
    original_filename: str
    mime_type: str | None
    extension: str


class TelegramDeliveryError(Exception):
    """Raised when Telegram Bot API delivery fails."""

    def __init__(
        self,
        message: str,
        *,
        error_code: int | str | None = None,
        status_code: int | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds


class TelegramService:
    """Telegram Bot API integration for seller notifications."""

    def __init__(
        self,
        *,
        bot_token: str | None = None,
        seller_chat_id: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.bot_token = bot_token if bot_token is not None else settings.telegram_bot_token
        self.seller_chat_id = (
            seller_chat_id if seller_chat_id is not None else settings.telegram_seller_chat_id
        )
        self.timeout_seconds = timeout_seconds

    async def send_seller_notification(self, message: str) -> None:
        if not self.bot_token or not self.seller_chat_id:
            raise TelegramDeliveryError("Telegram seller notification is not configured")

        await self.send_message(self.seller_chat_id, message)

    async def send_seller_photo(self, photo: str, *, caption: str | None = None) -> None:
        if not self.bot_token or not self.seller_chat_id:
            raise TelegramDeliveryError("Telegram seller notification is not configured")

        await self.send_photo(self.seller_chat_id, photo, caption=caption)

    async def send_message(
        self,
        chat_id: str,
        message: str,
        *,
        parse_mode: str | None = None,
        reply_markup: dict[str, object] | None = None,
    ) -> int | None:
        payload: dict[str, object] = {
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        body = await self._post("sendMessage", payload)
        if not body.get("ok", False):
            raise self._delivery_error_from_body(body)
        result = body.get("result")
        if not isinstance(result, dict):
            return None
        message_id = result.get("message_id")
        return int(message_id) if isinstance(message_id, int) else None

    async def send_photo(
        self,
        chat_id: str,
        photo: str,
        *,
        caption: str | None = None,
        parse_mode: str | None = None,
        reply_markup: dict[str, object] | None = None,
    ) -> int | None:
        payload: dict[str, object] = {
            "chat_id": chat_id,
            "photo": photo,
        }
        if caption:
            payload["caption"] = caption
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        body = await self._post("sendPhoto", payload)
        if not body.get("ok", False):
            raise self._delivery_error_from_body(body)
        result = body.get("result")
        if not isinstance(result, dict):
            return None
        message_id = result.get("message_id")
        return int(message_id) if isinstance(message_id, int) else None

    async def get_file(self, file_id: str) -> dict[str, object]:
        body = await self._post("getFile", {"file_id": file_id})
        if not body.get("ok", False):
            raise self._delivery_error_from_body(body)
        result = body.get("result")
        if not isinstance(result, dict):
            raise TelegramDeliveryError("Telegram API returned invalid file metadata")
        return result

    async def download_file(self, file_id: str) -> TelegramDownloadedFile:
        if not self.bot_token:
            raise TelegramDeliveryError(
                "Telegram bot token is not configured",
                error_code="configuration_error",
            )

        file_metadata = await self.get_file(file_id)
        file_path_value = file_metadata.get("file_path")
        if not isinstance(file_path_value, str) or not file_path_value.strip():
            raise TelegramDeliveryError("Telegram API returned invalid file path")

        url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path_value}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url)
        except httpx.HTTPError as exc:
            raise TelegramDeliveryError(
                "Telegram file download failed",
                error_code="request_failed",
            ) from exc
        if response.status_code >= 400:
            raise TelegramDeliveryError(
                f"Telegram file download returned HTTP {response.status_code}",
                status_code=response.status_code,
            )

        original_filename = Path(file_path_value).name or f"{file_id}.jpg"
        extension = Path(original_filename).suffix.lower() or ".jpg"
        return TelegramDownloadedFile(
            content=response.content,
            file_path=file_path_value,
            original_filename=original_filename[:255],
            mime_type=mimetypes.guess_type(original_filename)[0],
            extension=extension,
        )

    async def get_me(self) -> dict[str, object]:
        body = await self._post("getMe", {})
        if not body.get("ok", False):
            raise self._delivery_error_from_body(body)
        result = body.get("result")
        if not isinstance(result, dict):
            raise TelegramDeliveryError("Telegram API returned invalid bot profile")
        return {
            "id": result.get("id"),
            "username": result.get("username"),
            "first_name": result.get("first_name"),
            "can_join_groups": result.get("can_join_groups"),
            "can_read_all_group_messages": result.get("can_read_all_group_messages"),
            "supports_inline_queries": result.get("supports_inline_queries"),
        }

    async def answer_callback_query(
        self,
        callback_query_id: str,
        *,
        text: str | None = None,
    ) -> None:
        payload: dict[str, object] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        body = await self._post("answerCallbackQuery", payload)
        if not body.get("ok", False):
            raise self._delivery_error_from_body(body)

    async def set_webhook(
        self,
        url: str,
        *,
        secret_token: str | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {"url": url}
        if secret_token:
            payload["secret_token"] = secret_token
        body = await self._post("setWebhook", payload)
        if not body.get("ok", False):
            raise self._delivery_error_from_body(body)
        return body

    async def get_webhook_info(self) -> dict[str, object]:
        body = await self._post("getWebhookInfo", {})
        if not body.get("ok", False):
            raise self._delivery_error_from_body(body)
        result = body.get("result")
        if not isinstance(result, dict):
            raise TelegramDeliveryError("Telegram API returned invalid webhook info")
        return result

    async def _post(self, method: str, payload: dict[str, object]) -> dict[str, object]:
        if not self.bot_token:
            raise TelegramDeliveryError(
                "Telegram bot token is not configured",
                error_code="configuration_error",
            )

        url = f"https://api.telegram.org/bot{self.bot_token}/{method}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(url, json=payload)
        except httpx.HTTPError as exc:
            raise TelegramDeliveryError(
                "Telegram API request failed",
                error_code="request_failed",
            ) from exc

        if response.status_code >= 400:
            try:
                body = response.json()
            except ValueError:
                body = None
            if isinstance(body, dict):
                raise self._delivery_error_from_body(body, status_code=response.status_code)
            raise TelegramDeliveryError(
                f"Telegram API returned HTTP {response.status_code}",
                status_code=response.status_code,
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise TelegramDeliveryError("Telegram API returned invalid JSON") from exc

        if not isinstance(body, dict):
            raise TelegramDeliveryError("Telegram API returned invalid JSON")
        return body

    def _delivery_error_from_body(
        self,
        body: dict[str, object],
        *,
        status_code: int | None = None,
    ) -> TelegramDeliveryError:
        description = str(body.get("description") or "Telegram API returned an error")
        error_code = body.get("error_code")
        retry_after_seconds = self._retry_after_seconds(body.get("parameters"))
        return TelegramDeliveryError(
            description,
            error_code=error_code if isinstance(error_code, (int, str)) else None,
            status_code=status_code,
            retry_after_seconds=retry_after_seconds,
        )

    def _retry_after_seconds(self, parameters: object) -> int | None:
        if not isinstance(parameters, dict):
            return None
        retry_after = parameters.get("retry_after")
        return retry_after if isinstance(retry_after, int) else None


class SellerBotWebhookService:
    """Telegram webhook adapter for Bot 2 seller registration updates."""

    def __init__(
        self,
        *,
        seller_auth_service,
        seller_bot_service=None,
        telegram_service: TelegramService | None = None,
    ) -> None:
        self.seller_auth_service = seller_auth_service
        self.seller_bot_service = seller_bot_service
        self.telegram_service = telegram_service or seller_auth_service.telegram_service

    async def handle_update(self, update: TelegramUpdate) -> SellerBotWebhookResponse:
        if update.callback_query is not None:
            return await self._handle_callback_query(update)

        message = update.message
        message_text = self._message_text(message)
        if message is None or message_text is None:
            return self._response(handled=False, result="unsupported_update")

        command_match = COMMAND_RE.match(message_text.strip())
        if command_match is not None:
            command = command_match.group("command").lower()
            args = (command_match.group("args") or "").strip()
            if command in {
                "/sellers",
                "/block_seller",
                "/unblock_seller",
                "/new_product",
                "/new_product_help",
            }:
                return await self._handle_seller_group_command(
                    command=command,
                    args=args,
                    update=update,
                )

        start_payload = self._extract_start_payload(message_text)
        if start_payload is None:
            return self._response(handled=False, result="ignored")

        if not start_payload.startswith(SELLER_START_PREFIX):
            await self._send_chat_message(message.chat.id, INVALID_START_MESSAGE)
            return self._response(handled=True, result="invalid_start_payload")

        if message.chat.id <= 0:
            await self._send_chat_message(message.chat.id, PRIVATE_CHAT_REQUIRED_MESSAGE)
            return self._response(handled=True, result="private_chat_required")

        if message.from_user is None:
            await self._send_chat_message(message.chat.id, MISSING_USER_MESSAGE)
            return self._response(handled=True, result="missing_telegram_user")

        payload = SellerTelegramStartRequest(
            start_payload=start_payload,
            telegram_user_id=message.from_user.id,
            telegram_chat_id=message.chat.id,
            telegram_username=message.from_user.username,
            telegram_first_name=message.from_user.first_name,
            telegram_last_name=message.from_user.last_name,
        )
        try:
            await self.seller_auth_service.handle_telegram_start(payload)
        except AppError as exc:
            await self._send_chat_message(message.chat.id, self._registration_error_message(exc))
            return self._response(handled=True, result="registration_error")

        return self._response(handled=True, result="registration_linked")

    async def _handle_callback_query(
        self,
        update: TelegramUpdate,
    ) -> SellerBotWebhookResponse:
        callback_query = update.callback_query
        if callback_query is None or not callback_query.data:
            return self._response(handled=False, result="unsupported_callback")
        if callback_query.message is None:
            return self._response(handled=False, result="callback_without_message")
        if not self._is_seller_group_chat(callback_query.message.chat.id):
            await self._send_chat_message(
                callback_query.message.chat.id,
                "Seller registration approval is available only in the seller group.",
            )
            return self._response(handled=True, result="approval_rejected_outside_seller_group")

        try:
            action, registration_id = parse_seller_registration_callback_data(callback_query.data)
            if action == "approve":
                await self.seller_auth_service.approve_registration(
                    registration_id=registration_id,
                    actor_telegram_user_id=callback_query.from_user.id,
                    actor_username=callback_query.from_user.username,
                )
                return self._response(handled=True, result="registration_approved")
            await self.seller_auth_service.reject_registration(
                registration_id=registration_id,
                actor_telegram_user_id=callback_query.from_user.id,
                actor_username=callback_query.from_user.username,
            )
            return self._response(handled=True, result="registration_rejected")
        except AppError as exc:
            await self._send_chat_message(
                callback_query.message.chat.id,
                self._registration_error_message(exc),
            )
            return self._response(handled=True, result="registration_callback_error")

    async def _handle_seller_group_command(
        self,
        *,
        command: str,
        args: str,
        update: TelegramUpdate,
    ) -> SellerBotWebhookResponse:
        message = update.message
        if message is None:
            return self._response(handled=False, result="unsupported_update")
        if self.seller_bot_service is None:
            await self._send_chat_message(
                message.chat.id,
                "Seller bot commands are not configured.",
            )
            return self._response(handled=True, result="seller_bot_commands_unconfigured")

        try:
            if command == "/sellers":
                response_text = await self.seller_bot_service.format_sellers_command(
                    chat_id=message.chat.id,
                )
                await self._send_chat_message(message.chat.id, response_text)
                return self._response(handled=True, result="sellers_list_sent")

            actor_user = message.from_user
            if command == "/new_product_help":
                response_text = self.seller_bot_service.format_new_product_help_command(
                    chat_id=message.chat.id,
                )
                await self._send_chat_message(
                    message.chat.id,
                    response_text,
                    parse_mode="HTML",
                )
                return self._response(handled=True, result="new_product_help_sent")

            if command == "/new_product":
                response_text = await self.seller_bot_service.create_quick_product_draft_command(
                    chat_id=message.chat.id,
                    message=message,
                    actor_telegram_user_id=actor_user.id if actor_user is not None else None,
                    actor_username=actor_user.username if actor_user is not None else None,
                )
                await self._send_chat_message(message.chat.id, response_text)
                return self._response(handled=True, result="bot_product_draft_created")

            target_user_id = self._parse_seller_id_arg(args, command=command)
            if command == "/block_seller":
                response_text = await self.seller_bot_service.block_seller_command(
                    chat_id=message.chat.id,
                    target_user_id=target_user_id,
                    actor_telegram_user_id=actor_user.id if actor_user is not None else None,
                    actor_username=actor_user.username if actor_user is not None else None,
                )
                await self._send_chat_message(message.chat.id, response_text)
                return self._response(handled=True, result="seller_blocked")

            response_text = await self.seller_bot_service.unblock_seller_command(
                chat_id=message.chat.id,
                target_user_id=target_user_id,
                actor_telegram_user_id=actor_user.id if actor_user is not None else None,
                actor_username=actor_user.username if actor_user is not None else None,
            )
            await self._send_chat_message(message.chat.id, response_text)
            return self._response(handled=True, result="seller_unblocked")
        except AppError as exc:
            error_message = (
                self._product_creation_error_message(exc.message)
                if command == "/new_product"
                else exc.message
            )
            await self._send_chat_message(message.chat.id, error_message)
            result = (
                "bot_product_post_rejected"
                if command == "/new_product"
                else "seller_command_error"
            )
            return self._response(handled=True, result=result)
        except Exception:
            if command != "/new_product":
                raise
            logger.exception("Unexpected Bot 2 product creation failure")
            await self._send_chat_message(
                message.chat.id,
                self._product_creation_error_message(
                    "внутренняя ошибка. Товар не создан; повтори попытку позже.",
                ),
            )
            return self._response(handled=True, result="bot_product_post_rejected")

    def _extract_start_payload(self, text: str) -> str | None:
        match = START_COMMAND_RE.match(text.strip())
        if match is None:
            return None
        payload = match.group("payload")
        return payload.strip() if payload else ""

    def _product_creation_error_message(self, detail: str) -> str:
        return (
            "Не удалось создать товар.\n\n"
            f"Ошибка: {detail}\n\n"
            "Проверь формат через /new_product_help. Товар не был сохранён."
        )

    async def _send_chat_message(
        self,
        chat_id: int,
        message: str,
        *,
        parse_mode: str | None = None,
    ) -> bool:
        try:
            await self.telegram_service.send_message(
                str(chat_id),
                message,
                parse_mode=parse_mode,
            )
        except TelegramDeliveryError:
            return False
        return True

    def _is_seller_group_chat(self, chat_id: int) -> bool:
        seller_chat_id = settings.telegram_seller_chat_id
        return bool(seller_chat_id and str(chat_id) == seller_chat_id.strip())

    def _parse_seller_id_arg(self, args: str, *, command: str) -> int:
        seller_id_text = args.strip()
        usage_message = f"Usage: {command} <Seller ID>. Get Seller ID with /sellers."
        if not seller_id_text or SELLER_ID_RE.fullmatch(seller_id_text) is None:
            raise AppError(usage_message, 400)

        seller_id = int(seller_id_text)
        if seller_id <= 0:
            raise AppError(usage_message, 400)
        if seller_id > POSTGRES_INT32_MAX:
            if seller_id <= TELEGRAM_ID_HINT_MAX:
                raise AppError(TELEGRAM_ID_GUIDANCE_MESSAGE, 400)
            raise AppError(SELLER_ID_RANGE_MESSAGE, 400)
        return seller_id

    def _message_text(self, message: object | None) -> str | None:
        if message is None:
            return None
        text = getattr(message, "text", None) or getattr(message, "caption", None)
        return text if isinstance(text, str) else None

    def _registration_error_message(self, exc: AppError) -> str:
        message = exc.message.lower()
        if "expired" in message:
            return "Ссылка регистрации истекла. Начните регистрацию заново в Seller Panel."
        if "already used" in message:
            return "Эта ссылка уже использована. Если код не пришел, нажмите Resend code."
        if "username" in message:
            return (
                "Telegram username не совпадает с регистрацией. "
                "Откройте Bot 2 из аккаунта, указанного в Seller Panel."
            )
        if "awaiting approval" in message:
            return "Регистрация продавца уже ожидает подтверждения."
        if "already approved" in message or "already verified" in message:
            return "Регистрация продавца уже обработана."
        if "rejected" in message:
            return "Регистрация продавца уже отклонена."
        if "invalid approval callback" in message:
            return "Недействительная кнопка подтверждения регистрации."
        return "Ссылка регистрации недействительна. Начните регистрацию заново в Seller Panel."

    def _response(self, *, handled: bool, result: str) -> SellerBotWebhookResponse:
        return SellerBotWebhookResponse(handled=handled, result=result)
