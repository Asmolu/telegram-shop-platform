from sqlalchemy import String, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import CustomerInAppNotification, ManualPayment, ManualPaymentStatus, Order


class CustomerInAppNotificationsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert_if_source_absent(
        self, notification: CustomerInAppNotification
    ) -> bool:
        """Atomically insert unless the durable transition identity already exists.

        The named conflict target is deliberately narrow: foreign-key, nullability,
        and every other integrity failure still abort the caller's transaction.
        """
        if not isinstance(self.session, AsyncSession):
            # Lightweight unit-session boundary. Real application sessions always
            # execute the PostgreSQL ON CONFLICT statement below.
            self.session.add(notification)
            return True
        result = await self.session.execute(
            pg_insert(CustomerInAppNotification)
            .values(
                user_id=notification.user_id,
                category=notification.category,
                event_code=notification.event_code,
                variant=notification.variant,
                action_mode=notification.action_mode,
                order_id=notification.order_id,
                manual_payment_id=notification.manual_payment_id,
                return_request_id=notification.return_request_id,
                title=notification.title,
                message=notification.message,
                payload=notification.payload,
                occurred_at=notification.occurred_at,
                seen_at=notification.seen_at,
                source_key=notification.source_key,
            )
            .on_conflict_do_nothing(
                constraint="uq_customer_in_app_notifications_source_key"
            )
            .returning(CustomerInAppNotification.id)
        )
        return result.scalar_one_or_none() is not None

    async def list_pending(self, *, user_id: int, limit: int) -> list[CustomerInAppNotification]:
        result = await self.session.execute(
            select(CustomerInAppNotification)
            .where(
                CustomerInAppNotification.user_id == user_id,
                CustomerInAppNotification.seen_at.is_(None),
            )
            .order_by(
                CustomerInAppNotification.occurred_at.asc(),
                CustomerInAppNotification.id.asc(),
            )
            .limit(limit)
        )
        return list(result.scalars())

    async def get_for_user(
        self, *, notification_id: int, user_id: int, for_update: bool = False
    ) -> CustomerInAppNotification | None:
        query = select(CustomerInAppNotification).where(
            CustomerInAppNotification.id == notification_id,
            CustomerInAppNotification.user_id == user_id,
        )
        if for_update:
            query = query.with_for_update()
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_source_key(self, source_key: str) -> CustomerInAppNotification | None:
        result = await self.session.execute(
            select(CustomerInAppNotification).where(
                CustomerInAppNotification.source_key == source_key
            )
        )
        return result.scalar_one_or_none()

    async def get_legacy_approved_order(self, *, user_id: int) -> Order | None:
        source_key = "payment:" + ManualPayment.id.cast(String) + ":APPROVED"
        result = await self.session.execute(
            select(Order)
            .options(selectinload(Order.manual_payment))
            .join(ManualPayment, ManualPayment.order_id == Order.id)
            .outerjoin(
                CustomerInAppNotification,
                CustomerInAppNotification.source_key == source_key,
            )
            .where(
                Order.user_id == user_id,
                Order.payment_success_banner_seen_at.is_(None),
                ManualPayment.status == ManualPaymentStatus.APPROVED,
                CustomerInAppNotification.id.is_(None),
            )
            .order_by(ManualPayment.approved_at.desc().nullslast(), Order.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
