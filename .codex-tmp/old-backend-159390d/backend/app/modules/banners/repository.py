from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Banner


class BannersRepository:
    """Database access layer for banners."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        active_only: bool = False,
    ) -> tuple[list[Banner], int]:
        conditions = []
        if active_only:
            now = datetime.now(UTC)
            conditions.extend(
                [
                    Banner.is_active.is_(True),
                    Banner.target_type.is_not(None),
                    or_(Banner.starts_at.is_(None), Banner.starts_at <= now),
                    or_(Banner.ends_at.is_(None), Banner.ends_at > now),
                ]
            )

        banners_query = (
            select(Banner)
            .where(*conditions)
            .order_by(Banner.position, Banner.created_at.desc(), Banner.id.desc())
            .limit(limit)
            .offset(offset)
        )
        count_query = select(func.count(Banner.id)).where(*conditions)

        banners_result = await self.session.execute(banners_query)
        count_result = await self.session.execute(count_query)
        return list(banners_result.scalars().all()), count_result.scalar_one()

    async def get_by_id(self, banner_id: int) -> Banner | None:
        result = await self.session.execute(select(Banner).where(Banner.id == banner_id))
        return result.scalar_one_or_none()

    def add(self, banner: Banner) -> None:
        self.session.add(banner)
