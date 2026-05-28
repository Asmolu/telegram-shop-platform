from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import Favorite
from app.modules.favorites.repository import FavoritesRepository
from app.modules.favorites.schemas import FavoriteCreate, FavoriteList, FavoriteRead


class FavoritesService:
    """Favorite product endpoints."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = FavoritesRepository(session)

    async def list_current_user_favorites(self, user_id: int) -> FavoriteList:
        favorites = await self.repository.list_for_user(user_id=user_id)
        return FavoriteList(items=[FavoriteRead.model_validate(favorite) for favorite in favorites])

    async def add_favorite(self, user_id: int, payload: FavoriteCreate) -> FavoriteRead:
        if not await self.repository.product_exists(payload.product_id):
            raise AppError("Product not found", status.HTTP_404_NOT_FOUND)

        existing_favorite = await self.repository.get_for_user_product(
            user_id=user_id,
            product_id=payload.product_id,
        )
        if existing_favorite is not None:
            return FavoriteRead.model_validate(existing_favorite)

        favorite = Favorite(user_id=user_id, product_id=payload.product_id)
        self.repository.add(favorite)

        try:
            await self.session.commit()
            await self.session.refresh(favorite)
        except IntegrityError as exc:
            await self.session.rollback()
            existing_favorite = await self.repository.get_for_user_product(
                user_id=user_id,
                product_id=payload.product_id,
            )
            if existing_favorite is not None:
                return FavoriteRead.model_validate(existing_favorite)
            raise AppError("Favorite already exists", status.HTTP_409_CONFLICT) from exc

        return FavoriteRead.model_validate(favorite)

    async def remove_favorite(self, *, user_id: int, product_id: int) -> None:
        await self.repository.delete_for_user_product(user_id=user_id, product_id=product_id)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("Favorite removal failed", status.HTTP_409_CONFLICT) from exc
