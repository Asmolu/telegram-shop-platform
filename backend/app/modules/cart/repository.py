from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Cart, CartItem, Product, ProductVariant


class CartRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_user_id(self, user_id: int) -> Cart | None:
        result = await self.session.execute(
            select(Cart)
            .options(
                selectinload(Cart.items).selectinload(CartItem.product),
                selectinload(Cart.items).selectinload(CartItem.product_variant),
            )
            .where(Cart.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_item_for_user(self, *, user_id: int, item_id: int) -> CartItem | None:
        result = await self.session.execute(
            select(CartItem)
            .join(Cart)
            .options(
                selectinload(CartItem.product),
                selectinload(CartItem.product_variant),
            )
            .where(Cart.user_id == user_id, CartItem.id == item_id)
        )
        return result.scalar_one_or_none()

    async def get_item_by_cart_and_variant(
        self,
        *,
        cart_id: int,
        product_variant_id: int,
    ) -> CartItem | None:
        result = await self.session.execute(
            select(CartItem)
            .options(
                selectinload(CartItem.product),
                selectinload(CartItem.product_variant),
            )
            .where(
                CartItem.cart_id == cart_id,
                CartItem.product_variant_id == product_variant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_product_by_id(self, product_id: int) -> Product | None:
        return await self.session.get(Product, product_id)

    async def get_product_variant_by_id(self, product_variant_id: int) -> ProductVariant | None:
        return await self.session.get(ProductVariant, product_variant_id)

    def add(self, instance: Cart | CartItem) -> None:
        self.session.add(instance)

    async def delete_item(self, item: CartItem) -> None:
        await self.session.delete(item)

    async def clear_cart(self, cart_id: int) -> None:
        await self.session.execute(delete(CartItem).where(CartItem.cart_id == cart_id))
