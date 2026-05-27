from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.common.deps import get_current_user
from app.db.models import User, UserRole
from app.main import create_app


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
