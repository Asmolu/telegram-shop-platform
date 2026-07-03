from fastapi import status
from pydantic import TypeAdapter
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.cache import CacheService, categories_list_key, taxonomy_cache_patterns
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import Category, RouteAliasEntityType
from app.modules.categories.repository import CategoriesRepository
from app.modules.categories.schemas import CategoryCreate, CategoryRead, CategoryUpdate
from app.modules.route_aliases.service import RouteAliasesService
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
        self.route_aliases = RouteAliasesService(session)
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

    async def resolve_category_by_slug(self, slug: str) -> Category:
        category = await self._get_category_by_slug_or_alias(slug)
        if category is None:
            raise AppError("Category not found", status.HTTP_404_NOT_FOUND)
        return category

    async def create_category(
        self,
        payload: CategoryCreate,
        actor_user_id: int | None = None,
    ) -> Category:
        self._validate_image_path(payload.image_path)
        await self.route_aliases.ensure_slug_available(
            RouteAliasEntityType.CATEGORY,
            payload.slug,
            conflict_message="Category slug conflicts with an active route alias",
        )
        category = Category(**payload.model_dump())
        self.repository.add(category)
        await self._commit()
        await self.session.refresh(category)
        await self._invalidate_cache()
        return category

    async def update_category(
        self,
        category_id: int,
        payload: CategoryUpdate,
        actor_user_id: int | None = None,
    ) -> Category:
        category = await self.get_category(category_id)
        data = payload.model_dump(exclude_unset=True)
        if "image_path" in data:
            self._validate_image_path(data["image_path"])
        next_slug = data.get("slug")
        if next_slug is not None and next_slug != category.slug:
            existing_slug_owner = await self.repository.get_by_slug(next_slug)
            if existing_slug_owner is not None and existing_slug_owner.id != category.id:
                raise AppError("Category slug already exists", status.HTTP_409_CONFLICT)
            await self.route_aliases.ensure_slug_available(
                RouteAliasEntityType.CATEGORY,
                next_slug,
                entity_id=category.id,
                conflict_message="Category slug conflicts with an active route alias",
            )
            await self.route_aliases.create_alias_for_slug_change(
                RouteAliasEntityType.CATEGORY,
                entity_id=category.id,
                old_slug=category.slug,
                new_slug=next_slug,
                created_by_user_id=actor_user_id,
                conflict_message="Category slug conflicts with an active route alias",
            )
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

    async def _get_category_by_slug_or_alias(self, slug: str) -> Category | None:
        category = await self.repository.get_by_slug(slug)
        if category is not None:
            return category

        category_id = await self.route_aliases.resolve_entity_id(
            RouteAliasEntityType.CATEGORY,
            slug,
        )
        if category_id is None:
            return None
        return await self.repository.get_by_id(category_id)

    def _validate_image_path(self, image_path: str | None) -> None:
        if image_path is not None and not self.storage.exists(image_path):
            raise AppError("Category image was not uploaded", status.HTTP_400_BAD_REQUEST)
