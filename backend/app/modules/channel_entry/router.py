from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_db_session, require_roles
from app.core.config import settings
from app.db.models import User, UserRole
from app.modules.audit.service import AuditService
from app.modules.channel_entry.schemas import (
    ChannelCheckRequest,
    ChannelCheckResponse,
    ChannelEntryConfigRead,
    ChannelEntryHistoryRead,
    ChannelEntryPreviewRead,
    ChannelEntryPreviewRequest,
    ChannelEntryPublishRead,
    ChannelEntryPublishRequest,
    TelegramChannelCreate,
    TelegramChannelEntryMessageRead,
    TelegramChannelRead,
    TelegramChannelUpdate,
)
from app.modules.channel_entry.service import ChannelEntryService
from app.modules.telegram.service import TelegramService

router = APIRouter(prefix="/channel-entry", tags=["channel-entry"])


def get_channel_entry_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChannelEntryService:
    return ChannelEntryService(
        session,
        telegram_service=TelegramService(bot_token=settings.telegram_customer_bot_token),
        audit_service=AuditService(session),
    )


@router.get("/config", response_model=ChannelEntryConfigRead)
def get_config(
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[ChannelEntryService, Depends(get_channel_entry_service)],
) -> ChannelEntryConfigRead:
    return service.get_config()


@router.get("/channels", response_model=list[TelegramChannelRead])
async def list_channels(
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[ChannelEntryService, Depends(get_channel_entry_service)],
) -> list[TelegramChannelRead]:
    return await service.list_channels()


@router.post(
    "/channels",
    response_model=TelegramChannelRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_channel(
    payload: TelegramChannelCreate,
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[ChannelEntryService, Depends(get_channel_entry_service)],
) -> TelegramChannelRead:
    return await service.create_channel(payload, actor=current_user)


@router.post("/channels/check", response_model=ChannelCheckResponse)
async def check_channel(
    payload: ChannelCheckRequest,
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[ChannelEntryService, Depends(get_channel_entry_service)],
) -> ChannelCheckResponse:
    return await service.check_channel(payload)


@router.patch("/channels/{channel_id}", response_model=TelegramChannelRead)
async def update_channel(
    channel_id: int,
    payload: TelegramChannelUpdate,
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[ChannelEntryService, Depends(get_channel_entry_service)],
) -> TelegramChannelRead:
    return await service.update_channel(channel_id, payload, actor=current_user)


@router.delete("/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disable_channel(
    channel_id: int,
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[ChannelEntryService, Depends(get_channel_entry_service)],
) -> Response:
    await service.disable_channel(channel_id, actor=current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/preview", response_model=ChannelEntryPreviewRead)
async def preview(
    payload: ChannelEntryPreviewRequest,
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[ChannelEntryService, Depends(get_channel_entry_service)],
) -> ChannelEntryPreviewRead:
    return await service.preview(payload)


@router.post("/publish", response_model=ChannelEntryPublishRead)
async def publish(
    payload: ChannelEntryPublishRequest,
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[ChannelEntryService, Depends(get_channel_entry_service)],
) -> ChannelEntryPublishRead:
    return await service.publish(payload, actor=current_user)


@router.post("/messages/{message_id}/pin", response_model=TelegramChannelEntryMessageRead)
async def pin_message(
    message_id: int,
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[ChannelEntryService, Depends(get_channel_entry_service)],
) -> TelegramChannelEntryMessageRead:
    return await service.pin_message(message_id, actor=current_user)


@router.get("/history", response_model=ChannelEntryHistoryRead)
async def history(
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[ChannelEntryService, Depends(get_channel_entry_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ChannelEntryHistoryRead:
    return await service.history(limit=limit, offset=offset)
