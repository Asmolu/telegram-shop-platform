from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.common.deps import get_current_user, get_optional_current_user
from app.common.pagination import PageMeta
from app.core.errors import AppError
from app.db.models import User, UserBlock, UserRole
from app.main import create_app
from app.modules.orders.schemas import OrderCheckoutCreate
from app.modules.orders.service import OrdersService
from app.modules.products.router import get_products_service
from app.modules.products.schemas import ProductCardList
from app.modules.returns.schemas import ReturnRequestCreate, ReturnRequestItemCreate
from app.modules.returns.service import ReturnsService
from app.modules.reviews.schemas import ReviewCreate
from app.modules.reviews.service import ReviewsService
from app.modules.users.schemas import UserBlockCreate
from app.modules.users.service import BLOCKED_USER_MESSAGE, UsersService

NOW = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)


class DummySession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.flushed = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def flush(self) -> None:
        self.flushed = True


class FakeAuditService:
    def __init__(self) -> None:
        self.logs: list[dict[str, object]] = []

    async def record_action(self, **payload: object) -> None:
        self.logs.append(payload)

    def snapshot(self, instance: object, fields: tuple[str, ...]) -> dict[str, object]:
        return {field: getattr(instance, field) for field in fields}


class FakeUsersRepository:
    def __init__(self) -> None:
        self.users: dict[int, User] = {}
        self.blocks: dict[int, UserBlock] = {}
        self.next_block_id = 1

    async def get_by_id(self, user_id: int) -> User | None:
        return self.users.get(user_id)

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        return next(
            (user for user in self.users.values() if user.telegram_id == telegram_id),
            None,
        )

    async def get_by_telegram_username(self, telegram_username: str) -> User | None:
        normalized = telegram_username.lower()
        return next(
            (
                user
                for user in self.users.values()
                if (user.username or "").lower() == normalized
                or (user.telegram_username or "").lower() == normalized
            ),
            None,
        )

    async def list_active_blocks(self) -> list[UserBlock]:
        return [
            block
            for block in sorted(self.blocks.values(), key=lambda item: item.id, reverse=True)
            if block.unblocked_at is None
        ]

    async def get_block_by_id(self, block_id: int) -> UserBlock | None:
        return self.blocks.get(block_id)

    async def find_active_block(
        self,
        *,
        user_id: int | None = None,
        telegram_id: int | None = None,
        telegram_username: str | None = None,
    ) -> UserBlock | None:
        for block in self.blocks.values():
            if block.unblocked_at is not None:
                continue
            if user_id is not None and block.user_id == user_id:
                return block
            if telegram_id is not None and block.telegram_id == telegram_id:
                return block
            if telegram_username is not None and block.telegram_username == telegram_username:
                return block
        return None

    async def find_active_block_for_user(self, user: User) -> UserBlock | None:
        usernames = {
            value.lower()
            for value in (user.username, user.telegram_username)
            if value
        }
        for block in self.blocks.values():
            if block.unblocked_at is not None:
                continue
            if block.user_id == user.id or block.telegram_id == user.telegram_id:
                return block
            if block.telegram_username in usernames:
                return block
        return None

    async def list_matching_pending_username_blocks(self, usernames: set[str]) -> list[UserBlock]:
        return [
            block
            for block in self.blocks.values()
            if block.unblocked_at is None
            and block.telegram_username in usernames
            and (block.user_id is None or block.telegram_id is None)
        ]

    def add_block(self, user_block: UserBlock) -> None:
        user_block.id = self.next_block_id
        self.next_block_id += 1
        user_block.blocked_at = NOW
        if user_block.user_id is not None:
            user_block.user = self.users.get(user_block.user_id)
        if user_block.blocked_by_user_id is not None:
            user_block.blocked_by = self.users.get(user_block.blocked_by_user_id)
        self.blocks[user_block.id] = user_block


class FakeUserBlocksService:
    def __init__(self, *, blocked_user_ids: set[int]) -> None:
        self.blocked_user_ids = blocked_user_ids

    async def assert_user_not_blocked(self, user_id: int) -> None:
        if user_id in self.blocked_user_ids:
            raise AppError(BLOCKED_USER_MESSAGE, 403)


@pytest.mark.asyncio
async def test_block_by_telegram_id_prevents_checkout() -> None:
    service = OrdersService(
        DummySession(),
        users_service=FakeUserBlocksService(blocked_user_ids={1}),
    )

    with pytest.raises(AppError, match=BLOCKED_USER_MESSAGE):
        await service.checkout_current_user_cart(
            user_id=1,
            payload=OrderCheckoutCreate(
                contact_name="Ada",
                contact_phone="+79999999999",
                delivery_method="CDEK",
                delivery_address="Main street",
            ),
        )


@pytest.mark.asyncio
async def test_block_by_username_prevents_checkout_after_user_matched() -> None:
    service, repository, _session, _audit = _users_service()
    repository.users[1] = _user(user_id=1, telegram_id=1001, username="StyleXas")
    repository.users[10] = _user(user_id=10, telegram_id=1010, role=UserRole.SELLER)

    block = await service.create_block(
        UserBlockCreate(telegram_username="@stylexas", reason="Risk"),
        actor_user_id=10,
    )

    assert block.user_id == 1
    assert block.telegram_id == 1001
    assert block.telegram_username == "stylexas"
    with pytest.raises(AppError, match=BLOCKED_USER_MESSAGE):
        await service.assert_user_not_blocked(1)


@pytest.mark.asyncio
async def test_blocked_user_cannot_create_return() -> None:
    service = ReturnsService(
        DummySession(),
        users_service=FakeUserBlocksService(blocked_user_ids={1}),
    )

    with pytest.raises(AppError, match=BLOCKED_USER_MESSAGE):
        await service.create_return_request(
            order_id=1,
            user_id=1,
            payload=ReturnRequestCreate(
                reason="Size",
                items=[ReturnRequestItemCreate(order_item_id=1, quantity=1)],
            ),
        )


@pytest.mark.asyncio
async def test_blocked_user_cannot_create_review() -> None:
    service = ReviewsService(
        DummySession(),
        users_service=FakeUserBlocksService(blocked_user_ids={1}),
    )

    with pytest.raises(AppError, match=BLOCKED_USER_MESSAGE):
        await service.create_product_review(
            user_id=1,
            product_id=1,
            payload=ReviewCreate(rating=5, text="Great"),
        )


def test_blocked_user_can_still_read_catalog() -> None:
    app = create_app()

    class FakeProductsService:
        async def list_public_products(self, **_: object) -> ProductCardList:
            return ProductCardList(items=[], meta=PageMeta(limit=20, offset=0, total=0))

        async def track_public_product_list_search(self, **_: object) -> None:
            return None

    async def current_user() -> User:
        return _user(user_id=1, telegram_id=1001)

    app.dependency_overrides[get_optional_current_user] = current_user
    app.dependency_overrides[get_products_service] = lambda: FakeProductsService()
    try:
        response = TestClient(app).get("/api/v1/products")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"] == []


@pytest.mark.asyncio
async def test_unblock_restores_permissions() -> None:
    service, repository, _session, _audit = _users_service()
    repository.users[1] = _user(user_id=1, telegram_id=1001)
    repository.blocks[1] = UserBlock(
        id=1,
        user_id=1,
        telegram_id=1001,
        telegram_username="buyer",
        reason="Risk",
        blocked_at=NOW,
        blocked_by_user_id=10,
        unblocked_at=None,
        unblocked_by_user_id=None,
    )

    unblocked = await service.unblock(1, actor_user_id=10)
    await service.assert_user_not_blocked(1)

    assert unblocked.unblocked_at is not None
    assert unblocked.unblocked_by_user_id == 10


@pytest.mark.asyncio
async def test_duplicate_active_block_reuses_existing() -> None:
    service, repository, _session, _audit = _users_service()
    repository.users[10] = _user(user_id=10, telegram_id=1010, role=UserRole.SELLER)

    first = await service.create_block(
        UserBlockCreate(telegram_id=1001, reason="First"),
        actor_user_id=10,
    )
    second = await service.create_block(
        UserBlockCreate(telegram_id=1001, reason="Second"),
        actor_user_id=10,
    )

    assert first.id == second.id
    assert len(repository.blocks) == 1
    assert second.reason == "First"


@pytest.mark.asyncio
async def test_list_returns_active_blocks_only() -> None:
    service, repository, _session, _audit = _users_service()
    repository.blocks[1] = UserBlock(
        id=1,
        telegram_id=1001,
        telegram_username="active",
        reason=None,
        blocked_at=NOW,
        blocked_by_user_id=10,
        unblocked_at=None,
    )
    repository.blocks[2] = UserBlock(
        id=2,
        telegram_id=1002,
        telegram_username="inactive",
        reason=None,
        blocked_at=NOW,
        blocked_by_user_id=10,
        unblocked_at=NOW,
    )

    result = await service.list_active_blocks()

    assert [item.id for item in result.items] == [1]


def test_regular_user_cannot_manage_blocks() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _user(
        user_id=1,
        telegram_id=1001,
        role=UserRole.USER,
    )
    try:
        with TestClient(app) as client:
            list_response = client.get("/api/v1/users/admin/blocks")
            create_response = client.post(
                "/api/v1/users/admin/blocks",
                json={"telegram_id": 1001},
            )
            unblock_response = client.post("/api/v1/users/admin/blocks/1/unblock")
    finally:
        app.dependency_overrides.clear()

    assert list_response.status_code == 403
    assert create_response.status_code == 403
    assert unblock_response.status_code == 403


def _users_service() -> tuple[UsersService, FakeUsersRepository, DummySession, FakeAuditService]:
    session = DummySession()
    audit = FakeAuditService()
    service = UsersService(session, audit_service=audit)
    repository = FakeUsersRepository()
    service.repository = repository
    return service, repository, session, audit


def _user(
    *,
    user_id: int,
    telegram_id: int,
    username: str = "buyer",
    role: UserRole = UserRole.USER,
) -> User:
    return User(
        id=user_id,
        telegram_id=telegram_id,
        username=username,
        telegram_username=username,
        first_name="Ada",
        last_name=None,
        phone=None,
        role=role,
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
    )
