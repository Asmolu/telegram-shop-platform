from fastapi import status
from pydantic import TypeAdapter
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.cache import CacheService, tags_list_key, taxonomy_cache_patterns
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import Tag
from app.modules.tags.repository import TagsRepository
from app.modules.tags.schemas import TagCreate, TagRead, TagUpdate

_TAGS_ADAPTER = TypeAdapter(list[TagRead])


class TagsService:
    def __init__(self, session: AsyncSession, cache: CacheService | None = None) -> None:
        self.session = session
        self.repository = TagsRepository(session)
        self.cache = cache

    async def list_tags(self) -> list[Tag] | list[TagRead]:
        if self.cache is not None:
            cached = await self.cache.get_value(tags_list_key(), _TAGS_ADAPTER)
            if cached is not None:
                return cached

        tags = await self.repository.list()
        if self.cache is not None:
            await self.cache.set_value(
                tags_list_key(),
                [TagRead.model_validate(tag) for tag in tags],
                _TAGS_ADAPTER,
                settings.cache_taxonomy_ttl_seconds,
            )
        return tags

    async def get_tag(self, tag_id: int) -> Tag:
        tag = await self.repository.get_by_id(tag_id)
        if tag is None:
            raise AppError("Tag not found", status.HTTP_404_NOT_FOUND)
        return tag

    async def create_tag(self, payload: TagCreate) -> Tag:
        tag = Tag(**payload.model_dump())
        self.repository.add(tag)
        await self._commit()
        await self.session.refresh(tag)
        await self._invalidate_cache()
        return tag

    async def update_tag(self, tag_id: int, payload: TagUpdate) -> Tag:
        tag = await self.get_tag(tag_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(tag, field, value)

        await self._commit()
        await self.session.refresh(tag)
        await self._invalidate_cache()
        return tag

    async def delete_tag(self, tag_id: int) -> None:
        tag = await self.get_tag(tag_id)
        await self.repository.delete(tag)
        await self._commit()
        await self._invalidate_cache()

    async def _commit(self) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("Tag slug already exists", status.HTTP_409_CONFLICT) from exc

    async def _invalidate_cache(self) -> None:
        if self.cache is None:
            return
        await self.cache.delete_patterns(*taxonomy_cache_patterns())
