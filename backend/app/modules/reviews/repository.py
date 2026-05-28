from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Order, OrderItem, OrderStatus, Product, Review, ReviewStatus


class ReviewsRepository:
    """Database access layer for reviews."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def product_exists(self, product_id: int) -> bool:
        result = await self.session.execute(select(Product.id).where(Product.id == product_id))
        return result.scalar_one_or_none() is not None

    async def get_by_id(self, review_id: int) -> Review | None:
        result = await self.session.execute(select(Review).where(Review.id == review_id))
        return result.scalar_one_or_none()

    async def get_by_user_product(self, *, user_id: int, product_id: int) -> Review | None:
        result = await self.session.execute(
            select(Review).where(Review.user_id == user_id, Review.product_id == product_id)
        )
        return result.scalar_one_or_none()

    async def find_purchase_order_id(self, *, user_id: int, product_id: int) -> int | None:
        result = await self.session.execute(
            select(Order.id)
            .join(OrderItem, OrderItem.order_id == Order.id)
            .where(
                Order.user_id == user_id,
                Order.status != OrderStatus.CANCELLED,
                OrderItem.product_id == product_id,
            )
            .order_by(Order.created_at.desc(), Order.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_approved_for_product(self, *, product_id: int) -> list[Review]:
        result = await self.session.execute(
            select(Review)
            .where(Review.product_id == product_id, Review.status == ReviewStatus.APPROVED)
            .order_by(Review.created_at.desc(), Review.id.desc())
        )
        return list(result.scalars())

    async def list_for_user(self, *, user_id: int) -> list[Review]:
        result = await self.session.execute(
            select(Review)
            .where(Review.user_id == user_id)
            .order_by(Review.created_at.desc(), Review.id.desc())
        )
        return list(result.scalars())

    def add(self, review: Review) -> None:
        self.session.add(review)
