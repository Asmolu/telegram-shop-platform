from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import TelegramChannel, TelegramChannelEntryMessage


class ChannelEntryRepository:
    """Database access layer for Telegram channel entry publishing."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_active_channels(self) -> list[TelegramChannel]:
        result = await self.session.execute(
            select(TelegramChannel)
            .where(TelegramChannel.is_active.is_(True))
            .order_by(TelegramChannel.created_at.desc(), TelegramChannel.id.desc())
        )
        return list(result.scalars().all())

    async def get_channel_by_id(self, channel_id: int) -> TelegramChannel | None:
        result = await self.session.execute(
            select(TelegramChannel).where(TelegramChannel.id == channel_id)
        )
        return result.scalar_one_or_none()

    async def get_active_channel_by_id(self, channel_id: int) -> TelegramChannel | None:
        result = await self.session.execute(
            select(TelegramChannel).where(
                TelegramChannel.id == channel_id,
                TelegramChannel.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_channel_by_chat_id(self, chat_id: str) -> TelegramChannel | None:
        result = await self.session.execute(
            select(TelegramChannel).where(TelegramChannel.chat_id == chat_id)
        )
        return result.scalar_one_or_none()

    def add_channel(self, channel: TelegramChannel) -> None:
        self.session.add(channel)

    def add_message(self, message: TelegramChannelEntryMessage) -> None:
        self.session.add(message)

    async def get_message_by_id(self, message_id: int) -> TelegramChannelEntryMessage | None:
        result = await self.session.execute(
            select(TelegramChannelEntryMessage)
            .options(selectinload(TelegramChannelEntryMessage.channel))
            .where(TelegramChannelEntryMessage.id == message_id)
        )
        return result.scalar_one_or_none()

    async def list_messages(
        self,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[TelegramChannelEntryMessage], int]:
        result = await self.session.execute(
            select(TelegramChannelEntryMessage)
            .options(selectinload(TelegramChannelEntryMessage.channel))
            .order_by(
                TelegramChannelEntryMessage.created_at.desc(),
                TelegramChannelEntryMessage.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        count_result = await self.session.execute(
            select(func.count(TelegramChannelEntryMessage.id))
        )
        return list(result.scalars().all()), count_result.scalar_one()
