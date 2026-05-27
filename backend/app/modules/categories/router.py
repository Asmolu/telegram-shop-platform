from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_db_session, require_roles
from app.db.models import User, UserRole
from app.modules.categories.schemas import CategoryCreate, CategoryRead, CategoryUpdate
from app.modules.categories.service import CategoriesService

router = APIRouter(prefix="/categories", tags=["categories"])


def get_categories_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CategoriesService:
    return CategoriesService(session)


@router.get("", response_model=list[CategoryRead])
async def list_categories(
    service: Annotated[CategoriesService, Depends(get_categories_service)],
) -> list:
    return await service.list_categories()


@router.get("/{category_id}", response_model=CategoryRead)
async def get_category(
    category_id: int,
    service: Annotated[CategoriesService, Depends(get_categories_service)],
) -> object:
    return await service.get_category(category_id)


@router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreate,
    service: Annotated[CategoriesService, Depends(get_categories_service)],
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
) -> object:
    return await service.create_category(payload)


@router.patch("/{category_id}", response_model=CategoryRead)
async def update_category(
    category_id: int,
    payload: CategoryUpdate,
    service: Annotated[CategoriesService, Depends(get_categories_service)],
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
) -> object:
    return await service.update_category(category_id, payload)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: int,
    service: Annotated[CategoriesService, Depends(get_categories_service)],
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
) -> Response:
    await service.delete_category(category_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
