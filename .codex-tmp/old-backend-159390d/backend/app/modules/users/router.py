from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_current_user, get_db_session, require_roles
from app.db.models import User, UserRole
from app.modules.audit.service import AuditService
from app.modules.users.schemas import (
    PersonalDataRead,
    PersonalDataUpdate,
    UserBlockCreate,
    UserBlockList,
    UserBlockRead,
    UserList,
    UserRead,
)
from app.modules.users.service import UsersService

router = APIRouter(prefix="/users", tags=["users"])


def get_users_service(session: Annotated[AsyncSession, Depends(get_db_session)]) -> UsersService:
    return UsersService(session, audit_service=AuditService(session))


@router.get("/me", response_model=UserRead)
async def read_current_user(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    return current_user


@router.get("/me/personal-data", response_model=PersonalDataRead)
async def read_current_user_personal_data(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[UsersService, Depends(get_users_service)],
) -> PersonalDataRead:
    return service.get_personal_data(current_user)


@router.put("/me/personal-data", response_model=PersonalDataRead)
async def update_current_user_personal_data(
    payload: PersonalDataUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[UsersService, Depends(get_users_service)],
) -> PersonalDataRead:
    return await service.update_personal_data(current_user, payload)


@router.get("/admin", response_model=UserList)
async def list_users(
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[UsersService, Depends(get_users_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UserList:
    return await service.list_users(limit=limit, offset=offset)


@router.get("/admin/blocks", response_model=UserBlockList)
async def list_user_blocks(
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[UsersService, Depends(get_users_service)],
) -> UserBlockList:
    return await service.list_active_blocks()


@router.post("/admin/blocks", response_model=UserBlockRead)
async def create_user_block(
    payload: UserBlockCreate,
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[UsersService, Depends(get_users_service)],
) -> UserBlockRead:
    return await service.create_block(payload, actor_user_id=current_user.id)


@router.post("/admin/blocks/{block_id}/unblock", response_model=UserBlockRead)
async def unblock_user(
    block_id: int,
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[UsersService, Depends(get_users_service)],
) -> UserBlockRead:
    return await service.unblock(block_id, actor_user_id=current_user.id)


@router.get("/admin/{user_id}", response_model=UserRead)
async def get_user_detail(
    user_id: int,
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[UsersService, Depends(get_users_service)],
) -> UserRead:
    return await service.get_user_detail(user_id)
