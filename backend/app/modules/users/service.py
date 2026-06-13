from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PageMeta
from app.core.errors import AppError
from app.db.models import User
from app.modules.users.repository import UsersRepository
from app.modules.users.schemas import PersonalDataRead, PersonalDataUpdate, UserList, UserRead


class UsersService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = UsersRepository(session)

    async def get_user_by_id(self, user_id: int) -> User | None:
        return await self.repository.get_by_id(user_id)

    async def list_users(self, *, limit: int, offset: int) -> UserList:
        users, total = await self.repository.list(limit=limit, offset=offset)
        return UserList(
            items=[UserRead.model_validate(user) for user in users],
            meta=PageMeta(limit=limit, offset=offset, total=total),
        )

    async def get_user_detail(self, user_id: int) -> UserRead:
        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise AppError("User not found", status.HTTP_404_NOT_FOUND)
        return UserRead.model_validate(user)

    def get_personal_data(self, user: User) -> PersonalDataRead:
        return PersonalDataRead.model_validate(user)

    async def update_personal_data(
        self,
        user: User,
        payload: PersonalDataUpdate,
    ) -> PersonalDataRead:
        self.repository.set_personal_data(user, payload.model_dump())
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        return PersonalDataRead.model_validate(user)
