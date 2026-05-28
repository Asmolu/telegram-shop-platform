from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Cart, CartItem, Order, OrderItem, ProductVariant


class OrdersRepository:
    """Database access layer for orders."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_cart_for_checkout(self, user_id: int) -> Cart | None:
        result = await self.session.execute(
            select(Cart)
            .options(
                selectinload(Cart.items).selectinload(CartItem.product),
                selectinload(Cart.items).selectinload(CartItem.product_variant),
            )
            .where(Cart.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def lock_variants_by_ids(self, variant_ids: Iterable[int]) -> dict[int, ProductVariant]:
        unique_ids = sorted(set(variant_ids))
        if not unique_ids:
            return {}

        result = await self.session.execute(
            select(ProductVariant)
            .where(ProductVariant.id.in_(unique_ids))
            .with_for_update()
        )
        return {variant.id: variant for variant in result.scalars()}

    async def list_for_user(self, *, user_id: int, limit: int, offset: int) -> list[Order]:
        result = await self.session.execute(
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.user_id == user_id)
            .order_by(Order.created_at.desc(), Order.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars())

    async def list_all(self, *, limit: int, offset: int) -> list[Order]:
        result = await self.session.execute(
            select(Order)
            .options(selectinload(Order.items))
            .order_by(Order.created_at.desc(), Order.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars())

    async def get_by_id(self, order_id: int) -> Order | None:
        result = await self.session.execute(
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.id == order_id)
        )
        return result.scalar_one_or_none()

    async def get_for_user(self, *, user_id: int, order_id: int) -> Order | None:
        result = await self.session.execute(
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.user_id == user_id, Order.id == order_id)
        )
        return result.scalar_one_or_none()

    def add(self, instance: Order | OrderItem) -> None:
        self.session.add(instance)

    async def clear_cart(self, cart_id: int) -> None:
        await self.session.execute(delete(CartItem).where(CartItem.cart_id == cart_id))
