from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import User, UserBlock


class UsersRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

    async def get_by_telegram_username(self, telegram_username: str) -> User | None:
        normalized = telegram_username.lower()
        result = await self.session.execute(
            select(User).where(
                or_(
                    func.lower(User.username) == normalized,
                    func.lower(User.telegram_username) == normalized,
                )
            )
        )
        return result.scalars().first()

    async def list(self, *, limit: int, offset: int) -> tuple[list[User], int]:
        users_query = (
            select(User)
            .order_by(User.created_at.desc(), User.id.desc())
            .limit(limit)
            .offset(offset)
        )
        count_query = select(func.count(User.id))

        users_result = await self.session.execute(users_query)
        count_result = await self.session.execute(count_query)
        return list(users_result.scalars().all()), count_result.scalar_one()

    def add(self, user: User) -> None:
        self.session.add(user)

    def set_personal_data(self, user: User, values: dict[str, object]) -> None:
        for field, value in values.items():
            setattr(user, field, value)

    async def list_active_blocks(self) -> list[UserBlock]:
        result = await self.session.execute(
            select(UserBlock)
            .options(
                selectinload(UserBlock.user),
                selectinload(UserBlock.blocked_by),
            )
            .where(UserBlock.unblocked_at.is_(None))
            .order_by(UserBlock.blocked_at.desc(), UserBlock.id.desc())
        )
        return list(result.scalars().all())

    async def get_block_by_id(self, block_id: int) -> UserBlock | None:
        result = await self.session.execute(
            select(UserBlock)
            .options(
                selectinload(UserBlock.user),
                selectinload(UserBlock.blocked_by),
            )
            .where(UserBlock.id == block_id)
        )
        return result.scalar_one_or_none()

    async def find_active_block(
        self,
        *,
        user_id: int | None = None,
        telegram_id: int | None = None,
        telegram_username: str | None = None,
    ) -> UserBlock | None:
        criteria = []
        if user_id is not None:
            criteria.append(UserBlock.user_id == user_id)
        if telegram_id is not None:
            criteria.append(UserBlock.telegram_id == telegram_id)
        if telegram_username is not None:
            criteria.append(UserBlock.telegram_username == telegram_username)
        if not criteria:
            return None

        result = await self.session.execute(
            select(UserBlock)
            .options(
                selectinload(UserBlock.user),
                selectinload(UserBlock.blocked_by),
            )
            .where(UserBlock.unblocked_at.is_(None), or_(*criteria))
            .order_by(UserBlock.blocked_at.desc(), UserBlock.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def find_active_block_for_user(self, user: User) -> UserBlock | None:
        usernames = {
            username.lower()
            for username in (user.username, user.telegram_username)
            if username
        }
        criteria = [
            UserBlock.user_id == user.id,
            UserBlock.telegram_id == user.telegram_id,
        ]
        if usernames:
            criteria.append(UserBlock.telegram_username.in_(usernames))

        result = await self.session.execute(
            select(UserBlock)
            .where(UserBlock.unblocked_at.is_(None), or_(*criteria))
            .order_by(UserBlock.blocked_at.desc(), UserBlock.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_matching_pending_username_blocks(self, usernames: set[str]) -> list[UserBlock]:
        if not usernames:
            return []
        result = await self.session.execute(
            select(UserBlock).where(
                UserBlock.unblocked_at.is_(None),
                UserBlock.telegram_username.in_(usernames),
                or_(UserBlock.user_id.is_(None), UserBlock.telegram_id.is_(None)),
            )
        )
        return list(result.scalars().all())

    def add_block(self, user_block: UserBlock) -> None:
        self.session.add(user_block)
