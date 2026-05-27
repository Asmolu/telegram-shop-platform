from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.modules.users.repository import UsersRepository


class UsersService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = UsersRepository(session)

    async def get_user_by_id(self, user_id: int) -> User | None:
        return await self.repository.get_by_id(user_id)
