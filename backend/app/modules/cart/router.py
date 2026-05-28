from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_current_user, get_db_session
from app.db.models import User
from app.modules.cart.schemas import CartItemCreate, CartItemUpdate, CartRead
from app.modules.cart.service import CartService

router = APIRouter(prefix="/cart", tags=["cart"])


def get_cart_service(session: Annotated[AsyncSession, Depends(get_db_session)]) -> CartService:
    return CartService(session)


@router.get("", response_model=CartRead)
async def get_current_user_cart(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CartService, Depends(get_cart_service)],
) -> CartRead:
    return await service.get_current_user_cart(current_user.id)


@router.post("/items", response_model=CartRead, status_code=status.HTTP_201_CREATED)
async def add_item_to_cart(
    payload: CartItemCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CartService, Depends(get_cart_service)],
) -> CartRead:
    return await service.add_item(current_user.id, payload)


@router.patch("/items/{item_id}", response_model=CartRead)
async def update_cart_item_quantity(
    item_id: int,
    payload: CartItemUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CartService, Depends(get_cart_service)],
) -> CartRead:
    return await service.update_item_quantity(current_user.id, item_id, payload)


@router.delete("/items/{item_id}", response_model=CartRead)
async def remove_cart_item(
    item_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CartService, Depends(get_cart_service)],
) -> CartRead:
    return await service.remove_item(current_user.id, item_id)


@router.delete("/items", response_model=CartRead)
async def clear_cart(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CartService, Depends(get_cart_service)],
) -> CartRead:
    return await service.clear_cart(current_user.id)


@router.delete("", response_model=CartRead)
async def clear_current_user_cart(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CartService, Depends(get_cart_service)],
) -> CartRead:
    return await service.clear_cart(current_user.id)
