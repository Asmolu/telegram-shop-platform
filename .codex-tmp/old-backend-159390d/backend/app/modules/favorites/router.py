from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_current_user, get_db_session
from app.common.http_cache import PRIVATE_NO_STORE_CACHE
from app.db.models import User
from app.modules.analytics.service import IsolatedAnalyticsTracker
from app.modules.favorites.schemas import FavoriteCreate, FavoriteList, FavoriteRead
from app.modules.favorites.service import FavoritesService

router = APIRouter(prefix="/favorites", tags=["favorites"])


def get_favorites_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> FavoritesService:
    return FavoritesService(session, analytics_tracker=IsolatedAnalyticsTracker())


@router.get("", response_model=FavoriteList)
async def list_current_user_favorites(
    response: Response,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[FavoritesService, Depends(get_favorites_service)],
) -> FavoriteList:
    response.headers["Cache-Control"] = PRIVATE_NO_STORE_CACHE
    return await service.list_current_user_favorites(current_user.id)


@router.post("", response_model=FavoriteRead, status_code=status.HTTP_201_CREATED)
async def add_favorite(
    payload: FavoriteCreate,
    response: Response,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[FavoritesService, Depends(get_favorites_service)],
) -> FavoriteRead:
    response.headers["Cache-Control"] = PRIVATE_NO_STORE_CACHE
    return await service.add_favorite(current_user.id, payload)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_favorite(
    product_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[FavoritesService, Depends(get_favorites_service)],
) -> Response:
    await service.remove_favorite(user_id=current_user.id, product_id=product_id)
    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers={"Cache-Control": PRIVATE_NO_STORE_CACHE},
    )
