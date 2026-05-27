from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import Tag
from app.modules.tags.repository import TagsRepository
from app.modules.tags.schemas import TagCreate, TagUpdate


class TagsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = TagsRepository(session)

    async def list_tags(self) -> list[Tag]:
        return await self.repository.list()

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
        return tag

    async def update_tag(self, tag_id: int, payload: TagUpdate) -> Tag:
        tag = await self.get_tag(tag_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(tag, field, value)

        await self._commit()
        await self.session.refresh(tag)
        return tag

    async def delete_tag(self, tag_id: int) -> None:
        tag = await self.get_tag(tag_id)
        await self.repository.delete(tag)
        await self._commit()

    async def _commit(self) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("Tag slug already exists", status.HTTP_409_CONFLICT) from exc
