from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import TokenError, verify_access_token
from app.db.models import User, UserRole
from app.db.session import async_session_factory
from app.modules.users.repository import UsersRepository

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.api_v1_prefix}/auth/telegram/login",
    auto_error=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
    if token is None:
        raise _authentication_error()

    try:
        payload = verify_access_token(token)
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError, TokenError):
        raise _authentication_error() from None

    user = await UsersRepository(session).get_by_id(user_id)
    if user is None:
        raise _authentication_error()
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    return user


async def get_optional_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> User | None:
    if token is None:
        return None

    try:
        payload = verify_access_token(token)
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError, TokenError):
        return None

    user = await UsersRepository(session).get_by_id(user_id)
    if user is None or not user.is_active:
        return None
    return user


def require_roles(*allowed_roles: UserRole):
    async def dependency(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return dependency


def _authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
