from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.common.deps import get_current_user
from app.db.models import User, UserRole
from app.main import create_app
from app.modules.users.router import get_users_service


def test_users_me_requires_authentication() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/users/me")

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


def test_users_me_returns_current_user() -> None:
    app = create_app()

    async def fake_current_user() -> User:
        return User(
            id=1,
            telegram_id=42,
            username="buyer",
            first_name="Ada",
            last_name=None,
            phone=None,
            role=UserRole.USER,
            is_active=True,
            created_at=datetime(2026, 5, 27, tzinfo=UTC),
            updated_at=datetime(2026, 5, 27, tzinfo=UTC),
        )

    app.dependency_overrides[get_current_user] = fake_current_user
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/users/me")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["telegram_id"] == 42
    assert response.json()["role"] == "USER"


def test_user_admin_list_requires_authentication() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/users/admin")

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


def test_user_admin_list_rejects_regular_user() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.USER)
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/users/admin")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}


def test_user_admin_detail_allows_seller() -> None:
    app = create_app()

    class FakeUsersService:
        async def get_user_detail(self, _: int) -> dict[str, object]:
            return _user_response(UserRole.USER)

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_users_service] = lambda: FakeUsersService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/users/admin/2")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["role"] == "USER"


def _user(role: UserRole) -> User:
    return User(
        id=1,
        telegram_id=42,
        username="seller",
        first_name="Ada",
        last_name=None,
        phone=None,
        role=role,
        is_active=True,
        created_at=datetime(2026, 5, 27, tzinfo=UTC),
        updated_at=datetime(2026, 5, 27, tzinfo=UTC),
    )


def _user_response(role: UserRole) -> dict[str, object]:
    now = datetime(2026, 5, 27, tzinfo=UTC).isoformat()
    return {
        "id": 2,
        "telegram_id": 43,
        "username": "buyer",
        "first_name": "Grace",
        "last_name": None,
        "phone": None,
        "role": role.value,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
