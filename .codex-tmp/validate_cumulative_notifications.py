import asyncio
import os

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import CustomerInAppNotification, Look, Order
from app.modules.customer_in_app_notifications.service import CustomerInAppNotificationsService


async def main() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        counts = {
            table: await session.scalar(text(f"SELECT count(*) FROM {table}"))
            for table in (
                "users",
                "products",
                "product_variants",
                "looks",
                "orders",
                "manual_payments",
                "return_requests",
                "seller_payment_settings",
                "customer_in_app_notifications",
            )
        }
        assert counts == {
            "users": 1,
            "products": 1,
            "product_variants": 1,
            "looks": 1,
            "orders": 3,
            "manual_payments": 2,
            "return_requests": 1,
            "seller_payment_settings": 1,
            "customer_in_app_notifications": 0,
        }
        look = await session.get(Look, 5601)
        assert look is not None
        assert look.image_badge_type.value == "none"
        assert look.image_badge_text is None
        assert look.image_badge_color is None
        assert look.image_badge_position is None

    async with sessions() as session:
        service = CustomerInAppNotificationsService(session)
        first = await service.pending(user_id=5601, limit=20)
        second = await service.pending(user_id=5601, limit=20)
        assert len(first) == len(second) == 1
        assert first[0].id == second[0].id
        assert await session.scalar(
            select(func.count(CustomerInAppNotification.id)).where(
                CustomerInAppNotification.source_key == "payment:5603:APPROVED"
            )
        ) == 1
        assert await session.scalar(
            select(CustomerInAppNotification.id).where(
                CustomerInAppNotification.source_key == "payment:5602:APPROVED"
            )
        ) is None
        seen = await service.mark_seen(notification_id=first[0].id, user_id=5601)
        assert seen.seen_at is not None

    async with sessions() as session:
        assert await session.scalar(
            select(Order.payment_success_banner_seen_at).where(Order.id == 5603)
        ) is not None
        assert await session.scalar(
            select(func.count(CustomerInAppNotification.id))
        ) == 1
        assert await CustomerInAppNotificationsService(session).pending(
            user_id=5601, limit=20
        ) == []

    await engine.dispose()
    print(counts)
    print("legacy-approved compatibility: seen suppressed, unseen converted once, ack coordinated")


asyncio.run(main())
