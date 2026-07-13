import logging
from datetime import UTC, datetime

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.cache import CacheService, public_product_reviews_key, review_cache_patterns
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import Review, ReviewStatus
from app.modules.analytics.service import AnalyticsTracker
from app.modules.audit.service import AuditService, NoopAuditService
from app.modules.reviews.repository import ReviewsRepository
from app.modules.reviews.schemas import ReviewCreate, ReviewList, ReviewModerationUpdate, ReviewRead
from app.modules.users.service import UsersService

logger = logging.getLogger(__name__)
REVIEW_AUDIT_FIELDS = ("status", "moderated_at", "moderated_by_id")


class ReviewsService:
    """Review creation, public listing, and moderation."""

    def __init__(
        self,
        session: AsyncSession,
        analytics_tracker: AnalyticsTracker | None = None,
        audit_service: AuditService | None = None,
        cache: CacheService | None = None,
        users_service: UsersService | None = None,
    ) -> None:
        self.session = session
        self.repository = ReviewsRepository(session)
        self.analytics_tracker = analytics_tracker
        self.audit_service = audit_service or NoopAuditService()
        self.cache = cache
        self.users_service = users_service or UsersService(session)

    async def create_product_review(
        self,
        *,
        user_id: int,
        product_id: int,
        payload: ReviewCreate,
    ) -> ReviewRead:
        await self.users_service.assert_user_not_blocked(user_id)
        if not await self.repository.product_exists(product_id):
            raise AppError("Product not found", status.HTTP_404_NOT_FOUND)

        existing_review = await self.repository.get_by_user_product(
            user_id=user_id,
            product_id=product_id,
        )
        if existing_review is not None:
            raise AppError("Product already reviewed", status.HTTP_409_CONFLICT)

        order_id = await self.repository.find_purchase_order_id(
            user_id=user_id,
            product_id=product_id,
        )
        if order_id is None:
            raise AppError("Product purchase required for review", status.HTTP_403_FORBIDDEN)

        review = Review(
            user_id=user_id,
            product_id=product_id,
            order_id=order_id,
            rating=payload.rating,
            text=payload.text,
            status=ReviewStatus.PENDING,
        )
        self.repository.add(review)

        try:
            await self.session.commit()
            await self.session.refresh(review)
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("Product already reviewed", status.HTTP_409_CONFLICT) from exc

        await self._track_event(
            "review.created",
            user_id=user_id,
            product_id=product_id,
            order_id=order_id,
            metadata={"review_id": review.id, "rating": review.rating},
        )
        return ReviewRead.model_validate(review)

    async def list_approved_product_reviews(self, product_id: int) -> ReviewList:
        cache_key = public_product_reviews_key(product_id)
        if self.cache is not None:
            cached = await self.cache.get_model(cache_key, ReviewList)
            if cached is not None:
                return cached

        if not await self.repository.product_exists(product_id):
            raise AppError("Product not found", status.HTTP_404_NOT_FOUND)
        reviews = await self.repository.list_approved_for_product(product_id=product_id)
        result = ReviewList(items=[ReviewRead.model_validate(review) for review in reviews])
        if self.cache is not None:
            await self.cache.set_model(cache_key, result, settings.cache_reviews_ttl_seconds)
        return result

    async def list_current_user_reviews(self, user_id: int) -> ReviewList:
        reviews = await self.repository.list_for_user(user_id=user_id)
        return ReviewList(items=[ReviewRead.model_validate(review) for review in reviews])

    async def list_reviews(self, status: ReviewStatus | None = None) -> ReviewList:
        reviews = await self.repository.list_all(status=status)
        return ReviewList(items=[ReviewRead.model_validate(review) for review in reviews])

    async def get_review(self, review_id: int) -> ReviewRead:
        review = await self.repository.get_by_id(review_id)
        if review is None:
            raise AppError("Review not found", status.HTTP_404_NOT_FOUND)
        return ReviewRead.model_validate(review)

    async def approve_review(self, *, review_id: int, moderator_id: int) -> ReviewRead:
        return await self.moderate_review(
            review_id=review_id,
            moderator_id=moderator_id,
            payload=ReviewModerationUpdate(status=ReviewStatus.APPROVED),
        )

    async def reject_review(self, *, review_id: int, moderator_id: int) -> ReviewRead:
        return await self.moderate_review(
            review_id=review_id,
            moderator_id=moderator_id,
            payload=ReviewModerationUpdate(status=ReviewStatus.REJECTED),
        )

    async def moderate_review(
        self,
        *,
        review_id: int,
        moderator_id: int,
        payload: ReviewModerationUpdate,
    ) -> ReviewRead:
        review = await self.repository.get_by_id(review_id)
        if review is None:
            raise AppError("Review not found", status.HTTP_404_NOT_FOUND)

        before_data = self.audit_service.snapshot(review, REVIEW_AUDIT_FIELDS)
        review.status = payload.status
        review.moderated_at = datetime.now(UTC)
        review.moderated_by_id = moderator_id

        try:
            await self.audit_service.record_action(
                actor_user_id=moderator_id,
                action=(
                    "review.approved"
                    if payload.status == ReviewStatus.APPROVED
                    else "review.rejected"
                ),
                entity_type="review",
                entity_id=review.id,
                before_data=before_data,
                after_data=self.audit_service.snapshot(review, REVIEW_AUDIT_FIELDS),
                metadata={"product_id": review.product_id, "user_id": review.user_id},
            )
            await self.session.commit()
            await self.session.refresh(review)
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("Review moderation failed", status.HTTP_409_CONFLICT) from exc

        await self._invalidate_public_cache(product_id=review.product_id)
        return ReviewRead.model_validate(review)

    async def _track_event(
        self,
        event_name: str,
        *,
        user_id: int,
        product_id: int,
        order_id: int | None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        if self.analytics_tracker is None:
            return
        try:
            await self.analytics_tracker.track(
                event_name,
                user_id=user_id,
                product_id=product_id,
                order_id=order_id,
                metadata=metadata,
            )
        except Exception:
            logger.warning("Failed to track review analytics event %s", event_name, exc_info=True)

    async def _invalidate_public_cache(self, *, product_id: int | None = None) -> None:
        if self.cache is None:
            return
        await self.cache.delete_patterns(*review_cache_patterns(product_id))
