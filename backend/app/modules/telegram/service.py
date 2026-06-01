import re

import httpx

from app.core.config import settings
from app.core.errors import AppError
from app.modules.seller_auth.schemas import SellerTelegramStartRequest
from app.modules.telegram.schemas import SellerBotWebhookResponse, TelegramUpdate

SELLER_START_PREFIX = "seller_"
START_COMMAND_RE = re.compile(
    r"^/start(?:@[A-Za-z0-9_]{5,32})?(?:\s+(?P<payload>\S+))?",
    re.IGNORECASE,
)
INVALID_START_MESSAGE = (
    "Откройте регистрацию в Seller Panel и отправьте Bot 2 команду /start seller_<token>."
)
PRIVATE_CHAT_REQUIRED_MESSAGE = (
    "Откройте Bot 2 в личном чате и отправьте команду регистрации из Seller Panel."
)
MISSING_USER_MESSAGE = "Не удалось прочитать Telegram аккаунт. Откройте Bot 2 заново."


class TelegramDeliveryError(Exception):
    """Raised when Telegram Bot API delivery fails."""


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

    async def send_message(self, chat_id: str, message: str) -> None:
        payload = {"chat_id": chat_id, "text": message, "disable_web_page_preview": True}
        body = await self._post("sendMessage", payload)
        if not body.get("ok", False):
            description = str(body.get("description") or "Telegram API returned an error")
            raise TelegramDeliveryError(description)

    async def get_me(self) -> dict[str, object]:
        body = await self._post("getMe", {})
        if not body.get("ok", False):
            description = str(body.get("description") or "Telegram API returned an error")
            raise TelegramDeliveryError(description)
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
            description = str(body.get("description") or "Telegram API returned an error")
            raise TelegramDeliveryError(description)
        return body

    async def get_webhook_info(self) -> dict[str, object]:
        body = await self._post("getWebhookInfo", {})
        if not body.get("ok", False):
            description = str(body.get("description") or "Telegram API returned an error")
            raise TelegramDeliveryError(description)
        result = body.get("result")
        if not isinstance(result, dict):
            raise TelegramDeliveryError("Telegram API returned invalid webhook info")
        return result

    async def _post(self, method: str, payload: dict[str, object]) -> dict[str, object]:
        if not self.bot_token:
            raise TelegramDeliveryError("Telegram bot token is not configured")

        url = f"https://api.telegram.org/bot{self.bot_token}/{method}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(url, json=payload)
        except httpx.HTTPError as exc:
            raise TelegramDeliveryError("Telegram API request failed") from exc

        if response.status_code >= 400:
            raise TelegramDeliveryError(f"Telegram API returned HTTP {response.status_code}")

        try:
            body = response.json()
        except ValueError as exc:
            raise TelegramDeliveryError("Telegram API returned invalid JSON") from exc

        if not isinstance(body, dict):
            raise TelegramDeliveryError("Telegram API returned invalid JSON")
        return body


class SellerBotWebhookService:
    """Telegram webhook adapter for Bot 2 seller registration updates."""

    def __init__(
        self,
        *,
        seller_auth_service,
        telegram_service: TelegramService | None = None,
    ) -> None:
        self.seller_auth_service = seller_auth_service
        self.telegram_service = telegram_service or seller_auth_service.telegram_service

    async def handle_update(self, update: TelegramUpdate) -> SellerBotWebhookResponse:
        message = update.message
        if message is None or message.text is None:
            return self._response(handled=False, result="unsupported_update")

        start_payload = self._extract_start_payload(message.text)
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

    def _extract_start_payload(self, text: str) -> str | None:
        match = START_COMMAND_RE.match(text.strip())
        if match is None:
            return None
        payload = match.group("payload")
        return payload.strip() if payload else ""

    async def _send_chat_message(self, chat_id: int, message: str) -> bool:
        try:
            await self.telegram_service.send_message(str(chat_id), message)
        except TelegramDeliveryError:
            return False
        return True

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
        return "Ссылка регистрации недействительна. Начните регистрацию заново в Seller Panel."

    def _response(self, *, handled: bool, result: str) -> SellerBotWebhookResponse:
        return SellerBotWebhookResponse(handled=handled, result=result)
