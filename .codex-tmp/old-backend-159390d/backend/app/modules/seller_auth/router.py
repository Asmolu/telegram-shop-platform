from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_db_session, require_roles
from app.db.models import User, UserRole
from app.modules.auth.schemas import TokenResponse
from app.modules.seller_auth.schemas import (
    SellerLoginRequest,
    SellerMeResponse,
    SellerRegistrationConfirmRequest,
    SellerRegistrationResendCodeRequest,
    SellerRegistrationResendCodeResponse,
    SellerRegistrationStartRequest,
    SellerRegistrationStartResponse,
    SellerTelegramStartRequest,
    SellerTelegramStartResponse,
)
from app.modules.seller_auth.service import SellerAuthService

router = APIRouter(prefix="/seller-auth", tags=["seller-auth"])


def get_seller_auth_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SellerAuthService:
    return SellerAuthService(session)


@router.post(
    "/register/start",
    response_model=SellerRegistrationStartResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_registration(
    payload: SellerRegistrationStartRequest,
    service: Annotated[SellerAuthService, Depends(get_seller_auth_service)],
) -> SellerRegistrationStartResponse:
    return await service.start_registration(payload)


@router.post("/register/telegram-start", response_model=SellerTelegramStartResponse)
async def link_telegram_start(
    payload: SellerTelegramStartRequest,
    service: Annotated[SellerAuthService, Depends(get_seller_auth_service)],
) -> SellerTelegramStartResponse:
    return await service.handle_telegram_start(payload)


@router.post("/register/resend-code", response_model=SellerRegistrationResendCodeResponse)
async def resend_code(
    payload: SellerRegistrationResendCodeRequest,
    service: Annotated[SellerAuthService, Depends(get_seller_auth_service)],
) -> SellerRegistrationResendCodeResponse:
    return await service.resend_code(payload)


@router.post("/register/confirm", response_model=TokenResponse)
async def confirm_registration(
    payload: SellerRegistrationConfirmRequest,
    service: Annotated[SellerAuthService, Depends(get_seller_auth_service)],
) -> TokenResponse:
    return await service.confirm_registration(payload)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: SellerLoginRequest,
    service: Annotated[SellerAuthService, Depends(get_seller_auth_service)],
) -> TokenResponse:
    return await service.login(payload)


@router.get("/me", response_model=SellerMeResponse)
async def read_current_seller(
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
) -> User:
    return current_user
