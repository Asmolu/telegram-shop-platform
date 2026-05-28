from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_current_user, get_db_session, require_roles
from app.db.models import ReviewStatus, User, UserRole
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


@router.get("/admin", response_model=ReviewList)
async def list_reviews(
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[ReviewsService, Depends(get_reviews_service)],
    status_filter: Annotated[ReviewStatus | None, Query(alias="status")] = None,
) -> ReviewList:
    return await service.list_reviews(status_filter)


@router.get("/admin/{review_id}", response_model=ReviewRead)
async def get_review(
    review_id: int,
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[ReviewsService, Depends(get_reviews_service)],
) -> ReviewRead:
    return await service.get_review(review_id)


@router.patch("/admin/{review_id}/approve", response_model=ReviewRead)
async def approve_review(
    review_id: int,
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[ReviewsService, Depends(get_reviews_service)],
) -> ReviewRead:
    return await service.approve_review(review_id=review_id, moderator_id=current_user.id)


@router.patch("/admin/{review_id}/reject", response_model=ReviewRead)
async def reject_review(
    review_id: int,
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[ReviewsService, Depends(get_reviews_service)],
) -> ReviewRead:
    return await service.reject_review(review_id=review_id, moderator_id=current_user.id)


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
