from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.core.security import create_access_token
from app.db.models import (
    PendingSellerRegistration,
    SellerCredential,
    SellerRegistrationStatus,
    User,
    UserRole,
)
from app.modules.auth.schemas import TokenResponse
from app.modules.seller_auth.repository import SellerAuthRepository
from app.modules.seller_auth.schemas import (
    SellerLoginRequest,
    SellerRegistrationConfirmRequest,
    SellerRegistrationResendCodeRequest,
    SellerRegistrationResendCodeResponse,
    SellerRegistrationStartRequest,
    SellerRegistrationStartResponse,
    SellerTelegramStartRequest,
    SellerTelegramStartResponse,
)
from app.modules.telegram.service import TelegramDeliveryError, TelegramService

PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 310_000
SELLER_START_PREFIX = "seller_"


class SellerAuthService:
    """Seller Portal email/password auth and Telegram bot verification flow."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        telegram_service: TelegramService | None = None,
        token_factory: Callable[[], str] | None = None,
        code_factory: Callable[[], str] | None = None,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self.session = session
        self.repository = SellerAuthRepository(session)
        self.telegram_service = telegram_service or TelegramService()
        self.token_factory = token_factory or (lambda: secrets.token_urlsafe(32))
        self.code_factory = code_factory or _generate_verification_code
        self.now_factory = now_factory or (lambda: datetime.now(UTC))

    async def start_registration(
        self,
        payload: SellerRegistrationStartRequest,
    ) -> SellerRegistrationStartResponse:
        now = self._now()
        existing_credential = await self.repository.get_credential_by_email(payload.email)
        if existing_credential is not None:
            raise AppError("Seller email is already registered", status.HTTP_409_CONFLICT)

        existing_pending = await self.repository.get_active_pending_by_email(
            email=payload.email,
            now=now,
        )
        if existing_pending is not None:
            raise AppError("Seller registration is already pending", status.HTTP_409_CONFLICT)

        start_token = self.token_factory()
        registration = PendingSellerRegistration(
            email=payload.email,
            password_hash=hash_password(payload.password),
            telegram_username=payload.telegram_username,
            bot_start_token_hash=hash_secret(start_token),
            expires_at=now + timedelta(minutes=settings.seller_registration_expires_minutes),
            status=SellerRegistrationStatus.PENDING,
        )
        self.repository.add_pending_registration(registration)
        await self._commit("Seller registration start failed")
        await self.session.refresh(registration)

        start_payload = f"{SELLER_START_PREFIX}{start_token}"
        return SellerRegistrationStartResponse(
            registration_id=registration.id,
            bot_start_link=self._bot_start_link(start_payload),
            start_command=f"/start {start_payload}",
            expires_at=registration.expires_at,
        )

    async def handle_telegram_start(
        self,
        payload: SellerTelegramStartRequest,
    ) -> SellerTelegramStartResponse:
        start_token = self._parse_start_token(payload.start_payload)
        registration = await self.repository.get_pending_by_start_token_hash(
            hash_secret(start_token)
        )
        registration = await self._require_pending_registration(registration)

        if registration.telegram_user_id is not None:
            raise AppError("Telegram start token was already used", status.HTTP_409_CONFLICT)

        self._validate_telegram_username(registration, payload.telegram_username)

        code = self.code_factory()
        now = self._now()
        registration.telegram_user_id = payload.telegram_user_id
        registration.telegram_chat_id = payload.telegram_chat_id
        registration.verification_code_hash = hash_secret(code)
        registration.verification_expires_at = now + timedelta(
            minutes=settings.seller_verification_code_expires_minutes
        )
        await self._commit("Telegram registration link failed")
        await self.session.refresh(registration)
        await self._send_verification_code(registration, code)

        return SellerTelegramStartResponse(
            registration_id=registration.id,
            telegram_username=payload.telegram_username,
            verification_expires_at=registration.verification_expires_at,
        )

    async def resend_code(
        self,
        payload: SellerRegistrationResendCodeRequest,
    ) -> SellerRegistrationResendCodeResponse:
        registration = await self.repository.get_pending_by_id(payload.registration_id)
        registration = await self._require_pending_registration(registration)
        if registration.telegram_chat_id is None:
            raise AppError("Telegram account is not linked yet", status.HTTP_400_BAD_REQUEST)

        code = self.code_factory()
        registration.verification_code_hash = hash_secret(code)
        registration.verification_expires_at = self._now() + timedelta(
            minutes=settings.seller_verification_code_expires_minutes
        )
        await self._commit("Verification code resend failed")
        await self.session.refresh(registration)
        await self._send_verification_code(registration, code)

        return SellerRegistrationResendCodeResponse(
            registration_id=registration.id,
            verification_expires_at=registration.verification_expires_at,
        )

    async def confirm_registration(
        self,
        payload: SellerRegistrationConfirmRequest,
    ) -> TokenResponse:
        registration = await self.repository.get_pending_by_id(payload.registration_id)
        registration = await self._require_pending_registration(registration)
        self._validate_confirmation_code(registration, payload.code)

        existing_credential = await self.repository.get_credential_by_email(registration.email)
        if existing_credential is not None:
            raise AppError("Seller email is already registered", status.HTTP_409_CONFLICT)

        if registration.telegram_user_id is None:
            raise AppError("Telegram account is not linked yet", status.HTTP_400_BAD_REQUEST)

        user = await self.repository.get_user_by_telegram_id(registration.telegram_user_id)
        if user is None:
            user = User(
                telegram_id=registration.telegram_user_id,
                username=registration.telegram_username,
                role=UserRole.SELLER,
                is_active=True,
            )
            self.repository.add_user(user)
            await self.session.flush()
        else:
            user.username = registration.telegram_username or user.username
            if user.role == UserRole.USER:
                user.role = UserRole.SELLER

        if not user.is_active:
            raise AppError("Inactive user", status.HTTP_403_FORBIDDEN)

        credential = SellerCredential(
            user=user,
            email=registration.email,
            password_hash=registration.password_hash,
            telegram_username=registration.telegram_username,
            telegram_user_id=registration.telegram_user_id,
            telegram_chat_id=registration.telegram_chat_id,
            verified_at=self._now(),
        )
        self.repository.add_seller_credential(credential)
        registration.status = SellerRegistrationStatus.VERIFIED
        registration.verified_at = credential.verified_at
        await self._commit("Seller registration confirmation failed")
        await self.session.refresh(user)

        return self._token_response(user)

    async def login(self, payload: SellerLoginRequest) -> TokenResponse:
        credential = await self.repository.get_credential_by_email(payload.email)
        if credential is None or not verify_password(payload.password, credential.password_hash):
            raise AppError("Invalid email or password", status.HTTP_401_UNAUTHORIZED)
        if credential.verified_at is None:
            raise AppError("Seller account is not verified", status.HTTP_403_FORBIDDEN)
        if credential.user.role not in {UserRole.SELLER, UserRole.ADMIN}:
            raise AppError("Insufficient permissions", status.HTTP_403_FORBIDDEN)
        if not credential.user.is_active:
            raise AppError("Inactive user", status.HTTP_403_FORBIDDEN)

        return self._token_response(credential.user)

    async def _require_pending_registration(
        self,
        registration: PendingSellerRegistration | None,
    ) -> PendingSellerRegistration:
        if registration is None:
            raise AppError("Seller registration not found", status.HTTP_404_NOT_FOUND)
        if registration.status != SellerRegistrationStatus.PENDING:
            raise AppError("Seller registration is not pending", status.HTTP_400_BAD_REQUEST)
        if registration.expires_at <= self._now():
            registration.status = SellerRegistrationStatus.EXPIRED
            await self._commit("Seller registration expiration update failed")
            raise AppError("Seller registration expired", status.HTTP_400_BAD_REQUEST)
        return registration

    def _validate_confirmation_code(
        self,
        registration: PendingSellerRegistration,
        code: str,
    ) -> None:
        if (
            registration.verification_code_hash is None
            or registration.verification_expires_at is None
        ):
            raise AppError("Verification code was not sent", status.HTTP_400_BAD_REQUEST)
        if registration.verification_expires_at <= self._now():
            raise AppError("Verification code expired", status.HTTP_400_BAD_REQUEST)
        if not compare_secret(code, registration.verification_code_hash):
            raise AppError("Invalid verification code", status.HTTP_400_BAD_REQUEST)

    def _validate_telegram_username(
        self,
        registration: PendingSellerRegistration,
        actual_username: str | None,
    ) -> None:
        if registration.telegram_username is None:
            return
        if actual_username is None:
            raise AppError(
                "Telegram username is missing on the linked account",
                status.HTTP_400_BAD_REQUEST,
            )
        if actual_username != registration.telegram_username:
            raise AppError(
                "Telegram username does not match the registration",
                status.HTTP_400_BAD_REQUEST,
            )

    def _parse_start_token(self, start_payload: str) -> str:
        payload = start_payload.strip()
        if payload.startswith("/start "):
            payload = payload.split(maxsplit=1)[1].strip()
        if not payload.startswith(SELLER_START_PREFIX):
            raise AppError("Invalid Telegram start payload", status.HTTP_400_BAD_REQUEST)
        start_token = payload.removeprefix(SELLER_START_PREFIX)
        if not start_token:
            raise AppError("Invalid Telegram start payload", status.HTTP_400_BAD_REQUEST)
        return start_token

    async def _send_verification_code(
        self,
        registration: PendingSellerRegistration,
        code: str,
    ) -> None:
        if registration.telegram_chat_id is None:
            raise AppError("Telegram chat is not linked", status.HTTP_400_BAD_REQUEST)
        message = (
            "Seller Portal verification code\n\n"
            f"Code: {code}\n"
            "Enter this code in the Seller Portal to finish registration."
        )
        try:
            await self.telegram_service.send_message(str(registration.telegram_chat_id), message)
        except TelegramDeliveryError as exc:
            raise AppError(
                "Could not send Telegram verification code",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from exc

    def _bot_start_link(self, start_payload: str) -> str | None:
        if not settings.telegram_seller_bot_username:
            return None
        username = settings.telegram_seller_bot_username.lstrip("@")
        return f"https://t.me/{username}?start={start_payload}"

    def _token_response(self, user: User) -> TokenResponse:
        access_token = create_access_token(
            subject=str(user.id),
            additional_claims={"role": user.role.value},
        )
        return TokenResponse(access_token=access_token, user=user)

    async def _commit(self, error_message: str) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(error_message, status.HTTP_409_CONFLICT) from exc

    def _now(self) -> datetime:
        return self.now_factory()


def hash_password(password: str, *, salt: str | None = None) -> str:
    password_salt = salt or secrets.token_urlsafe(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        password_salt.encode("utf-8"),
        PASSWORD_HASH_ITERATIONS,
    )
    encoded_digest = base64.b64encode(digest).decode("ascii")
    return (
        f"{PASSWORD_HASH_ALGORITHM}${PASSWORD_HASH_ITERATIONS}${password_salt}${encoded_digest}"
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt, expected_digest = password_hash.split("$", 3)
        iterations = int(iterations_raw)
    except ValueError:
        return False
    if algorithm != PASSWORD_HASH_ALGORITHM:
        return False

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    encoded_digest = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(encoded_digest, expected_digest)


def hash_secret(value: str) -> str:
    digest = hmac.new(
        settings.jwt_secret_key.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"sha256${digest}"


def compare_secret(value: str, hashed_value: str) -> bool:
    return hmac.compare_digest(hash_secret(value), hashed_value)


def _generate_verification_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"
