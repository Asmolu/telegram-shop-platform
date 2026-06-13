from fastapi import status
from pydantic import TypeAdapter
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.cache import CacheService, categories_list_key, taxonomy_cache_patterns
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import Category
from app.modules.categories.repository import CategoriesRepository
from app.modules.categories.schemas import CategoryCreate, CategoryRead, CategoryUpdate
from app.modules.uploads.storage import LocalStorageService

_CATEGORIES_ADAPTER = TypeAdapter(list[CategoryRead])


class CategoriesService:
    def __init__(
        self,
        session: AsyncSession,
        cache: CacheService | None = None,
        storage: LocalStorageService | None = None,
    ) -> None:
        self.session = session
        self.repository = CategoriesRepository(session)
        self.cache = cache
        self.storage = storage or LocalStorageService()

    async def list_categories(self) -> list[Category] | list[CategoryRead]:
        if self.cache is not None:
            cached = await self.cache.get_value(categories_list_key(), _CATEGORIES_ADAPTER)
            if cached is not None:
                return cached

        categories = await self.repository.list()
        if self.cache is not None:
            await self.cache.set_value(
                categories_list_key(),
                [CategoryRead.model_validate(category) for category in categories],
                _CATEGORIES_ADAPTER,
                settings.cache_taxonomy_ttl_seconds,
            )
        return categories

    async def get_category(self, category_id: int) -> Category:
        category = await self.repository.get_by_id(category_id)
        if category is None:
            raise AppError("Category not found", status.HTTP_404_NOT_FOUND)
        return category

    async def create_category(self, payload: CategoryCreate) -> Category:
        self._validate_image_path(payload.image_path)
        category = Category(**payload.model_dump())
        self.repository.add(category)
        await self._commit()
        await self.session.refresh(category)
        await self._invalidate_cache()
        return category

    async def update_category(self, category_id: int, payload: CategoryUpdate) -> Category:
        category = await self.get_category(category_id)
        data = payload.model_dump(exclude_unset=True)
        if "image_path" in data:
            self._validate_image_path(data["image_path"])
        for field, value in data.items():
            setattr(category, field, value)

        await self._commit()
        await self.session.refresh(category)
        await self._invalidate_cache()
        return category

    async def delete_category(self, category_id: int) -> None:
        category = await self.get_category(category_id)
        await self.repository.delete(category)
        await self._commit()
        await self._invalidate_cache()

    async def _commit(self) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("Category slug already exists", status.HTTP_409_CONFLICT) from exc

    async def _invalidate_cache(self) -> None:
        if self.cache is None:
            return
        await self.cache.delete_patterns(*taxonomy_cache_patterns())

    def _validate_image_path(self, image_path: str | None) -> None:
        if image_path is not None and not self.storage.exists(image_path):
            raise AppError("Category image was not uploaded", status.HTTP_400_BAD_REQUEST)
