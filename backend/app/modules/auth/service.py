import logging
from typing import Any

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.core.security import create_access_token
from app.db.models import User
from app.modules.auth.schemas import TokenResponse
from app.modules.auth.telegram import TelegramInitDataError, validate_telegram_init_data
from app.modules.customer_notifications.repository import CustomerNotificationsRepository
from app.modules.users.repository import UsersRepository

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users_repository = UsersRepository(session)
        self.customer_notifications_repository = CustomerNotificationsRepository(session)

    async def login_with_telegram(self, init_data: str) -> TokenResponse:
        bot_token = settings.telegram_webapp_bot_token or settings.telegram_bot_token
        if not bot_token:
            raise AppError(
                "Telegram authentication is not configured",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            telegram_payload = validate_telegram_init_data(
                init_data,
                bot_token,
                max_age_seconds=settings.telegram_auth_max_age_seconds,
            )
        except TelegramInitDataError as exc:
            raise AppError(
                "Invalid Telegram authentication data",
                status.HTTP_401_UNAUTHORIZED,
            ) from exc

        user_payload = telegram_payload.get("user")
        if not isinstance(user_payload, dict):
            raise AppError("Telegram user payload is missing", status.HTTP_401_UNAUTHORIZED)

        user = await self._upsert_user_from_telegram(user_payload)
        await self._link_customer_subscription(user)
        access_token = create_access_token(
            subject=str(user.id),
            additional_claims={"role": user.role.value},
        )
        return TokenResponse(access_token=access_token, user=user)

    async def _upsert_user_from_telegram(self, telegram_user: dict[str, Any]) -> User:
        telegram_id = telegram_user.get("id")
        if not isinstance(telegram_id, int):
            raise AppError("Telegram user id is missing", status.HTTP_401_UNAUTHORIZED)

        user = await self.users_repository.get_by_telegram_id(telegram_id)
        if user is None:
            user = User(telegram_id=telegram_id)
            self.users_repository.add(user)

        user.username = _optional_str(telegram_user.get("username"))
        user.first_name = _optional_str(telegram_user.get("first_name"))
        user.last_name = _optional_str(telegram_user.get("last_name"))
        user.phone = _optional_str(telegram_user.get("phone") or telegram_user.get("phone_number"))

        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

        return user

    async def _link_customer_subscription(self, user: User) -> None:
        try:
            existing = await self.customer_notifications_repository.get_by_user_id(user.id)
            if existing is not None:
                return
            subscription = (
                await self.customer_notifications_repository.link_unlinked_subscription_to_user(
                    user_id=user.id,
                    telegram_user_id=user.telegram_id,
                )
            )
            if subscription is None or subscription.user_id != user.id:
                return
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            logger.warning(
                "customer notification subscription auto-link conflict",
                extra={"user_id": user.id, "telegram_user_id": user.telegram_id},
            )
        except Exception:
            await self.session.rollback()
            logger.warning(
                "customer notification subscription auto-link failed",
                extra={"user_id": user.id, "telegram_user_id": user.telegram_id},
                exc_info=True,
            )


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
