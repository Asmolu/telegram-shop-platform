from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.db.models import NotificationChannel, UserRole
from app.modules.audit.service import AuditService
from app.modules.notifications.schemas import NotificationList
from app.modules.notifications.service import NotificationsService
from app.modules.seller_bot.repository import SellerBotRepository
from app.modules.seller_bot.schemas import (
    SellerBotActionResponse,
    SellerBotBroadcastRequest,
    SellerBotMessageRequest,
    SellerBotStatusResponse,
)
from app.modules.telegram.service import TelegramDeliveryError, TelegramService

SELLER_BOT_TEST_MESSAGE = "seller_bot.test_message"
SELLER_BOT_BROADCAST = "seller_bot.broadcast"
SELLER_BOT_BLOCK_SELLER = "seller_bot.block_seller"
SELLER_BOT_UNBLOCK_SELLER = "seller_bot.unblock_seller"
SELLER_BOT_COMMAND_LIMIT = 20
SELLER_GROUP_ONLY_MESSAGE = "Command is available only in the seller group."
POSTGRES_INT32_MAX = 2_147_483_647


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
        self.repository = SellerBotRepository(session)
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

    async def format_sellers_command(self, *, chat_id: int) -> str:
        self._require_seller_group(chat_id)
        sellers, total = await self.repository.list_sellers(limit=SELLER_BOT_COMMAND_LIMIT)
        if not sellers:
            return "No sellers found."

        lines = [f"Sellers ({len(sellers)} of {total}):"]
        for user, credential in sellers:
            username = f"@{credential.telegram_username}" if credential.telegram_username else "-"
            telegram_user_id = (
                str(credential.telegram_user_id)
                if credential.telegram_user_id is not None
                else "-"
            )
            telegram_chat_id = (
                str(credential.telegram_chat_id)
                if credential.telegram_chat_id is not None
                else "-"
            )
            active_status = "active" if user.is_active else "blocked"
            lines.append(
                "\n".join(
                    (
                        f"Seller ID for commands: {user.id}",
                        f"Email: {credential.email}",
                        f"Telegram: {username}",
                        f"Telegram user/chat: {telegram_user_id} / {telegram_chat_id}",
                        f"Role: {user.role.value}",
                        f"Status: {active_status}",
                        f"Created at: {user.created_at.isoformat()}",
                    )
                )
            )
        if total > len(sellers):
            lines.append(f"Showing first {len(sellers)} sellers. Use the API for full history.")
        lines.append(
            "\n".join(
                (
                    "Use /block_seller <Seller ID>, for example: /block_seller 5",
                    "Do not use Telegram user id/chat id.",
                )
            )
        )
        return "\n\n".join(lines)

    async def block_seller_command(
        self,
        *,
        chat_id: int,
        target_user_id: int,
        actor_telegram_user_id: int | None,
        actor_username: str | None,
    ) -> str:
        return await self._set_seller_active_state(
            chat_id=chat_id,
            target_user_id=target_user_id,
            is_active=False,
            actor_telegram_user_id=actor_telegram_user_id,
            actor_username=actor_username,
        )

    async def unblock_seller_command(
        self,
        *,
        chat_id: int,
        target_user_id: int,
        actor_telegram_user_id: int | None,
        actor_username: str | None,
    ) -> str:
        return await self._set_seller_active_state(
            chat_id=chat_id,
            target_user_id=target_user_id,
            is_active=True,
            actor_telegram_user_id=actor_telegram_user_id,
            actor_username=actor_username,
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

    async def _set_seller_active_state(
        self,
        *,
        chat_id: int,
        target_user_id: int,
        is_active: bool,
        actor_telegram_user_id: int | None,
        actor_username: str | None,
    ) -> str:
        self._require_seller_group(chat_id)
        if not 1 <= target_user_id <= POSTGRES_INT32_MAX:
            raise AppError(
                "Seller ID is outside the supported range. Get Seller ID with /sellers.",
                400,
            )
        user = await self.repository.get_seller_user(target_user_id)
        if user is None:
            raise AppError("Seller not found. Check Seller ID with /sellers.", 404)
        if user.role == UserRole.ADMIN and not is_active:
            raise AppError("ADMIN users cannot be blocked from Bot 2", 400)
        if user.is_active == is_active:
            state = "active" if is_active else "blocked"
            return f"Seller #{user.id} is already {state}."

        before_data = {
            "id": user.id,
            "role": user.role.value,
            "is_active": user.is_active,
        }
        user.is_active = is_active
        action = SELLER_BOT_UNBLOCK_SELLER if is_active else SELLER_BOT_BLOCK_SELLER
        await self.audit_service.record_action(
            actor_user_id=None,
            action=action,
            entity_type="user",
            entity_id=user.id,
            before_data=before_data,
            after_data={
                "id": user.id,
                "role": user.role.value,
                "is_active": user.is_active,
            },
            metadata={
                "actor_telegram_user_id": actor_telegram_user_id,
                "actor_username": actor_username,
                "source": "seller_bot_command",
            },
            commit=False,
        )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("Seller active state update failed", 409) from exc

        state = "unblocked" if is_active else "blocked"
        return f"Seller #{user.id} has been {state}."

    def _require_seller_group(self, chat_id: int) -> None:
        configured_chat_id = settings.telegram_seller_chat_id
        if not configured_chat_id or str(chat_id) != configured_chat_id.strip():
            raise AppError(SELLER_GROUP_ONLY_MESSAGE, 403)
