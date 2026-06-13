from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.cache import CacheService
from app.common.deps import get_db_session, require_roles
from app.db.models import User, UserRole
from app.modules.uploads.image_profiles import ImageUploadKind
from app.modules.uploads.schemas import (
    BannerImageUploadRead,
    CategoryImageUploadRead,
    ProductImageUploadRead,
    TagImageUploadRead,
)
from app.modules.uploads.service import UploadsService

router = APIRouter(prefix="/uploads", tags=["uploads"])


def get_uploads_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UploadsService:
    return UploadsService(session, cache=CacheService())


@router.get("/status")
async def module_status() -> dict[str, str]:
    return {"module": "uploads", "status": "stub"}


@router.post(
    "/products/{product_id}/images",
    response_model=ProductImageUploadRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_product_image(
    product_id: int,
    service: Annotated[UploadsService, Depends(get_uploads_service)],
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    file: Annotated[UploadFile, File()],
    alt_text: Annotated[str | None, Form(max_length=255)] = None,
    position: Annotated[int | None, Form(ge=0)] = None,
    is_primary: Annotated[bool, Form()] = False,
) -> object:
    return await service.upload_product_image(
        product_id=product_id,
        file=file,
        alt_text=alt_text,
        position=position,
        is_primary=is_primary,
    )


@router.post(
    "/banners/images",
    response_model=BannerImageUploadRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_banner_image(
    service: Annotated[UploadsService, Depends(get_uploads_service)],
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    file: Annotated[UploadFile, File()],
    alt_text: Annotated[str | None, Form(max_length=255)] = None,
    image_kind: Annotated[ImageUploadKind, Form()] = ImageUploadKind.NATIVE_BANNER,
) -> object:
    return await service.upload_banner_image(file=file, alt_text=alt_text, image_kind=image_kind)


@router.post(
    "/tags/images",
    response_model=TagImageUploadRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_tag_image(
    service: Annotated[UploadsService, Depends(get_uploads_service)],
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    file: Annotated[UploadFile, File()],
    alt_text: Annotated[str | None, Form(max_length=255)] = None,
) -> object:
    return await service.upload_tag_image(file=file, alt_text=alt_text)


@router.post(
    "/categories/images",
    response_model=CategoryImageUploadRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_category_image(
    service: Annotated[UploadsService, Depends(get_uploads_service)],
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    file: Annotated[UploadFile, File()],
    alt_text: Annotated[str | None, Form(max_length=255)] = None,
) -> object:
    return await service.upload_category_image(file=file, alt_text=alt_text)
