from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import NotificationChannel
from app.modules.audit.service import AuditService
from app.modules.notifications.schemas import NotificationList
from app.modules.notifications.service import NotificationsService
from app.modules.seller_bot.schemas import (
    SellerBotActionResponse,
    SellerBotBroadcastRequest,
    SellerBotMessageRequest,
    SellerBotStatusResponse,
)
from app.modules.telegram.service import TelegramDeliveryError, TelegramService

SELLER_BOT_TEST_MESSAGE = "seller_bot.test_message"
SELLER_BOT_BROADCAST = "seller_bot.broadcast"


class SellerBotService:
    """Seller bot status, test message, and seller-chat broadcast logic."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        telegram_service: TelegramService | None = None,
        notifications_service: NotificationsService | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self.session = session
        self.telegram_service = telegram_service or TelegramService()
        self.notifications_service = notifications_service or NotificationsService(
            session,
            telegram_service=self.telegram_service,
        )
        self.audit_service = audit_service or AuditService(session)

    async def get_status(self) -> SellerBotStatusResponse:
        configured = bool(settings.telegram_bot_token)
        seller_chat_configured = bool(settings.telegram_seller_chat_id)
        if not configured:
            return SellerBotStatusResponse(
                configured=False,
                seller_chat_configured=seller_chat_configured,
                ok=False,
                error="Telegram bot token is not configured",
            )

        try:
            bot = await self.telegram_service.get_me()
        except TelegramDeliveryError as exc:
            return SellerBotStatusResponse(
                configured=True,
                seller_chat_configured=seller_chat_configured,
                ok=False,
                error=str(exc),
            )

        return SellerBotStatusResponse(
            configured=True,
            seller_chat_configured=seller_chat_configured,
            ok=True,
            bot=bot,
        )

    async def send_test_message(
        self,
        *,
        payload: SellerBotMessageRequest,
        actor_user_id: int,
    ) -> SellerBotActionResponse:
        notification = await self.notifications_service.send_seller_telegram_message(
            type=SELLER_BOT_TEST_MESSAGE,
            title="Seller bot test message",
            message=payload.message,
            payload={"target": "seller_notification_chat"},
        )
        await self._audit(
            actor_user_id=actor_user_id,
            action=SELLER_BOT_TEST_MESSAGE,
            notification_id=notification.id,
            message_length=len(payload.message),
        )
        return SellerBotActionResponse(
            notification_id=notification.id,
            status=notification.status.value,
            message=notification.message,
        )

    async def broadcast(
        self,
        *,
        payload: SellerBotBroadcastRequest,
        actor_user_id: int,
    ) -> SellerBotActionResponse:
        notification = await self.notifications_service.send_seller_telegram_message(
            type=SELLER_BOT_BROADCAST,
            title="Seller notification chat broadcast",
            message=payload.message,
            payload={"target": "seller_notification_chat"},
        )
        await self._audit(
            actor_user_id=actor_user_id,
            action=SELLER_BOT_BROADCAST,
            notification_id=notification.id,
            message_length=len(payload.message),
        )
        return SellerBotActionResponse(
            notification_id=notification.id,
            status=notification.status.value,
            message=notification.message,
        )

    async def list_messages(self, *, limit: int, offset: int) -> NotificationList:
        return await self.notifications_service.list_notifications(
            limit=limit,
            offset=offset,
            channel=NotificationChannel.TELEGRAM,
        )

    async def _audit(
        self,
        *,
        actor_user_id: int,
        action: str,
        notification_id: int,
        message_length: int,
    ) -> None:
        await self.audit_service.record_action(
            actor_user_id=actor_user_id,
            action=action,
            entity_type="seller_bot",
            entity_id=notification_id,
            after_data={
                "notification_id": notification_id,
                "target": "seller_notification_chat",
                "message_length": message_length,
            },
            commit=True,
        )
