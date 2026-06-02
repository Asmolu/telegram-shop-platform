from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.models import (
    PendingSellerRegistration,
    SellerCredential,
    SellerRegistrationStatus,
    User,
)

ACTIVE_SELLER_REGISTRATION_STATUSES = (
    SellerRegistrationStatus.PENDING,
    SellerRegistrationStatus.AWAITING_APPROVAL,
    SellerRegistrationStatus.APPROVED,
)


class SellerAuthRepository:
    """Database access for seller credentials and pending registrations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add_pending_registration(self, registration: PendingSellerRegistration) -> None:
        self.session.add(registration)

    def add_seller_credential(self, credential: SellerCredential) -> None:
        self.session.add(credential)

    def add_user(self, user: User) -> None:
        self.session.add(user)

    async def get_credential_by_email(self, email: str) -> SellerCredential | None:
        result = await self.session.execute(
            select(SellerCredential)
            .options(joinedload(SellerCredential.user))
            .where(SellerCredential.email == email)
        )
        return result.scalar_one_or_none()

    async def get_credential_by_user_id(self, user_id: int) -> SellerCredential | None:
        result = await self.session.execute(
            select(SellerCredential).where(SellerCredential.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_active_pending_by_email(
        self,
        *,
        email: str,
        now: datetime,
    ) -> PendingSellerRegistration | None:
        result = await self.session.execute(
            select(PendingSellerRegistration)
            .where(
                PendingSellerRegistration.email == email,
                PendingSellerRegistration.status.in_(ACTIVE_SELLER_REGISTRATION_STATUSES),
                PendingSellerRegistration.expires_at > now,
            )
            .order_by(PendingSellerRegistration.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_pending_by_id(
        self,
        registration_id: int,
    ) -> PendingSellerRegistration | None:
        return await self.session.get(PendingSellerRegistration, registration_id)

    async def get_pending_by_start_token_hash(
        self,
        token_hash: str,
    ) -> PendingSellerRegistration | None:
        result = await self.session.execute(
            select(PendingSellerRegistration).where(
                PendingSellerRegistration.bot_start_token_hash == token_hash
            )
        )
        return result.scalar_one_or_none()

    async def get_user_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()
