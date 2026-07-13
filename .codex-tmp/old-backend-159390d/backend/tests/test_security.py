from datetime import timedelta

import pytest

from app.core.security import TokenError, create_access_token, verify_access_token


def test_jwt_access_token_create_and_verify() -> None:
    token = create_access_token(subject="123", additional_claims={"role": "USER"})

    payload = verify_access_token(token)

    assert payload["sub"] == "123"
    assert payload["role"] == "USER"
    assert isinstance(payload["exp"], int)


@pytest.mark.parametrize("reserved_claim", ["sub", "iat", "exp"])
def test_jwt_additional_claims_cannot_override_reserved_claims(reserved_claim: str) -> None:
    with pytest.raises(TokenError, match="reserved claims"):
        create_access_token(subject="123", additional_claims={reserved_claim: "override"})


def test_jwt_rejects_expired_token() -> None:
    token = create_access_token(subject="123", expires_delta=timedelta(seconds=-1))

    with pytest.raises(TokenError, match="expired"):
        verify_access_token(token)


def test_jwt_rejects_tampered_token() -> None:
    token = create_access_token(subject="123")
    header, payload, signature = token.split(".")
    replacement = "A" if signature[0] != "A" else "B"
    tampered_token = f"{header}.{payload}.{replacement}{signature[1:]}"

    with pytest.raises(TokenError):
        verify_access_token(tampered_token)
