from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.common.deps import get_current_user
from app.core.errors import AppError
from app.core.security import verify_access_token
from app.db.models import (
    PendingSellerRegistration,
    SellerCredential,
    SellerRegistrationStatus,
    User,
    UserRole,
)
from app.main import create_app
from app.modules.seller_auth.router import get_seller_auth_service
from app.modules.seller_auth.schemas import (
    SellerLoginRequest,
    SellerRegistrationConfirmRequest,
    SellerRegistrationStartRequest,
    SellerTelegramStartRequest,
)
from app.modules.seller_auth.service import SellerAuthService, hash_password, verify_password


class DummySession:
    def __init__(self) -> None:
        self.commits = 0
        self.rolled_back = False

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rolled_back = True

    async def refresh(self, _: object) -> None:
        return None

    async def flush(self) -> None:
        return None


class FakeTelegramService:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    async def send_message(self, chat_id: str, message: str) -> None:
        self.messages.append((chat_id, message))


class FakeSellerAuthRepository:
    def __init__(self) -> None:
        self.next_registration_id = 1
        self.next_user_id = 1
        self.next_credential_id = 1
        self.registrations: dict[int, PendingSellerRegistration] = {}
        self.credentials_by_email: dict[str, SellerCredential] = {}
        self.users_by_telegram_id: dict[int, User] = {}

    def add_pending_registration(self, registration: PendingSellerRegistration) -> None:
        registration.id = self.next_registration_id
        self.next_registration_id += 1
        registration.created_at = _now()
        registration.updated_at = _now()
        self.registrations[registration.id] = registration

    def add_seller_credential(self, credential: SellerCredential) -> None:
        credential.id = self.next_credential_id
        self.next_credential_id += 1
        credential.user_id = credential.user.id
        credential.created_at = _now()
        credential.updated_at = _now()
        self.credentials_by_email[credential.email] = credential

    def add_user(self, user: User) -> None:
        user.id = self.next_user_id
        self.next_user_id += 1
        user.created_at = _now()
        user.updated_at = _now()
        self.users_by_telegram_id[user.telegram_id] = user

    async def get_credential_by_email(self, email: str) -> SellerCredential | None:
        return self.credentials_by_email.get(email)

    async def get_active_pending_by_email(
        self,
        *,
        email: str,
        now: datetime,
    ) -> PendingSellerRegistration | None:
        for registration in self.registrations.values():
            if (
                registration.email == email
                and registration.status == SellerRegistrationStatus.PENDING
                and registration.expires_at > now
            ):
                return registration
        return None

    async def get_pending_by_id(
        self,
        registration_id: int,
    ) -> PendingSellerRegistration | None:
        return self.registrations.get(registration_id)

    async def get_pending_by_start_token_hash(
        self,
        token_hash: str,
    ) -> PendingSellerRegistration | None:
        for registration in self.registrations.values():
            if registration.bot_start_token_hash == token_hash:
                return registration
        return None

    async def get_user_by_telegram_id(self, telegram_id: int) -> User | None:
        return self.users_by_telegram_id.get(telegram_id)


@pytest.mark.asyncio
async def test_start_seller_registration_hashes_password_and_returns_start_command() -> None:
    service, repository, _, _ = _seller_auth_service()

    response = await service.start_registration(_start_payload())

    registration = repository.registrations[response.registration_id]
    assert response.start_command == "/start seller_start-token"
    assert response.bot_start_link is None
    assert registration.email == "seller@example.com"
    assert registration.password_hash != "Password1"
    assert verify_password("Password1", registration.password_hash)


@pytest.mark.asyncio
async def test_start_seller_registration_rejects_duplicate_email() -> None:
    service, repository, _, _ = _seller_auth_service()
    repository.credentials_by_email["seller@example.com"] = _credential(verified=True)

    with pytest.raises(AppError, match="already registered"):
        await service.start_registration(_start_payload())


@pytest.mark.asyncio
async def test_telegram_start_links_identity_and_sends_code() -> None:
    service, repository, _, telegram = _seller_auth_service()
    started = await service.start_registration(_start_payload())

    response = await service.handle_telegram_start(
        SellerTelegramStartRequest(
            start_payload="seller_start-token",
            telegram_user_id=99,
            telegram_chat_id=100,
            telegram_username="@sellername",
        )
    )

    registration = repository.registrations[started.registration_id]
    assert response.registration_id == started.registration_id
    assert registration.telegram_user_id == 99
    assert registration.telegram_chat_id == 100
    assert registration.verification_code_hash != "123456"
    assert telegram.messages == [
        (
            "100",
            "Seller Portal verification code\n\n"
            "Code: 123456\n"
            "Enter this code in the Seller Portal to finish registration.",
        )
    ]


@pytest.mark.asyncio
async def test_telegram_start_rejects_username_mismatch() -> None:
    service, _, _, _ = _seller_auth_service()
    await service.start_registration(_start_payload())

    with pytest.raises(AppError, match="username does not match"):
        await service.handle_telegram_start(
            SellerTelegramStartRequest(
                start_payload="seller_start-token",
                telegram_user_id=99,
                telegram_chat_id=100,
                telegram_username="@othername",
            )
        )


@pytest.mark.asyncio
async def test_confirm_registration_creates_verified_seller_and_token() -> None:
    service, repository, _, _ = _seller_auth_service()
    started = await service.start_registration(_start_payload())
    await service.handle_telegram_start(
        SellerTelegramStartRequest(
            start_payload="seller_start-token",
            telegram_user_id=99,
            telegram_chat_id=100,
            telegram_username="@sellername",
        )
    )

    response = await service.confirm_registration(
        SellerRegistrationConfirmRequest(registration_id=started.registration_id, code="123456")
    )

    credential = repository.credentials_by_email["seller@example.com"]
    registration = repository.registrations[started.registration_id]
    claims = verify_access_token(response.access_token)
    assert response.user.role == UserRole.SELLER
    assert credential.password_hash == registration.password_hash
    assert credential.verified_at is not None
    assert claims["role"] == "SELLER"


@pytest.mark.asyncio
async def test_confirm_registration_rejects_expired_code() -> None:
    service, repository, _, _ = _seller_auth_service()
    started = await service.start_registration(_start_payload())
    await service.handle_telegram_start(
        SellerTelegramStartRequest(
            start_payload="seller_start-token",
            telegram_user_id=99,
            telegram_chat_id=100,
            telegram_username="@sellername",
        )
    )
    repository.registrations[started.registration_id].verification_expires_at = _now() - timedelta(
        seconds=1
    )

    with pytest.raises(AppError, match="Verification code expired"):
        await service.confirm_registration(
            SellerRegistrationConfirmRequest(
                registration_id=started.registration_id,
                code="123456",
            )
        )


@pytest.mark.asyncio
async def test_seller_login_accepts_verified_seller() -> None:
    service, repository, _, _ = _seller_auth_service()
    credential = _credential(verified=True)
    repository.credentials_by_email[credential.email] = credential

    response = await service.login(
        SellerLoginRequest(email="seller@example.com", password="Password1")
    )

    claims = verify_access_token(response.access_token)
    assert response.user.role == UserRole.SELLER
    assert claims["role"] == "SELLER"


@pytest.mark.asyncio
async def test_seller_login_rejects_unverified_seller() -> None:
    service, repository, _, _ = _seller_auth_service()
    credential = _credential(verified=False)
    repository.credentials_by_email[credential.email] = credential

    with pytest.raises(AppError, match="not verified"):
        await service.login(SellerLoginRequest(email="seller@example.com", password="Password1"))


@pytest.mark.asyncio
async def test_seller_login_rejects_wrong_password() -> None:
    service, repository, _, _ = _seller_auth_service()
    credential = _credential(verified=True)
    repository.credentials_by_email[credential.email] = credential

    with pytest.raises(AppError, match="Invalid email or password"):
        await service.login(SellerLoginRequest(email="seller@example.com", password="Wrong123"))


def test_seller_auth_register_start_rejects_weak_payload() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/seller-auth/register/start",
            json={
                "email": "seller@example.com",
                "password": "password",
                "telegram_username": "@sellername",
            },
        )

    assert response.status_code == 422


def test_seller_auth_me_rejects_normal_user() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.USER)
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/seller-auth/me")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}


def test_seller_auth_login_route_returns_token() -> None:
    app = create_app()

    class FakeSellerAuthService:
        async def login(self, _: SellerLoginRequest):
            return {
                "access_token": "token",
                "token_type": "bearer",
                "user": _user_response(UserRole.SELLER),
            }

    app.dependency_overrides[get_seller_auth_service] = lambda: FakeSellerAuthService()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/seller-auth/login",
                json={"email": "seller@example.com", "password": "Password1"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["user"]["role"] == "SELLER"


def _seller_auth_service() -> tuple[
    SellerAuthService,
    FakeSellerAuthRepository,
    DummySession,
    FakeTelegramService,
]:
    session = DummySession()
    telegram = FakeTelegramService()
    service = SellerAuthService(
        session,
        telegram_service=telegram,
        token_factory=lambda: "start-token",
        code_factory=lambda: "123456",
        now_factory=_now,
    )
    repository = FakeSellerAuthRepository()
    service.repository = repository
    return service, repository, session, telegram


def _start_payload() -> SellerRegistrationStartRequest:
    return SellerRegistrationStartRequest(
        email="seller@example.com",
        password="Password1",
        telegram_username="@sellername",
    )


def _credential(*, verified: bool) -> SellerCredential:
    user = _user(UserRole.SELLER)
    return SellerCredential(
        id=1,
        user_id=user.id,
        user=user,
        email="seller@example.com",
        password_hash=hash_password("Password1", salt="test-salt"),
        telegram_username="sellername",
        telegram_user_id=user.telegram_id,
        telegram_chat_id=user.telegram_id,
        verified_at=_now() if verified else None,
        created_at=_now(),
        updated_at=_now(),
    )


def _user(role: UserRole) -> User:
    return User(
        id=1,
        telegram_id=42,
        username="sellername",
        first_name="Ada",
        last_name=None,
        phone=None,
        role=role,
        is_active=True,
        created_at=_now(),
        updated_at=_now(),
    )


def _user_response(role: UserRole) -> dict[str, object]:
    return {
        "id": 1,
        "telegram_id": 42,
        "username": "sellername",
        "first_name": "Ada",
        "last_name": None,
        "phone": None,
        "role": role.value,
        "is_active": True,
        "created_at": _now().isoformat(),
        "updated_at": _now().isoformat(),
    }


def _now() -> datetime:
    return datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
