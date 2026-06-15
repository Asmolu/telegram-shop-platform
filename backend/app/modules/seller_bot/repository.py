from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.db.models import (
    Order,
    OrderItem,
    OrderStatus,
    Product,
    SellerCredential,
    User,
    UserRole,
)


class SellerBotRepository:
    """Database access for Bot 2 seller security commands."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_sellers(self, *, limit: int) -> tuple[list[tuple[User, SellerCredential]], int]:
        filters = (User.role.in_((UserRole.SELLER, UserRole.ADMIN)),)
        sellers_result = await self.session.execute(
            select(User, SellerCredential)
            .join(SellerCredential, SellerCredential.user_id == User.id)
            .where(*filters)
            .order_by(User.created_at.desc(), User.id.desc())
            .limit(limit)
        )
        count_result = await self.session.execute(
            select(func.count(User.id))
            .join(SellerCredential, SellerCredential.user_id == User.id)
            .where(*filters)
        )
        return list(sellers_result.tuples().all()), count_result.scalar_one()

    async def get_seller_user(self, user_id: int) -> User | None:
        result = await self.session.execute(
            select(User)
            .options(joinedload(User.seller_credential))
            .where(User.id == user_id, User.role.in_((UserRole.SELLER, UserRole.ADMIN)))
        )
        return result.scalar_one_or_none()

    async def list_active_orders(self, *, limit: int) -> tuple[list[Order], int]:
        filters = (Order.status.notin_((OrderStatus.DELIVERED, OrderStatus.CANCELLED)),)
        orders_result = await self.session.execute(
            select(Order)
            .options(
                selectinload(Order.user),
                selectinload(Order.items)
                .selectinload(OrderItem.product)
                .selectinload(Product.images),
                selectinload(Order.manual_payment),
            )
            .where(*filters)
            .order_by(Order.created_at.asc(), Order.id.asc())
            .limit(limit)
        )
        count_result = await self.session.execute(
            select(func.count(Order.id)).where(*filters)
        )
        return list(orders_result.scalars().all()), count_result.scalar_one()
