from datetime import UTC, datetime

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PageMeta
from app.core.errors import AppError
from app.db.models import User, UserBlock
from app.modules.audit.service import AuditService, NoopAuditService
from app.modules.users.repository import UsersRepository
from app.modules.users.schemas import (
    PersonalDataRead,
    PersonalDataUpdate,
    UserBlockCreate,
    UserBlockList,
    UserBlockRead,
    UserList,
    UserRead,
)

BLOCKED_USER_MESSAGE = "Ваш аккаунт ограничен. Свяжитесь с продавцом."


class UsersService:
    def __init__(
        self,
        session: AsyncSession,
        audit_service: AuditService | None = None,
    ) -> None:
        self.session = session
        self.repository = UsersRepository(session)
        self.audit_service = audit_service or NoopAuditService()

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

    async def list_active_blocks(self) -> UserBlockList:
        blocks = await self.repository.list_active_blocks()
        return UserBlockList(items=[UserBlockRead.model_validate(block) for block in blocks])

    async def create_block(
        self,
        payload: UserBlockCreate,
        *,
        actor_user_id: int,
    ) -> UserBlockRead:
        target_user = await self._resolve_block_target(payload)
        telegram_id = payload.telegram_id or (target_user.telegram_id if target_user else None)
        telegram_username = payload.telegram_username or _normalized_username_for_user(target_user)
        duplicate = await self.repository.find_active_block(
            user_id=target_user.id if target_user is not None else None,
            telegram_id=telegram_id,
            telegram_username=telegram_username,
        )
        if duplicate is not None:
            return UserBlockRead.model_validate(duplicate)

        user_block = UserBlock(
            user_id=target_user.id if target_user is not None else None,
            telegram_id=telegram_id,
            telegram_username=telegram_username,
            reason=payload.reason,
            blocked_by_user_id=actor_user_id,
            user=target_user,
            blocked_by=await self.repository.get_by_id(actor_user_id),
        )
        self.repository.add_block(user_block)
        try:
            await self.session.flush()
            await self.audit_service.record_action(
                actor_user_id=actor_user_id,
                action="user.blocked",
                entity_type="user_block",
                entity_id=user_block.id,
                after_data={
                    "user_id": user_block.user_id,
                    "telegram_id": user_block.telegram_id,
                    "telegram_username": user_block.telegram_username,
                    "reason": user_block.reason,
                },
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("Active user block already exists", status.HTTP_409_CONFLICT) from exc
        except Exception:
            await self.session.rollback()
            raise
        return UserBlockRead.model_validate(user_block)

    async def unblock(self, block_id: int, *, actor_user_id: int) -> UserBlockRead:
        user_block = await self.repository.get_block_by_id(block_id)
        if user_block is None or user_block.unblocked_at is not None:
            raise AppError("User block not found", status.HTTP_404_NOT_FOUND)

        before_data = self.audit_service.snapshot(
            user_block,
            (
                "user_id",
                "telegram_id",
                "telegram_username",
                "reason",
                "unblocked_at",
                "unblocked_by_user_id",
            ),
        )
        user_block.unblocked_at = datetime.now(UTC)
        user_block.unblocked_by_user_id = actor_user_id
        try:
            await self.audit_service.record_action(
                actor_user_id=actor_user_id,
                action="user.unblocked",
                entity_type="user_block",
                entity_id=user_block.id,
                before_data=before_data,
                after_data=self.audit_service.snapshot(
                    user_block,
                    (
                        "user_id",
                        "telegram_id",
                        "telegram_username",
                        "reason",
                        "unblocked_at",
                        "unblocked_by_user_id",
                    ),
                ),
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("User unblock failed", status.HTTP_409_CONFLICT) from exc
        except Exception:
            await self.session.rollback()
            raise
        return UserBlockRead.model_validate(user_block)

    async def assert_user_not_blocked(self, user_id: int) -> None:
        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise AppError("User not found", status.HTTP_404_NOT_FOUND)
        active_block = await self.repository.find_active_block_for_user(user)
        if active_block is not None:
            raise AppError(BLOCKED_USER_MESSAGE, status.HTTP_403_FORBIDDEN)

    async def attach_pending_blocks_for_user(self, user: User) -> None:
        usernames = _normalized_usernames_for_user(user)
        if not usernames:
            return
        if user.id is None:
            await self.session.flush()
        pending_blocks = await self.repository.list_matching_pending_username_blocks(usernames)
        for user_block in pending_blocks:
            if user_block.user_id is None:
                user_block.user_id = user.id
            if user_block.telegram_id is None:
                user_block.telegram_id = user.telegram_id

    async def _resolve_block_target(self, payload: UserBlockCreate) -> User | None:
        if payload.telegram_id is not None:
            user = await self.repository.get_by_telegram_id(payload.telegram_id)
            if user is not None:
                return user
        if payload.telegram_username is not None:
            return await self.repository.get_by_telegram_username(payload.telegram_username)
        return None


def _normalized_username_for_user(user: User | None) -> str | None:
    if user is None:
        return None
    for username in (user.username, user.telegram_username):
        if username and username.strip():
            return username.strip().removeprefix("@").lower()
    return None


def _normalized_usernames_for_user(user: User) -> set[str]:
    return {
        username.strip().removeprefix("@").lower()
        for username in (user.username, user.telegram_username)
        if username and username.strip()
    }
