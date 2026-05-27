from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_db_session
from app.modules.auth.schemas import TelegramLoginRequest, TokenResponse
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/telegram/login", response_model=TokenResponse)
async def telegram_login(
    payload: TelegramLoginRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponse:
    service = AuthService(session)
    return await service.login_with_telegram(payload.init_data)
