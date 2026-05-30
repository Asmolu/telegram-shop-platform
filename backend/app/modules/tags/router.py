from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.cache import CacheService
from app.common.deps import get_db_session, require_roles
from app.db.models import User, UserRole
from app.modules.tags.schemas import TagCreate, TagRead, TagUpdate
from app.modules.tags.service import TagsService

router = APIRouter(prefix="/tags", tags=["tags"])


def get_tags_service(session: Annotated[AsyncSession, Depends(get_db_session)]) -> TagsService:
    return TagsService(session, cache=CacheService())


@router.get("", response_model=list[TagRead])
async def list_tags(service: Annotated[TagsService, Depends(get_tags_service)]) -> list:
    return await service.list_tags()


@router.get("/{tag_id}", response_model=TagRead)
async def get_tag(
    tag_id: int,
    service: Annotated[TagsService, Depends(get_tags_service)],
) -> object:
    return await service.get_tag(tag_id)


@router.post("", response_model=TagRead, status_code=status.HTTP_201_CREATED)
async def create_tag(
    payload: TagCreate,
    service: Annotated[TagsService, Depends(get_tags_service)],
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
) -> object:
    return await service.create_tag(payload)


@router.patch("/{tag_id}", response_model=TagRead)
async def update_tag(
    tag_id: int,
    payload: TagUpdate,
    service: Annotated[TagsService, Depends(get_tags_service)],
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
) -> object:
    return await service.update_tag(tag_id, payload)


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: int,
    service: Annotated[TagsService, Depends(get_tags_service)],
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
) -> Response:
    await service.delete_tag(tag_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
