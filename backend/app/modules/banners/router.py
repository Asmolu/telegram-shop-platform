from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_db_session, require_roles
from app.db.models import User, UserRole
from app.modules.audit.service import AuditService
from app.modules.banners.schemas import BannerCreate, BannerList, BannerRead, BannerUpdate
from app.modules.banners.service import BannersService

router = APIRouter(prefix="/banners", tags=["banners"])


def get_banners_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> BannersService:
    return BannersService(session, audit_service=AuditService(session))


@router.get("", response_model=BannerList)
async def list_public_banners(
    service: Annotated[BannersService, Depends(get_banners_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> BannerList:
    return await service.list_public_banners(limit=limit, offset=offset)


@router.get("/admin", response_model=BannerList)
async def list_banners(
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[BannersService, Depends(get_banners_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> BannerList:
    return await service.list_banners(limit=limit, offset=offset)


@router.post("/admin", response_model=BannerRead, status_code=status.HTTP_201_CREATED)
async def create_banner(
    payload: BannerCreate,
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[BannersService, Depends(get_banners_service)],
) -> BannerRead:
    return await service.create_banner(payload, actor_user_id=current_user.id)


@router.get("/admin/{banner_id}", response_model=BannerRead)
async def get_banner(
    banner_id: int,
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[BannersService, Depends(get_banners_service)],
) -> BannerRead:
    return await service.get_banner(banner_id)


@router.patch("/admin/{banner_id}", response_model=BannerRead)
async def update_banner(
    banner_id: int,
    payload: BannerUpdate,
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[BannersService, Depends(get_banners_service)],
) -> BannerRead:
    return await service.update_banner(banner_id, payload, actor_user_id=current_user.id)


@router.patch("/admin/{banner_id}/activate", response_model=BannerRead)
async def activate_banner(
    banner_id: int,
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[BannersService, Depends(get_banners_service)],
) -> BannerRead:
    return await service.set_banner_active(banner_id, True, actor_user_id=current_user.id)


@router.patch("/admin/{banner_id}/deactivate", response_model=BannerRead)
async def deactivate_banner(
    banner_id: int,
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[BannersService, Depends(get_banners_service)],
) -> BannerRead:
    return await service.set_banner_active(banner_id, False, actor_user_id=current_user.id)
