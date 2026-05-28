from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_current_user, get_db_session, require_roles
from app.db.models import User, UserRole
from app.modules.promo_codes.schemas import (
    PromoCodeCreate,
    PromoCodeList,
    PromoCodeRead,
    PromoCodeUpdate,
    PromoCodeValidateRequest,
    PromoCodeValidationRead,
)
from app.modules.promo_codes.service import PromoCodesService

router = APIRouter(prefix="/promo-codes", tags=["promo-codes"])


def get_promo_codes_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PromoCodesService:
    return PromoCodesService(session)


@router.post("/validate", response_model=PromoCodeValidationRead)
async def validate_current_cart_promo_code(
    payload: PromoCodeValidateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[PromoCodesService, Depends(get_promo_codes_service)],
) -> PromoCodeValidationRead:
    return await service.validate_current_cart(user_id=current_user.id, code=payload.code)


@router.post("", response_model=PromoCodeRead, status_code=status.HTTP_201_CREATED)
async def create_promo_code(
    payload: PromoCodeCreate,
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[PromoCodesService, Depends(get_promo_codes_service)],
) -> PromoCodeRead:
    return await service.create_promo_code(payload)


@router.get("", response_model=PromoCodeList)
async def list_promo_codes(
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[PromoCodesService, Depends(get_promo_codes_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PromoCodeList:
    return await service.list_promo_codes(limit=limit, offset=offset)


@router.get("/{promo_code_id}", response_model=PromoCodeRead)
async def get_promo_code(
    promo_code_id: int,
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[PromoCodesService, Depends(get_promo_codes_service)],
) -> PromoCodeRead:
    return await service.get_promo_code(promo_code_id)


@router.patch("/{promo_code_id}", response_model=PromoCodeRead)
async def update_promo_code(
    promo_code_id: int,
    payload: PromoCodeUpdate,
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[PromoCodesService, Depends(get_promo_codes_service)],
) -> PromoCodeRead:
    return await service.update_promo_code(promo_code_id, payload)


@router.delete("/{promo_code_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_promo_code(
    promo_code_id: int,
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[PromoCodesService, Depends(get_promo_codes_service)],
) -> Response:
    await service.deactivate_promo_code(promo_code_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
