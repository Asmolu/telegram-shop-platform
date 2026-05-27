from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import Category
from app.modules.categories.repository import CategoriesRepository
from app.modules.categories.schemas import CategoryCreate, CategoryUpdate


class CategoriesService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = CategoriesRepository(session)

    async def list_categories(self) -> list[Category]:
        return await self.repository.list()

    async def get_category(self, category_id: int) -> Category:
        category = await self.repository.get_by_id(category_id)
        if category is None:
            raise AppError("Category not found", status.HTTP_404_NOT_FOUND)
        return category

    async def create_category(self, payload: CategoryCreate) -> Category:
        category = Category(**payload.model_dump())
        self.repository.add(category)
        await self._commit()
        await self.session.refresh(category)
        return category

    async def update_category(self, category_id: int, payload: CategoryUpdate) -> Category:
        category = await self.get_category(category_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(category, field, value)

        await self._commit()
        await self.session.refresh(category)
        return category

    async def delete_category(self, category_id: int) -> None:
        category = await self.get_category(category_id)
        await self.repository.delete(category)
        await self._commit()

    async def _commit(self) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("Category slug already exists", status.HTTP_409_CONFLICT) from exc
