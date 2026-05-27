from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import settings

RESERVED_JWT_CLAIMS = frozenset({"sub", "iat", "exp"})


class TokenError(ValueError):
    pass


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _base64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(f"{data}{padding}".encode("ascii"))


def create_access_token(
    subject: str,
    expires_delta: timedelta | None = None,
    additional_claims: dict[str, Any] | None = None,
) -> str:
    if settings.jwt_algorithm != "HS256":
        raise TokenError("Only HS256 JWT tokens are supported")

    now = datetime.now(UTC)
    expire_at = now + (expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes))
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(expire_at.timestamp()),
    }
    if additional_claims:
        reserved_claims = RESERVED_JWT_CLAIMS.intersection(additional_claims)
        if reserved_claims:
            claims = ", ".join(sorted(reserved_claims))
            raise TokenError(f"Additional JWT claims cannot override reserved claims: {claims}")
        payload.update(additional_claims)

    header = {"alg": settings.jwt_algorithm, "typ": "JWT"}
    encoded_header = _base64url_encode(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    encoded_payload = _base64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(
        settings.jwt_secret_key.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    return f"{encoded_header}.{encoded_payload}.{_base64url_encode(signature)}"


def verify_access_token(token: str) -> dict[str, Any]:
    if settings.jwt_algorithm != "HS256":
        raise TokenError("Only HS256 JWT tokens are supported")

    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".")
    except ValueError as exc:
        raise TokenError("Invalid token format") from exc

    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    expected_signature = hmac.new(
        settings.jwt_secret_key.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    actual_signature = _base64url_decode(encoded_signature)
    if not hmac.compare_digest(expected_signature, actual_signature):
        raise TokenError("Invalid token signature")

    try:
        header = json.loads(_base64url_decode(encoded_header))
        payload = json.loads(_base64url_decode(encoded_payload))
    except (json.JSONDecodeError, ValueError) as exc:
        raise TokenError("Invalid token payload") from exc

    if header.get("alg") != settings.jwt_algorithm or header.get("typ") != "JWT":
        raise TokenError("Invalid token header")

    expires_at = payload.get("exp")
    if not isinstance(expires_at, int):
        raise TokenError("Invalid token expiration")
    if datetime.now(UTC).timestamp() >= expires_at:
        raise TokenError("Token expired")

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise TokenError("Invalid token subject")

    return payload
