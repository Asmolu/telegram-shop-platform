from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    Order,
    OrderItem,
    Product,
    ReturnRequest,
    ReturnRequestAttachment,
    ReturnRequestItem,
    ReturnRequestStatus,
)


class ReturnsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_order_for_user(
        self,
        *,
        order_id: int,
        user_id: int,
        for_update: bool = False,
    ) -> Order | None:
        query = (
            select(Order)
            .options(*self._order_loads())
            .where(Order.id == order_id, Order.user_id == user_id)
        )
        if for_update:
            query = query.with_for_update()
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_return_for_order(self, order_id: int) -> ReturnRequest | None:
        result = await self.session.execute(
            self._return_request_query().where(ReturnRequest.order_id == order_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(
        self,
        return_request_id: int,
        *,
        for_update: bool = False,
    ) -> ReturnRequest | None:
        query = self._return_request_query().where(ReturnRequest.id == return_request_id)
        if for_update:
            query = query.with_for_update()
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_all(
        self,
        *,
        limit: int,
        offset: int,
        status: ReturnRequestStatus | None = None,
        order_id: int | None = None,
        user_id: int | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> list[ReturnRequest]:
        conditions = []
        if status is not None:
            conditions.append(ReturnRequest.status == status)
        if order_id is not None:
            conditions.append(ReturnRequest.order_id == order_id)
        if user_id is not None:
            conditions.append(ReturnRequest.user_id == user_id)
        if created_from is not None:
            conditions.append(ReturnRequest.created_at >= created_from)
        if created_to is not None:
            conditions.append(ReturnRequest.created_at <= created_to)

        result = await self.session.execute(
            self._return_request_query()
            .where(*conditions)
            .order_by(ReturnRequest.created_at.desc(), ReturnRequest.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars())

    def add(
        self,
        instance: ReturnRequest | ReturnRequestItem | ReturnRequestAttachment,
    ) -> None:
        self.session.add(instance)

    def _order_loads(self) -> tuple:
        return (
            selectinload(Order.items)
            .selectinload(OrderItem.product)
            .selectinload(Product.images),
            selectinload(Order.items).selectinload(OrderItem.product_variant),
            selectinload(Order.return_request),
        )

    def _return_request_query(self):
        return select(ReturnRequest).options(
            selectinload(ReturnRequest.order),
            selectinload(ReturnRequest.user),
            selectinload(ReturnRequest.items),
            selectinload(ReturnRequest.attachments),
        )
