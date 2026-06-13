from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.common.deps import get_current_user
from app.db.models import Order, OrderStatus, User, UserRole
from app.main import create_app
from app.modules.users.router import get_users_service
from app.modules.users.schemas import PersonalDataRead, PersonalDataUpdate
from app.modules.users.service import UsersService


class DummySession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeUsersService:
    def get_personal_data(self, user: User) -> PersonalDataRead:
        return PersonalDataRead.model_validate(user)

    async def update_personal_data(
        self,
        user: User,
        payload: PersonalDataUpdate,
    ) -> PersonalDataRead:
        for field, value in payload.model_dump().items():
            setattr(user, field, value)
        return PersonalDataRead.model_validate(user)


def test_current_user_can_get_empty_personal_data() -> None:
    app = create_app()
    user = _user()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_users_service] = FakeUsersService
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/users/me/personal-data")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "recipient_name": None,
        "contact_phone": None,
        "city": None,
        "height_cm": None,
        "weight_kg": None,
        "telegram_username": None,
        "persistent_comment": None,
    }


def test_current_user_can_update_personal_data_without_changing_another_user() -> None:
    app = create_app()
    current_user = _user(user_id=1)
    other_user = _user(user_id=2)
    other_user.recipient_name = "Other customer"
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_users_service] = FakeUsersService
    payload = {
        "recipient_name": "  Ada Lovelace  ",
        "contact_phone": "  +1 (555) 010-0200  ",
        "city": "  Moscow  ",
        "height_cm": 168,
        "weight_kg": 62.5,
        "telegram_username": "  @Ada_Lovelace  ",
        "persistent_comment": "  Call before delivery  ",
    }
    try:
        with TestClient(app) as client:
            response = client.put("/api/v1/users/me/personal-data", json=payload)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "recipient_name": "Ada Lovelace",
        "contact_phone": "+1 (555) 010-0200",
        "city": "Moscow",
        "height_cm": 168,
        "weight_kg": 62.5,
        "telegram_username": "ada_lovelace",
        "persistent_comment": "Call before delivery",
    }
    assert current_user.recipient_name == "Ada Lovelace"
    assert other_user.recipient_name == "Other customer"


def test_personal_data_endpoint_requires_authentication() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/users/me/personal-data")

    assert response.status_code == 401


def test_personal_data_does_not_expose_user_id_route() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _user()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/users/2/personal-data")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"height_cm": 0},
        {"weight_kg": -1},
        {"contact_phone": "phone only"},
        {"telegram_username": "bad tag!"},
        {"persistent_comment": "x" * 501},
    ],
)
def test_personal_data_validation_rejects_invalid_values(payload: dict[str, object]) -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _user()
    app.dependency_overrides[get_users_service] = FakeUsersService
    try:
        with TestClient(app) as client:
            response = client.put("/api/v1/users/me/personal-data", json=payload)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["detail"]


@pytest.mark.asyncio
async def test_profile_update_does_not_change_existing_order_snapshot() -> None:
    session = DummySession()
    user = _user()
    order = Order(
        id=1,
        order_number="ORD-00000001",
        user_id=user.id,
        status=OrderStatus.NEW,
        subtotal_amount=Decimal("100.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("100.00"),
        contact_name="Original recipient",
        contact_phone="+10000000000",
        delivery_address="Original city",
        delivery_comment="Original comment",
    )

    await UsersService(session).update_personal_data(
        user,
        PersonalDataUpdate(
            recipient_name="New recipient",
            contact_phone="+20000000000",
            city="New city",
            persistent_comment="New comment",
        ),
    )

    assert session.committed is True
    assert session.rolled_back is False
    assert order.contact_name == "Original recipient"
    assert order.contact_phone == "+10000000000"
    assert order.delivery_address == "Original city"
    assert order.delivery_comment == "Original comment"


def _user(*, user_id: int = 1) -> User:
    now = datetime(2026, 6, 13, tzinfo=UTC)
    return User(
        id=user_id,
        telegram_id=40 + user_id,
        username="buyer",
        first_name="Ada",
        last_name=None,
        phone=None,
        role=UserRole.USER,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
