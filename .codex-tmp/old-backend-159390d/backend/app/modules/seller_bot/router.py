from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_db_session, require_roles
from app.common.pagination import PaginationParams
from app.db.models import User, UserRole
from app.modules.notifications.schemas import NotificationList
from app.modules.seller_bot.schemas import (
    SellerBotActionResponse,
    SellerBotBroadcastRequest,
    SellerBotMessageRequest,
    SellerBotStatusResponse,
)
from app.modules.seller_bot.service import SellerBotService

router = APIRouter(prefix="/seller-bot", tags=["seller-bot"])


def get_seller_bot_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SellerBotService:
    return SellerBotService(session)


@router.get("/status", response_model=SellerBotStatusResponse)
async def get_status(
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[SellerBotService, Depends(get_seller_bot_service)],
) -> SellerBotStatusResponse:
    return await service.get_status()


@router.post("/test-message", response_model=SellerBotActionResponse)
async def send_test_message(
    payload: SellerBotMessageRequest,
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[SellerBotService, Depends(get_seller_bot_service)],
) -> SellerBotActionResponse:
    return await service.send_test_message(payload=payload, actor_user_id=current_user.id)


@router.post("/broadcast", response_model=SellerBotActionResponse)
async def broadcast(
    payload: SellerBotBroadcastRequest,
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[SellerBotService, Depends(get_seller_bot_service)],
) -> SellerBotActionResponse:
    return await service.broadcast(payload=payload, actor_user_id=current_user.id)


@router.get("/messages", response_model=NotificationList)
async def list_messages(
    pagination: Annotated[PaginationParams, Depends()],
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[SellerBotService, Depends(get_seller_bot_service)],
) -> NotificationList:
    return await service.list_messages(limit=pagination.limit, offset=pagination.offset)
