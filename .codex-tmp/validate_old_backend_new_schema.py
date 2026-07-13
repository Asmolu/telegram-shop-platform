import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".codex-tmp" / "old-backend-159390d" / "backend"))
os.environ["OUTBOX_ENABLED"] = "false"
os.environ["MANUAL_PAYMENT_EXPIRATION_WORKER_ENABLED"] = "false"
os.environ["CUSTOMER_CAMPAIGN_WORKER_ENABLED"] = "false"

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import Look, LookStatus, Order, User
from app.main import create_app


def health() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


async def old_orm_reads_and_insert() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        assert (await session.scalars(select(User).where(User.id == 5601))).one().telegram_id
        assert (await session.scalars(select(Order).where(Order.id == 5601))).one().order_number
        assert (await session.scalars(select(Look).where(Look.id == 5601))).one().title
        old_look = Look(
            slug="old-backend-new-schema",
            title="Old backend compatible insert",
            status=LookStatus.DRAFT,
            is_listed=True,
            search_priority=1,
        )
        session.add(old_look)
        await session.commit()
        defaults = (
            await session.execute(
                text(
                    "SELECT image_badge_type::text, image_badge_text, image_badge_color::text, "
                    "image_badge_position::text FROM looks WHERE id = :id"
                ),
                {"id": old_look.id},
            )
        ).one()
        assert defaults == ("none", None, None, None)
        await session.delete(old_look)
        await session.commit()
    await engine.dispose()


health()
asyncio.run(old_orm_reads_and_insert())
print("old backend health/read/insert compatibility passed against 0056")
