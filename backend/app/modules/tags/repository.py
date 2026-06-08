from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Tag


class TagsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> list[Tag]:
        result = await self.session.execute(select(Tag).order_by(Tag.name))
        return list(result.scalars().all())

    async def get_by_id(self, tag_id: int) -> Tag | None:
        return await self.session.get(Tag, tag_id)

    async def list_by_ids(self, tag_ids: list[int]) -> list[Tag]:
        if not tag_ids:
            return []
        result = await self.session.execute(select(Tag).where(Tag.id.in_(tag_ids)))
        return list(result.scalars().all())

    async def list_by_names_or_slugs(self, values: list[str]) -> list[Tag]:
        normalized = [value.strip().lower() for value in values if value.strip()]
        if not normalized:
            return []
        result = await self.session.execute(
            select(Tag).where(
                (func.lower(Tag.name).in_(normalized)) | (Tag.slug.in_(normalized))
            )
        )
        return list(result.scalars().all())

    def add(self, tag: Tag) -> None:
        self.session.add(tag)

    async def delete(self, tag: Tag) -> None:
        await self.session.delete(tag)
