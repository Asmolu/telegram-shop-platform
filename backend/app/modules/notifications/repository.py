from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Notification, NotificationChannel, NotificationStatus


class NotificationsRepository:
    """Database access layer for notifications."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, notification: Notification) -> None:
        self.session.add(notification)

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        channel: NotificationChannel | None = None,
        status: NotificationStatus | None = None,
        user_id: int | None = None,
    ) -> tuple[list[Notification], int]:
        conditions = []
        if channel is not None:
            conditions.append(Notification.channel == channel)
        if status is not None:
            conditions.append(Notification.status == status)
        if user_id is not None:
            conditions.append(Notification.user_id == user_id)

        notifications_query = (
            select(Notification)
            .where(*conditions)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(limit)
            .offset(offset)
        )
        count_query = select(func.count(Notification.id)).where(*conditions)

        notifications_result = await self.session.execute(notifications_query)
        count_result = await self.session.execute(count_query)
        return list(notifications_result.scalars().all()), count_result.scalar_one()

    async def get_by_id(self, notification_id: int) -> Notification | None:
        result = await self.session.execute(
            select(Notification).where(Notification.id == notification_id)
        )
        return result.scalar_one_or_none()

    async def get_by_source(self, *, event_id: UUID, consumer: str) -> Notification | None:
        result = await self.session.execute(
            select(Notification).where(
                Notification.source_event_id == event_id,
                Notification.source_consumer == consumer,
            )
        )
        return result.scalar_one_or_none()
