import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_db_session
from app.core.config import settings
from app.modules.audit.service import AuditService
from app.modules.customer_notifications.schemas import CustomerBotWebhookResponse
from app.modules.customer_notifications.service import (
    CustomerBotWebhookService,
    CustomerNotificationsService,
)
from app.modules.manual_payments.service import ManualPaymentsService
from app.modules.seller_auth.service import SellerAuthService
from app.modules.seller_bot.service import SellerBotService
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
    from app.modules.returns.service import ReturnsService

    seller_auth_service = SellerAuthService(session)
    seller_bot_service = SellerBotService(
        session,
        telegram_service=seller_auth_service.telegram_service,
    )
    return SellerBotWebhookService(
        seller_auth_service=seller_auth_service,
        seller_bot_service=seller_bot_service,
        manual_payments_service=ManualPaymentsService(
            session,
            audit_service=AuditService(session),
        ),
        returns_service=ReturnsService(session),
    )


def get_customer_bot_webhook_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CustomerBotWebhookService:
    return CustomerBotWebhookService(CustomerNotificationsService(session))


def verify_seller_bot_webhook_header(
    x_telegram_secret_token: Annotated[
        str | None,
        Header(alias="X-Telegram-Bot-Api-Secret-Token"),
    ] = None,
) -> None:
    _verify_seller_bot_webhook_secret(header_secret=x_telegram_secret_token)


def verify_seller_bot_webhook_path_secret(
    secret: str,
    x_telegram_secret_token: Annotated[
        str | None,
        Header(alias="X-Telegram-Bot-Api-Secret-Token"),
    ] = None,
) -> None:
    _verify_seller_bot_webhook_secret(path_secret=secret, header_secret=x_telegram_secret_token)


def verify_customer_bot_webhook_header(
    x_telegram_secret_token: Annotated[
        str | None,
        Header(alias="X-Telegram-Bot-Api-Secret-Token"),
    ] = None,
) -> None:
    configured_secret = settings.telegram_customer_webhook_secret
    if not configured_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Customer bot webhook is not configured",
        )
    if x_telegram_secret_token is None or not hmac.compare_digest(
        x_telegram_secret_token,
        configured_secret,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid customer bot webhook secret",
        )


def _verify_seller_bot_webhook_secret(
    *,
    path_secret: str | None = None,
    header_secret: str | None = None,
) -> None:
    configured_secret = settings.telegram_seller_webhook_secret
    if not configured_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Seller bot webhook is not configured",
        )
    if path_secret is None and header_secret is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid seller bot webhook secret",
        )
    if path_secret is not None and not hmac.compare_digest(path_secret, configured_secret):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid seller bot webhook secret",
        )
    if header_secret is not None and not hmac.compare_digest(
        header_secret,
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
    "/seller-bot/webhook",
    response_model=SellerBotWebhookResponse,
    dependencies=[Depends(verify_seller_bot_webhook_header)],
)
async def handle_seller_bot_webhook(
    update: TelegramUpdate,
    service: Annotated[SellerBotWebhookService, Depends(get_seller_bot_webhook_service)],
) -> SellerBotWebhookResponse:
    return await service.handle_update(update)


@router.post(
    "/customer-bot/webhook",
    response_model=CustomerBotWebhookResponse,
    dependencies=[Depends(verify_customer_bot_webhook_header)],
)
async def handle_customer_bot_webhook(
    update: TelegramUpdate,
    service: Annotated[CustomerBotWebhookService, Depends(get_customer_bot_webhook_service)],
) -> CustomerBotWebhookResponse:
    return await service.handle_update(update)


@router.post(
    "/seller-bot/webhook/{secret}",
    response_model=SellerBotWebhookResponse,
    dependencies=[Depends(verify_seller_bot_webhook_path_secret)],
)
async def handle_legacy_seller_bot_webhook(
    update: TelegramUpdate,
    service: Annotated[SellerBotWebhookService, Depends(get_seller_bot_webhook_service)],
) -> SellerBotWebhookResponse:
    return await service.handle_update(update)
