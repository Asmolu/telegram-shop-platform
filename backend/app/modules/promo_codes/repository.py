from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Cart, CartItem, CouponUsage, PromoCode


class PromoCodesRepository:
    """Database access layer for promo codes."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, *, limit: int, offset: int) -> tuple[list[PromoCode], int]:
        promo_codes_query = (
            select(PromoCode)
            .order_by(PromoCode.created_at.desc(), PromoCode.id.desc())
            .limit(limit)
            .offset(offset)
        )
        count_query = select(func.count(PromoCode.id))

        promo_codes_result = await self.session.execute(promo_codes_query)
        count_result = await self.session.execute(count_query)
        return list(promo_codes_result.scalars().all()), count_result.scalar_one()

    async def get_by_id(self, promo_code_id: int) -> PromoCode | None:
        result = await self.session.execute(
            select(PromoCode).where(PromoCode.id == promo_code_id)
        )
        return result.scalar_one_or_none()

    async def get_by_ids(self, promo_code_ids: set[int]) -> dict[int, PromoCode]:
        if not promo_code_ids:
            return {}
        result = await self.session.execute(
            select(PromoCode).where(PromoCode.id.in_(promo_code_ids))
        )
        return {promo_code.id: promo_code for promo_code in result.scalars().all()}

    async def get_by_code(self, code: str, *, for_update: bool = False) -> PromoCode | None:
        query = select(PromoCode).where(PromoCode.code == code)
        if for_update:
            query = query.with_for_update()

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def count_usages(self, promo_code_id: int) -> int:
        result = await self.session.execute(
            select(func.count(CouponUsage.id)).where(CouponUsage.promo_code_id == promo_code_id)
        )
        return result.scalar_one()

    async def count_user_usages(self, *, promo_code_id: int, user_id: int) -> int:
        result = await self.session.execute(
            select(func.count(CouponUsage.id)).where(
                CouponUsage.promo_code_id == promo_code_id,
                CouponUsage.user_id == user_id,
            )
        )
        return result.scalar_one()

    async def get_cart_for_validation(self, user_id: int) -> Cart | None:
        result = await self.session.execute(
            select(Cart)
            .options(selectinload(Cart.items).selectinload(CartItem.product))
            .where(Cart.user_id == user_id)
        )
        return result.scalar_one_or_none()

    def add(self, instance: PromoCode | CouponUsage) -> None:
        self.session.add(instance)

    async def delete(self, promo_code: PromoCode) -> None:
        await self.session.delete(promo_code)


def calculate_cart_subtotal(cart: Cart) -> Decimal:
    return sum(
        (item.product.base_price * item.quantity for item in cart.items),
        Decimal("0.00"),
    )
