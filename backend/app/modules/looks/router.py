from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_current_user, get_db_session, require_roles
from app.common.http_cache import PRIVATE_NO_STORE_CACHE
from app.common.pagination import PaginationParams
from app.db.models import LookStatus, User, UserRole
from app.modules.looks.schemas import (
    LookAdminList,
    LookAdminRead,
    LookCartAddRequest,
    LookCartAddResponse,
    LookCreate,
    LookDetailRead,
    LookImageRead,
    LookList,
    LookSlugList,
    LookUpdate,
)
from app.modules.looks.service import LooksService
from app.modules.products.schemas import ProductCardList

public_router = APIRouter(prefix="/looks", tags=["looks"])
admin_router = APIRouter(prefix="/looks/admin", tags=["looks"])


def get_looks_service(session: Annotated[AsyncSession, Depends(get_db_session)]) -> LooksService:
    return LooksService(session)


@public_router.get("", response_model=LookList)
async def list_public_looks(
    pagination: Annotated[PaginationParams, Depends()],
    service: Annotated[LooksService, Depends(get_looks_service)],
) -> LookList:
    return await service.list_public_looks(limit=pagination.limit, offset=pagination.offset)


@public_router.get("/{slug}", response_model=LookDetailRead)
async def get_public_look(
    slug: str,
    service: Annotated[LooksService, Depends(get_looks_service)],
) -> LookDetailRead:
    return await service.get_public_look(slug)


@public_router.get("/{slug}/similar-products", response_model=ProductCardList)
async def list_look_similar_products(
    slug: str,
    service: Annotated[LooksService, Depends(get_looks_service)],
    limit: Annotated[int, Query(ge=1, le=50)] = 12,
) -> ProductCardList:
    return await service.list_similar_products(slug, limit=limit)


@public_router.post("/{slug}/cart", response_model=LookCartAddResponse)
async def add_look_to_cart(
    slug: str,
    payload: LookCartAddRequest,
    response: Response,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[LooksService, Depends(get_looks_service)],
) -> LookCartAddResponse:
    response.headers["Cache-Control"] = PRIVATE_NO_STORE_CACHE
    return await service.add_look_to_cart(slug=slug, user_id=current_user.id, payload=payload)


@admin_router.get("", response_model=LookAdminList)
async def list_admin_looks(
    pagination: Annotated[PaginationParams, Depends()],
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[LooksService, Depends(get_looks_service)],
    status_filter: Annotated[LookStatus | None, Query(alias="status")] = None,
) -> LookAdminList:
    return await service.list_admin_looks(
        limit=pagination.limit,
        offset=pagination.offset,
        status_filter=status_filter,
    )


@admin_router.get("/slugs/next", response_model=LookSlugList)
async def generate_look_slugs(
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[LooksService, Depends(get_looks_service)],
    count: Annotated[int, Query(ge=1, le=100)] = 1,
) -> LookSlugList:
    return await service.generate_look_slugs(count)


@admin_router.post("", response_model=LookAdminRead, status_code=status.HTTP_201_CREATED)
async def create_admin_look(
    payload: LookCreate,
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[LooksService, Depends(get_looks_service)],
) -> LookAdminRead:
    return await service.create_admin_look(payload, actor_user_id=current_user.id)


@admin_router.get("/{look_id}", response_model=LookAdminRead)
async def get_admin_look(
    look_id: int,
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[LooksService, Depends(get_looks_service)],
) -> LookAdminRead:
    return await service.get_admin_look(look_id)


@admin_router.patch("/{look_id}", response_model=LookAdminRead)
async def update_admin_look(
    look_id: int,
    payload: LookUpdate,
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[LooksService, Depends(get_looks_service)],
) -> LookAdminRead:
    return await service.update_admin_look(look_id, payload, actor_user_id=current_user.id)


@admin_router.delete("/{look_id}", response_model=LookAdminRead)
async def archive_admin_look(
    look_id: int,
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[LooksService, Depends(get_looks_service)],
) -> LookAdminRead:
    return await service.archive_admin_look(look_id)


@admin_router.post(
    "/{look_id}/images",
    response_model=LookImageRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_admin_look_image(
    look_id: int,
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[LooksService, Depends(get_looks_service)],
    file: Annotated[UploadFile, File()],
    alt_text: Annotated[str | None, Form(max_length=255)] = None,
    position: Annotated[int | None, Form(ge=0)] = None,
    is_primary: Annotated[bool, Form()] = False,
) -> LookImageRead:
    return await service.upload_image(
        look_id=look_id,
        file=file,
        alt_text=alt_text,
        position=position,
        is_primary=is_primary,
    )


@admin_router.delete("/{look_id}/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin_look_image(
    look_id: int,
    image_id: int,
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[LooksService, Depends(get_looks_service)],
) -> Response:
    await service.delete_image(look_id=look_id, image_id=image_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
