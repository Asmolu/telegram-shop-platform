from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Category


class CategoriesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> list[Category]:
        result = await self.session.execute(select(Category).order_by(Category.name))
        return list(result.scalars().all())

    async def get_by_id(self, category_id: int) -> Category | None:
        return await self.session.get(Category, category_id)

    async def get_by_slug(self, slug: str) -> Category | None:
        result = await self.session.execute(select(Category).where(Category.slug == slug))
        return result.scalar_one_or_none()

    async def get_by_name_or_slug(self, value: str) -> Category | None:
        normalized = value.strip().lower()
        result = await self.session.execute(
            select(Category).where(
                (func.lower(Category.name) == normalized) | (Category.slug == normalized)
            )
        )
        return result.scalar_one_or_none()

    def add(self, category: Category) -> None:
        self.session.add(category)

    async def delete(self, category: Category) -> None:
        await self.session.delete(category)
