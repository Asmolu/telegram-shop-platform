from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_current_user, get_db_session
from app.common.http_cache import PRIVATE_NO_STORE_CACHE
from app.db.models import User
from app.modules.analytics.service import IsolatedAnalyticsTracker
from app.modules.cart.schemas import (
    CartItemCreate,
    CartItemSelectionUpdate,
    CartItemUpdate,
    CartRead,
    CartSelectionUpdate,
)
from app.modules.cart.service import CartService

router = APIRouter(prefix="/cart", tags=["cart"])


def get_cart_service(session: Annotated[AsyncSession, Depends(get_db_session)]) -> CartService:
    return CartService(session, analytics_tracker=IsolatedAnalyticsTracker())


@router.get("", response_model=CartRead)
async def get_current_user_cart(
    response: Response,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CartService, Depends(get_cart_service)],
) -> CartRead:
    response.headers["Cache-Control"] = PRIVATE_NO_STORE_CACHE
    return await service.get_current_user_cart(current_user.id)


@router.post("/items", response_model=CartRead, status_code=status.HTTP_201_CREATED)
async def add_item_to_cart(
    payload: CartItemCreate,
    response: Response,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CartService, Depends(get_cart_service)],
) -> CartRead:
    response.headers["Cache-Control"] = PRIVATE_NO_STORE_CACHE
    return await service.add_item(current_user.id, payload)


@router.patch("/items/{item_id}", response_model=CartRead)
async def update_cart_item_quantity(
    item_id: int,
    payload: CartItemUpdate,
    response: Response,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CartService, Depends(get_cart_service)],
) -> CartRead:
    response.headers["Cache-Control"] = PRIVATE_NO_STORE_CACHE
    return await service.update_item_quantity(current_user.id, item_id, payload)


@router.patch("/items/{item_id}/selection", response_model=CartRead)
async def update_cart_item_selection(
    item_id: int,
    payload: CartItemSelectionUpdate,
    response: Response,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CartService, Depends(get_cart_service)],
) -> CartRead:
    response.headers["Cache-Control"] = PRIVATE_NO_STORE_CACHE
    return await service.update_item_selection(current_user.id, item_id, payload)


@router.patch("/selection", response_model=CartRead)
async def update_cart_selection(
    payload: CartSelectionUpdate,
    response: Response,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CartService, Depends(get_cart_service)],
) -> CartRead:
    response.headers["Cache-Control"] = PRIVATE_NO_STORE_CACHE
    return await service.update_selection(current_user.id, payload)


@router.delete("/items/{item_id}", response_model=CartRead)
async def remove_cart_item(
    item_id: int,
    response: Response,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CartService, Depends(get_cart_service)],
) -> CartRead:
    response.headers["Cache-Control"] = PRIVATE_NO_STORE_CACHE
    return await service.remove_item(current_user.id, item_id)


@router.delete("/items", response_model=CartRead)
async def clear_cart(
    response: Response,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CartService, Depends(get_cart_service)],
) -> CartRead:
    response.headers["Cache-Control"] = PRIVATE_NO_STORE_CACHE
    return await service.clear_cart(current_user.id)


@router.delete("", response_model=CartRead)
async def clear_current_user_cart(
    response: Response,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CartService, Depends(get_cart_service)],
) -> CartRead:
    response.headers["Cache-Control"] = PRIVATE_NO_STORE_CACHE
    return await service.clear_cart(current_user.id)
