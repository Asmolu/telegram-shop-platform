from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.cache import CacheService
from app.common.deps import get_db_session, require_roles
from app.common.http_cache import (
    PUBLIC_STABLE_CACHE,
    is_not_modified,
    not_modified_response,
    set_cache_headers,
    stable_etag,
)
from app.db.models import User, UserRole
from app.modules.categories.schemas import CategoryCreate, CategoryRead, CategoryUpdate
from app.modules.categories.service import CategoriesService

router = APIRouter(prefix="/categories", tags=["categories"])


def get_categories_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CategoriesService:
    return CategoriesService(session, cache=CacheService())


@router.get("", response_model=list[CategoryRead])
async def list_categories(
    request: Request,
    response: Response,
    service: Annotated[CategoriesService, Depends(get_categories_service)],
) -> list[CategoryRead] | Response:
    categories = [
        CategoryRead.model_validate(category) for category in await service.list_categories()
    ]
    etag = stable_etag(categories)
    if is_not_modified(request, etag):
        return not_modified_response(etag=etag, cache_control=PUBLIC_STABLE_CACHE)
    set_cache_headers(response, etag=etag, cache_control=PUBLIC_STABLE_CACHE)
    return categories


@router.get("/resolve", response_model=CategoryRead)
async def resolve_category(
    slug: Annotated[str, Query(min_length=1, max_length=255)],
    request: Request,
    response: Response,
    service: Annotated[CategoriesService, Depends(get_categories_service)],
) -> CategoryRead | Response:
    category = CategoryRead.model_validate(await service.resolve_category_by_slug(slug))
    etag = stable_etag(category)
    if is_not_modified(request, etag):
        return not_modified_response(etag=etag, cache_control=PUBLIC_STABLE_CACHE)
    set_cache_headers(response, etag=etag, cache_control=PUBLIC_STABLE_CACHE)
    return category


@router.get("/{category_id}", response_model=CategoryRead)
async def get_category(
    category_id: int,
    request: Request,
    response: Response,
    service: Annotated[CategoriesService, Depends(get_categories_service)],
) -> CategoryRead | Response:
    category = CategoryRead.model_validate(await service.get_category(category_id))
    etag = stable_etag(category)
    if is_not_modified(request, etag):
        return not_modified_response(etag=etag, cache_control=PUBLIC_STABLE_CACHE)
    set_cache_headers(response, etag=etag, cache_control=PUBLIC_STABLE_CACHE)
    return category


@router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreate,
    service: Annotated[CategoriesService, Depends(get_categories_service)],
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
) -> object:
    return await service.create_category(payload, actor_user_id=current_user.id)


@router.patch("/{category_id}", response_model=CategoryRead)
async def update_category(
    category_id: int,
    payload: CategoryUpdate,
    service: Annotated[CategoriesService, Depends(get_categories_service)],
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
) -> object:
    return await service.update_category(category_id, payload, actor_user_id=current_user.id)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: int,
    service: Annotated[CategoriesService, Depends(get_categories_service)],
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
) -> Response:
    await service.delete_category(category_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
