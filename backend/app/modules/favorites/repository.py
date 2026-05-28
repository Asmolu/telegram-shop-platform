from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Favorite, Product


class FavoritesRepository:
    """Database access layer for favorites."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def product_exists(self, product_id: int) -> bool:
        result = await self.session.execute(select(Product.id).where(Product.id == product_id))
        return result.scalar_one_or_none() is not None

    async def get_for_user_product(self, *, user_id: int, product_id: int) -> Favorite | None:
        result = await self.session.execute(
            select(Favorite).where(Favorite.user_id == user_id, Favorite.product_id == product_id)
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, *, user_id: int) -> list[Favorite]:
        result = await self.session.execute(
            select(Favorite)
            .where(Favorite.user_id == user_id)
            .order_by(Favorite.created_at.desc(), Favorite.id.desc())
        )
        return list(result.scalars())

    async def delete_for_user_product(self, *, user_id: int, product_id: int) -> bool:
        result = await self.session.execute(
            delete(Favorite).where(Favorite.user_id == user_id, Favorite.product_id == product_id)
        )
        return bool(result.rowcount)

    def add(self, favorite: Favorite) -> None:
        self.session.add(favorite)
