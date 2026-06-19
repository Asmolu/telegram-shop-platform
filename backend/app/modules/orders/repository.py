from collections.abc import Iterable

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    Cart,
    CartItem,
    Order,
    OrderItem,
    OrderStatus,
    Product,
    ProductVariant,
    User,
)


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
            .with_for_update()
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
            .options(*self._order_detail_loads())
            .where(Order.user_id == user_id)
            .order_by(Order.created_at.desc(), Order.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars())

    async def list_all(
        self,
        *,
        limit: int,
        offset: int,
        status: OrderStatus | None = None,
        user_id: int | None = None,
        search: str | None = None,
    ) -> list[Order]:
        conditions = []
        if status is not None:
            conditions.append(Order.status == status)
        if user_id is not None:
            conditions.append(Order.user_id == user_id)
        if search:
            search_value = search.strip()
            search_conditions = [
                Order.order_number.ilike(f"%{search_value}%"),
                Order.contact_name.ilike(f"%{search_value}%"),
                Order.contact_phone.ilike(f"%{search_value}%"),
                User.username.ilike(f"%{search_value}%"),
            ]
            if search_value.isdigit():
                search_conditions.extend(
                    [
                        Order.id == int(search_value),
                        Order.user_id == int(search_value),
                    ]
                )
            conditions.append(or_(*search_conditions))

        result = await self.session.execute(
            select(Order)
            .join(User, User.id == Order.user_id)
            .options(*self._order_detail_loads())
            .where(*conditions)
            .order_by(Order.created_at.desc(), Order.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars())

    async def get_by_id(self, order_id: int) -> Order | None:
        result = await self.session.execute(
            select(Order)
            .options(*self._order_detail_loads())
            .where(Order.id == order_id)
        )
        return result.scalar_one_or_none()

    async def get_for_user(self, *, user_id: int, order_id: int) -> Order | None:
        result = await self.session.execute(
            select(Order)
            .options(*self._order_detail_loads())
            .where(Order.user_id == user_id, Order.id == order_id)
        )
        return result.scalar_one_or_none()

    def add(self, instance: Order | OrderItem) -> None:
        self.session.add(instance)

    async def clear_cart(self, cart_id: int) -> None:
        await self.session.execute(delete(CartItem).where(CartItem.cart_id == cart_id))

    async def clear_cart_items(self, cart_id: int, item_ids: Iterable[int]) -> None:
        unique_ids = sorted(set(item_ids))
        if not unique_ids:
            return

        await self.session.execute(
            delete(CartItem).where(CartItem.cart_id == cart_id, CartItem.id.in_(unique_ids))
        )

    def _order_detail_loads(self) -> tuple:
        return (
            selectinload(Order.user),
            selectinload(Order.items)
            .selectinload(OrderItem.product)
            .selectinload(Product.images),
            selectinload(Order.items).selectinload(OrderItem.product_variant),
            selectinload(Order.manual_payment),
        )
