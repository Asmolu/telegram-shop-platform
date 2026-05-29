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

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.seller_chat_id,
            "text": message,
            "disable_web_page_preview": True,
        }

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

        if not body.get("ok", False):
            description = str(body.get("description") or "Telegram API returned an error")
            raise TelegramDeliveryError(description)
