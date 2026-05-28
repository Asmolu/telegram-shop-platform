from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_current_user, get_db_session, require_roles
from app.db.models import User, UserRole
from app.modules.reviews.schemas import (
    ReviewCreate,
    ReviewList,
    ReviewModerationUpdate,
    ReviewRead,
)
from app.modules.reviews.service import ReviewsService

router = APIRouter(prefix="/reviews", tags=["reviews"])
product_reviews_router = APIRouter(prefix="/products", tags=["reviews"])


def get_reviews_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ReviewsService:
    return ReviewsService(session)


@product_reviews_router.post(
    "/{product_id}/reviews",
    response_model=ReviewRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_product_review(
    product_id: int,
    payload: ReviewCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ReviewsService, Depends(get_reviews_service)],
) -> ReviewRead:
    return await service.create_product_review(
        user_id=current_user.id,
        product_id=product_id,
        payload=payload,
    )


@product_reviews_router.get("/{product_id}/reviews", response_model=ReviewList)
async def list_approved_product_reviews(
    product_id: int,
    service: Annotated[ReviewsService, Depends(get_reviews_service)],
) -> ReviewList:
    return await service.list_approved_product_reviews(product_id)


@router.get("/me", response_model=ReviewList)
async def list_current_user_reviews(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ReviewsService, Depends(get_reviews_service)],
) -> ReviewList:
    return await service.list_current_user_reviews(current_user.id)


@router.patch("/{review_id}/status", response_model=ReviewRead)
async def moderate_review(
    review_id: int,
    payload: ReviewModerationUpdate,
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[ReviewsService, Depends(get_reviews_service)],
) -> ReviewRead:
    return await service.moderate_review(
        review_id=review_id,
        moderator_id=current_user.id,
        payload=payload,
    )
