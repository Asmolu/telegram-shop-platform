from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.common.deps import get_current_user
from app.core.errors import AppError
from app.db.models import Favorite, Review, ReviewStatus, User, UserRole
from app.main import create_app
from app.modules.favorites.router import get_favorites_service
from app.modules.favorites.schemas import FavoriteCreate
from app.modules.favorites.service import FavoritesService
from app.modules.reviews.router import get_reviews_service
from app.modules.reviews.schemas import ReviewCreate, ReviewModerationUpdate
from app.modules.reviews.service import ReviewsService


class DummySession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def refresh(self, _: object) -> None:
        return None


class FakeAnalyticsTracker:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    async def track(self, event_name: str, **payload: object) -> None:
        self.events.append((event_name, payload))


class FakeAuditService:
    def __init__(self) -> None:
        self.logs: list[dict[str, object]] = []

    async def record_action(self, **payload: object) -> None:
        self.logs.append(payload)

    def snapshot(self, instance: object, fields: tuple[str, ...]) -> dict[str, object]:
        return {field: getattr(instance, field) for field in fields}


class FakeReviewsRepository:
    def __init__(self) -> None:
        self.product_ids = {1}
        self.purchase_order_ids: dict[tuple[int, int], int] = {}
        self.reviews: dict[int, Review] = {}
        self.next_review_id = 1

    async def product_exists(self, product_id: int) -> bool:
        return product_id in self.product_ids

    async def get_by_id(self, review_id: int) -> Review | None:
        return self.reviews.get(review_id)

    async def get_by_user_product(self, *, user_id: int, product_id: int) -> Review | None:
        return next(
            (
                review
                for review in self.reviews.values()
                if review.user_id == user_id and review.product_id == product_id
            ),
            None,
        )

    async def find_purchase_order_id(self, *, user_id: int, product_id: int) -> int | None:
        return self.purchase_order_ids.get((user_id, product_id))

    async def list_approved_for_product(self, *, product_id: int) -> list[Review]:
        return [
            review
            for review in self.reviews.values()
            if review.product_id == product_id and review.status == ReviewStatus.APPROVED
        ]

    async def list_for_user(self, *, user_id: int) -> list[Review]:
        return [review for review in self.reviews.values() if review.user_id == user_id]

    async def list_all(self, *, status: ReviewStatus | None = None) -> list[Review]:
        if status is None:
            return list(self.reviews.values())
        return [review for review in self.reviews.values() if review.status == status]

    def add(self, review: Review) -> None:
        review.id = self.next_review_id
        self.next_review_id += 1
        review.created_at = _now()
        review.updated_at = _now()
        self.reviews[review.id] = review


class FakeFavoritesRepository:
    def __init__(self) -> None:
        self.product_ids = {1, 2}
        self.favorites: dict[int, Favorite] = {}
        self.next_favorite_id = 1

    async def product_exists(self, product_id: int) -> bool:
        return product_id in self.product_ids

    async def get_for_user_product(self, *, user_id: int, product_id: int) -> Favorite | None:
        return next(
            (
                favorite
                for favorite in self.favorites.values()
                if favorite.user_id == user_id and favorite.product_id == product_id
            ),
            None,
        )

    async def list_for_user(self, *, user_id: int) -> list[Favorite]:
        return [favorite for favorite in self.favorites.values() if favorite.user_id == user_id]

    async def delete_for_user_product(self, *, user_id: int, product_id: int) -> bool:
        favorite = await self.get_for_user_product(user_id=user_id, product_id=product_id)
        if favorite is None:
            return False
        self.favorites.pop(favorite.id)
        return True

    def add(self, favorite: Favorite) -> None:
        favorite.id = self.next_favorite_id
        self.next_favorite_id += 1
        favorite.created_at = _now()
        self.favorites[favorite.id] = favorite


@pytest.mark.asyncio
async def test_create_review_after_purchase() -> None:
    service, repository, session = _reviews_service()
    repository.purchase_order_ids[(1, 1)] = 10

    review = await service.create_product_review(
        user_id=1,
        product_id=1,
        payload=ReviewCreate(rating=5, text="Great hoodie"),
    )

    assert review.user_id == 1
    assert review.product_id == 1
    assert review.order_id == 10
    assert review.rating == 5
    assert session.committed is True


@pytest.mark.asyncio
async def test_reject_review_without_purchase() -> None:
    service, repository, session = _reviews_service()
    repository.purchase_order_ids = {}

    with pytest.raises(AppError, match="Product purchase required for review"):
        await service.create_product_review(
            user_id=1,
            product_id=1,
            payload=ReviewCreate(rating=5, text="Great hoodie"),
        )

    assert repository.reviews == {}
    assert session.committed is False


@pytest.mark.asyncio
async def test_reject_duplicate_review_for_same_product_user() -> None:
    service, repository, _ = _reviews_service()
    repository.purchase_order_ids[(1, 1)] = 10
    await service.create_product_review(
        user_id=1,
        product_id=1,
        payload=ReviewCreate(rating=5, text="Great hoodie"),
    )

    with pytest.raises(AppError, match="Product already reviewed"):
        await service.create_product_review(
            user_id=1,
            product_id=1,
            payload=ReviewCreate(rating=4, text="Still good"),
        )

    assert len(repository.reviews) == 1


@pytest.mark.asyncio
async def test_new_review_has_pending_status() -> None:
    service, repository, _ = _reviews_service()
    repository.purchase_order_ids[(1, 1)] = 10

    review = await service.create_product_review(
        user_id=1,
        product_id=1,
        payload=ReviewCreate(rating=5, text="Great hoodie"),
    )

    assert review.status == ReviewStatus.PENDING


@pytest.mark.asyncio
async def test_public_product_reviews_show_only_approved_reviews() -> None:
    service, repository, _ = _reviews_service()
    repository.reviews[1] = _review(1, status=ReviewStatus.APPROVED)
    repository.reviews[2] = _review(2, status=ReviewStatus.PENDING)
    repository.reviews[3] = _review(3, status=ReviewStatus.REJECTED)

    reviews = await service.list_approved_product_reviews(1)

    assert [review.id for review in reviews.items] == [1]


@pytest.mark.asyncio
async def test_seller_admin_can_approve_review() -> None:
    service, repository, _ = _reviews_service()
    repository.reviews[1] = _review(1, status=ReviewStatus.PENDING)

    review = await service.moderate_review(
        review_id=1,
        moderator_id=2,
        payload=ReviewModerationUpdate(status=ReviewStatus.APPROVED),
    )

    assert review.status == ReviewStatus.APPROVED
    assert review.moderated_by_id == 2
    assert review.moderated_at is not None


@pytest.mark.asyncio
async def test_seller_admin_can_reject_review() -> None:
    service, repository, _ = _reviews_service()
    repository.reviews[1] = _review(1, status=ReviewStatus.PENDING)

    review = await service.moderate_review(
        review_id=1,
        moderator_id=2,
        payload=ReviewModerationUpdate(status=ReviewStatus.REJECTED),
    )

    assert review.status == ReviewStatus.REJECTED
    assert review.moderated_by_id == 2


@pytest.mark.asyncio
async def test_review_moderation_records_audit_log() -> None:
    audit_service = FakeAuditService()
    service, repository, _ = _reviews_service(audit_service=audit_service)
    repository.reviews[1] = _review(1, status=ReviewStatus.PENDING)

    await service.moderate_review(
        review_id=1,
        moderator_id=2,
        payload=ReviewModerationUpdate(status=ReviewStatus.APPROVED),
    )

    assert audit_service.logs[0]["actor_user_id"] == 2
    assert audit_service.logs[0]["action"] == "review.approved"
    assert audit_service.logs[0]["entity_type"] == "review"
    assert audit_service.logs[0]["entity_id"] == 1


@pytest.mark.asyncio
async def test_seller_admin_can_list_and_get_reviews_by_status() -> None:
    service, repository, _ = _reviews_service()
    repository.reviews[1] = _review(1, status=ReviewStatus.PENDING)
    repository.reviews[2] = _review(2, status=ReviewStatus.APPROVED)

    reviews = await service.list_reviews(ReviewStatus.PENDING)
    review = await service.get_review(1)

    assert [item.id for item in reviews.items] == [1]
    assert review.id == 1


@pytest.mark.asyncio
async def test_dedicated_review_approve_and_reject_actions() -> None:
    service, repository, _ = _reviews_service()
    repository.reviews[1] = _review(1, status=ReviewStatus.PENDING)
    repository.reviews[2] = _review(2, status=ReviewStatus.PENDING)

    approved = await service.approve_review(review_id=1, moderator_id=2)
    rejected = await service.reject_review(review_id=2, moderator_id=2)

    assert approved.status == ReviewStatus.APPROVED
    assert rejected.status == ReviewStatus.REJECTED


def test_normal_user_cannot_moderate_reviews() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.USER)
    try:
        with TestClient(app) as client:
            response = client.patch(
                "/api/v1/reviews/1/status",
                json={"status": "APPROVED"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_normal_user_cannot_list_reviews_for_moderation() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.USER)
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/reviews/admin")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_user_can_list_own_reviews() -> None:
    service, repository, _ = _reviews_service()
    repository.reviews[1] = _review(1, user_id=1)
    repository.reviews[2] = _review(2, user_id=2)

    reviews = await service.list_current_user_reviews(1)

    assert [review.user_id for review in reviews.items] == [1]


@pytest.mark.asyncio
async def test_add_favorite() -> None:
    service, repository, session = _favorites_service()

    favorite = await service.add_favorite(1, FavoriteCreate(product_id=1))

    assert favorite.user_id == 1
    assert favorite.product_id == 1
    assert len(repository.favorites) == 1
    assert session.committed is True


@pytest.mark.asyncio
async def test_create_review_tracks_review_created_event() -> None:
    tracker = FakeAnalyticsTracker()
    service, repository, _ = _reviews_service(analytics_tracker=tracker)
    repository.purchase_order_ids[(1, 1)] = 10

    review = await service.create_product_review(
        user_id=1,
        product_id=1,
        payload=ReviewCreate(rating=5, text="Great hoodie"),
    )

    assert tracker.events == [
        (
            "review.created",
            {
                "user_id": 1,
                "product_id": 1,
                "order_id": 10,
                "metadata": {"review_id": review.id, "rating": 5},
            },
        )
    ]


@pytest.mark.asyncio
async def test_add_same_favorite_twice_does_not_duplicate() -> None:
    service, repository, _ = _favorites_service()

    first = await service.add_favorite(1, FavoriteCreate(product_id=1))
    second = await service.add_favorite(1, FavoriteCreate(product_id=1))

    assert first.id == second.id
    assert len(repository.favorites) == 1


@pytest.mark.asyncio
async def test_remove_favorite() -> None:
    service, repository, _ = _favorites_service()
    await service.add_favorite(1, FavoriteCreate(product_id=1))

    await service.remove_favorite(user_id=1, product_id=1)

    assert repository.favorites == {}


@pytest.mark.asyncio
async def test_list_current_users_favorites() -> None:
    service, repository, _ = _favorites_service()
    repository.add(Favorite(user_id=1, product_id=1))
    repository.add(Favorite(user_id=2, product_id=2))

    favorites = await service.list_current_user_favorites(1)

    assert [favorite.user_id for favorite in favorites.items] == [1]
    assert [favorite.product_id for favorite in favorites.items] == [1]


@pytest.mark.asyncio
async def test_user_cannot_access_another_users_favorites() -> None:
    service, repository, _ = _favorites_service()
    repository.add(Favorite(user_id=2, product_id=1))

    favorites = await service.list_current_user_favorites(1)
    await service.remove_favorite(user_id=1, product_id=1)

    assert favorites.items == []
    assert len(repository.favorites) == 1


def test_reviews_require_authentication_where_required() -> None:
    with TestClient(create_app()) as client:
        create_response = client.post(
            "/api/v1/products/1/reviews",
            json={"rating": 5, "text": "Great hoodie"},
        )
        own_response = client.get("/api/v1/reviews/me")
        moderate_response = client.patch(
            "/api/v1/reviews/1/status",
            json={"status": "APPROVED"},
        )

    assert create_response.status_code == 401
    assert own_response.status_code == 401
    assert moderate_response.status_code == 401


def test_favorites_require_authentication() -> None:
    with TestClient(create_app()) as client:
        list_response = client.get("/api/v1/favorites")
        add_response = client.post("/api/v1/favorites", json={"product_id": 1})
        remove_response = client.delete("/api/v1/favorites/1")

    assert list_response.status_code == 401
    assert add_response.status_code == 401
    assert remove_response.status_code == 401


def test_public_product_reviews_allow_anonymous_access() -> None:
    app = create_app()

    class FakeReviewsService:
        async def list_approved_product_reviews(self, product_id: int) -> dict[str, list]:
            assert product_id == 1
            return {"items": []}

    app.dependency_overrides[get_reviews_service] = lambda: FakeReviewsService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/products/1/reviews")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_favorite_routes_scope_to_current_user() -> None:
    app = create_app()

    class FakeFavoritesService:
        async def list_current_user_favorites(self, user_id: int) -> dict[str, list]:
            assert user_id == 1
            return {"items": []}

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.USER)
    app.dependency_overrides[get_favorites_service] = lambda: FakeFavoritesService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/favorites")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"


def _reviews_service(
    *,
    analytics_tracker: FakeAnalyticsTracker | None = None,
    audit_service: FakeAuditService | None = None,
) -> tuple[ReviewsService, FakeReviewsRepository, DummySession]:
    session = DummySession()
    service = ReviewsService(
        session,
        analytics_tracker=analytics_tracker,
        audit_service=audit_service,
    )
    repository = FakeReviewsRepository()
    service.repository = repository
    return service, repository, session


def _favorites_service() -> tuple[FavoritesService, FakeFavoritesRepository, DummySession]:
    session = DummySession()
    service = FavoritesService(session)
    repository = FakeFavoritesRepository()
    service.repository = repository
    return service, repository, session


def _review(
    review_id: int,
    *,
    user_id: int = 1,
    product_id: int = 1,
    status: ReviewStatus = ReviewStatus.PENDING,
) -> Review:
    return Review(
        id=review_id,
        user_id=user_id,
        product_id=product_id,
        order_id=10,
        rating=5,
        text="Great hoodie",
        status=status,
        moderated_at=None,
        moderated_by_id=None,
        created_at=_now(),
        updated_at=_now(),
    )


def _user(role: UserRole) -> User:
    return User(
        id=1,
        telegram_id=42,
        username="buyer",
        first_name="Ada",
        last_name=None,
        phone=None,
        role=role,
        is_active=True,
        created_at=_now(),
        updated_at=_now(),
    )


def _now() -> datetime:
    return datetime(2026, 5, 27, tzinfo=UTC)
