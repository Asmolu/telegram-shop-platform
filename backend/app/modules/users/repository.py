from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


class UsersRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

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
