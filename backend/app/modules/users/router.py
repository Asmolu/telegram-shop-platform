from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_current_user, get_db_session, require_roles
from app.db.models import User, UserRole
from app.modules.users.schemas import UserList, UserRead
from app.modules.users.service import UsersService

router = APIRouter(prefix="/users", tags=["users"])


def get_users_service(session: Annotated[AsyncSession, Depends(get_db_session)]) -> UsersService:
    return UsersService(session)


@router.get("/me", response_model=UserRead)
async def read_current_user(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    return current_user


@router.get("/admin", response_model=UserList)
async def list_users(
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[UsersService, Depends(get_users_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UserList:
    return await service.list_users(limit=limit, offset=offset)


@router.get("/admin/{user_id}", response_model=UserRead)
async def get_user_detail(
    user_id: int,
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[UsersService, Depends(get_users_service)],
) -> UserRead:
    return await service.get_user_detail(user_id)
