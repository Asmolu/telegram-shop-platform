import logging

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import Favorite
from app.modules.analytics.service import AnalyticsTracker
from app.modules.favorites.repository import FavoritesRepository
from app.modules.favorites.schemas import FavoriteCreate, FavoriteList, FavoriteRead

logger = logging.getLogger(__name__)


class FavoritesService:
    """Favorite product endpoints."""

    def __init__(
        self,
        session: AsyncSession,
        analytics_tracker: AnalyticsTracker | None = None,
    ) -> None:
        self.session = session
        self.repository = FavoritesRepository(session)
        self.analytics_tracker = analytics_tracker

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

        await self._track_event(
            "favorite.added",
            user_id=user_id,
            product_id=payload.product_id,
            metadata={"favorite_id": favorite.id},
        )
        return FavoriteRead.model_validate(favorite)

    async def remove_favorite(self, *, user_id: int, product_id: int) -> None:
        await self.repository.delete_for_user_product(user_id=user_id, product_id=product_id)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("Favorite removal failed", status.HTTP_409_CONFLICT) from exc

    async def _track_event(
        self,
        event_name: str,
        *,
        user_id: int,
        product_id: int,
        metadata: dict[str, object] | None = None,
    ) -> None:
        if self.analytics_tracker is None:
            return
        try:
            await self.analytics_tracker.track(
                event_name,
                user_id=user_id,
                product_id=product_id,
                metadata=metadata,
            )
        except Exception:
            logger.warning("Failed to track favorite analytics event %s", event_name, exc_info=True)
