import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_db_session
from app.core.config import settings
from app.modules.seller_auth.service import SellerAuthService
from app.modules.telegram.schemas import (
    SellerBotWebhookResponse,
    TelegramStatus,
    TelegramUpdate,
)
from app.modules.telegram.service import SellerBotWebhookService

router = APIRouter(prefix="/telegram", tags=["telegram"])


def get_seller_bot_webhook_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SellerBotWebhookService:
    seller_auth_service = SellerAuthService(session)
    return SellerBotWebhookService(seller_auth_service=seller_auth_service)


def verify_seller_bot_webhook_secret(
    secret: str,
    x_telegram_secret_token: Annotated[
        str | None,
        Header(alias="X-Telegram-Bot-Api-Secret-Token"),
    ] = None,
) -> None:
    configured_secret = settings.telegram_seller_webhook_secret
    if not configured_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Seller bot webhook is not configured",
        )
    if not hmac.compare_digest(secret, configured_secret):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid seller bot webhook secret",
        )
    if x_telegram_secret_token is not None and not hmac.compare_digest(
        x_telegram_secret_token,
        configured_secret,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid seller bot webhook secret",
        )


@router.get("/status", response_model=TelegramStatus)
async def module_status() -> TelegramStatus:
    return TelegramStatus(module="telegram", status="ok")


@router.post(
    "/seller-bot/webhook/{secret}",
    response_model=SellerBotWebhookResponse,
    dependencies=[Depends(verify_seller_bot_webhook_secret)],
)
async def handle_seller_bot_webhook(
    update: TelegramUpdate,
    service: Annotated[SellerBotWebhookService, Depends(get_seller_bot_webhook_service)],
) -> SellerBotWebhookResponse:
    return await service.handle_update(update)
