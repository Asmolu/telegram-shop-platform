from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    CustomerServiceNotificationDelivery,
    CustomerServiceNotificationDeliveryStatus,
    CustomerTelegramSubscription,
)


class CustomerNotificationsRepository:
    """Database access for Bot 1 customer subscriptions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, subscription: CustomerTelegramSubscription) -> None:
        self.session.add(subscription)

    def add_delivery(self, delivery: CustomerServiceNotificationDelivery) -> None:
        self.session.add(delivery)

    async def get_by_id(self, subscription_id: int) -> CustomerTelegramSubscription | None:
        return await self.session.get(CustomerTelegramSubscription, subscription_id)

    async def get_by_user_id(self, user_id: int) -> CustomerTelegramSubscription | None:
        result = await self.session.execute(
            select(CustomerTelegramSubscription).where(
                CustomerTelegramSubscription.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_telegram_user_id(
        self,
        telegram_user_id: int,
    ) -> CustomerTelegramSubscription | None:
        result = await self.session.execute(
            select(CustomerTelegramSubscription).where(
                CustomerTelegramSubscription.telegram_user_id == telegram_user_id
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        has_chat: bool | None = None,
        service_opt_in: bool | None = None,
        marketing_opt_in: bool | None = None,
        blocked: bool | None = None,
        user_id: int | None = None,
        telegram_username: str | None = None,
    ) -> tuple[list[CustomerTelegramSubscription], int]:
        conditions = self._filters(
            has_chat=has_chat,
            service_opt_in=service_opt_in,
            marketing_opt_in=marketing_opt_in,
            blocked=blocked,
            user_id=user_id,
            telegram_username=telegram_username,
        )
        items_result = await self.session.execute(
            select(CustomerTelegramSubscription)
            .where(*conditions)
            .order_by(
                CustomerTelegramSubscription.updated_at.desc(),
                CustomerTelegramSubscription.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        count_result = await self.session.execute(
            select(func.count(CustomerTelegramSubscription.id)).where(*conditions)
        )
        return list(items_result.scalars().all()), count_result.scalar_one()

    async def list_service_deliveries(
        self,
        *,
        limit: int,
        offset: int,
        status: CustomerServiceNotificationDeliveryStatus | None = None,
        event_name: str | None = None,
        user_id: int | None = None,
        order_id: int | None = None,
    ) -> tuple[list[CustomerServiceNotificationDelivery], int]:
        conditions: list[Any] = []
        if status is not None:
            conditions.append(CustomerServiceNotificationDelivery.status == status)
        if event_name:
            conditions.append(CustomerServiceNotificationDelivery.event_name == event_name)
        if user_id is not None:
            conditions.append(CustomerServiceNotificationDelivery.user_id == user_id)
        if order_id is not None:
            conditions.append(CustomerServiceNotificationDelivery.order_id == order_id)

        items_result = await self.session.execute(
            select(CustomerServiceNotificationDelivery)
            .where(*conditions)
            .order_by(
                CustomerServiceNotificationDelivery.created_at.desc(),
                CustomerServiceNotificationDelivery.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        count_result = await self.session.execute(
            select(func.count(CustomerServiceNotificationDelivery.id)).where(*conditions)
        )
        return list(items_result.scalars().all()), count_result.scalar_one()

    def _filters(
        self,
        *,
        has_chat: bool | None,
        service_opt_in: bool | None,
        marketing_opt_in: bool | None,
        blocked: bool | None,
        user_id: int | None,
        telegram_username: str | None,
    ) -> list[Any]:
        conditions: list[Any] = []
        if has_chat is not None:
            conditions.append(CustomerTelegramSubscription.has_chat == has_chat)
        if service_opt_in is not None:
            conditions.append(CustomerTelegramSubscription.service_opt_in == service_opt_in)
        if marketing_opt_in is not None:
            conditions.append(CustomerTelegramSubscription.marketing_opt_in == marketing_opt_in)
        if blocked is not None:
            if blocked:
                conditions.append(CustomerTelegramSubscription.blocked_at.is_not(None))
            else:
                conditions.append(CustomerTelegramSubscription.blocked_at.is_(None))
        if user_id is not None:
            conditions.append(CustomerTelegramSubscription.user_id == user_id)
        if telegram_username:
            conditions.append(
                CustomerTelegramSubscription.telegram_username.ilike(
                    f"%{telegram_username.lstrip('@')}%"
                )
            )
        return conditions
