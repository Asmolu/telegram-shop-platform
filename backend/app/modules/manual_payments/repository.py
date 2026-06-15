from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    ManualPayment,
    ManualPaymentStatus,
    Order,
    ProductVariant,
    SellerPaymentSettings,
    User,
)


class ManualPaymentsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_settings(self) -> SellerPaymentSettings | None:
        result = await self.session.execute(
            select(SellerPaymentSettings).where(SellerPaymentSettings.id == 1)
        )
        return result.scalar_one_or_none()

    async def get_for_order(self, order_id: int) -> ManualPayment | None:
        result = await self.session.execute(
            self._payment_query().where(ManualPayment.order_id == order_id)
        )
        return result.scalar_one_or_none()

    async def get_for_order_owner(
        self,
        *,
        order_id: int,
        user_id: int,
        for_update: bool = False,
    ) -> ManualPayment | None:
        query = (
            self._payment_query()
            .join(Order, Order.id == ManualPayment.order_id)
            .where(ManualPayment.order_id == order_id, Order.user_id == user_id)
        )
        if for_update:
            query = query.with_for_update()
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_id(
        self,
        payment_id: int,
        *,
        for_update: bool = False,
        populate_existing: bool = False,
    ) -> ManualPayment | None:
        query = self._payment_query().where(ManualPayment.id == payment_id)
        if for_update:
            query = query.with_for_update()
        if populate_existing:
            query = query.execution_options(populate_existing=True)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_all(
        self,
        *,
        limit: int,
        offset: int,
        status: ManualPaymentStatus | None = None,
    ) -> list[ManualPayment]:
        conditions = []
        if status is not None:
            conditions.append(ManualPayment.status == status)
        result = await self.session.execute(
            self._payment_query()
            .where(*conditions)
            .order_by(ManualPayment.created_at.desc(), ManualPayment.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars())

    async def list_due_ids(self, *, now: datetime, limit: int = 100) -> list[int]:
        result = await self.session.execute(
            select(ManualPayment.id)
            .where(
                ManualPayment.status.in_(
                    (ManualPaymentStatus.PENDING, ManualPaymentStatus.SUBMITTED)
                ),
                ManualPayment.expires_at <= now,
            )
            .order_by(ManualPayment.expires_at.asc(), ManualPayment.id.asc())
            .limit(limit)
        )
        return list(result.scalars())

    async def lock_variants_by_ids(
        self,
        variant_ids: Iterable[int],
    ) -> dict[int, ProductVariant]:
        unique_ids = sorted(set(variant_ids))
        if not unique_ids:
            return {}
        result = await self.session.execute(
            select(ProductVariant)
            .where(ProductVariant.id.in_(unique_ids))
            .with_for_update()
        )
        return {variant.id: variant for variant in result.scalars()}

    async def get_user_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

    def add(self, instance: ManualPayment | SellerPaymentSettings) -> None:
        self.session.add(instance)

    def _payment_query(self):
        return select(ManualPayment).options(
            selectinload(ManualPayment.order).selectinload(Order.user),
            selectinload(ManualPayment.order).selectinload(Order.items),
        )
