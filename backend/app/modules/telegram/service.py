import httpx

from app.core.config import settings


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
