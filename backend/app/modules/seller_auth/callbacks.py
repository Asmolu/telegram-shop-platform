import base64
import hashlib
import hmac

from fastapi import status

from app.core.config import settings
from app.core.errors import AppError

SELLER_APPROVAL_CALLBACK_PREFIX = "sr"
SELLER_APPROVAL_CALLBACK_ACTIONS = {"approve": "a", "reject": "r"}
SELLER_APPROVAL_CALLBACK_CODES = {
    value: key for key, value in SELLER_APPROVAL_CALLBACK_ACTIONS.items()
}


def build_seller_registration_callback_data(
    *,
    action: str,
    registration_id: int,
) -> str:
    action_code = SELLER_APPROVAL_CALLBACK_ACTIONS.get(action)
    if action_code is None:
        raise ValueError("Unsupported seller registration callback action")
    signature = _seller_registration_callback_signature(
        action=action,
        registration_id=registration_id,
    )
    return f"{SELLER_APPROVAL_CALLBACK_PREFIX}:{action_code}:{registration_id}:{signature}"


def parse_seller_registration_callback_data(data: str) -> tuple[str, int]:
    parts = data.split(":")
    if len(parts) != 4 or parts[0] != SELLER_APPROVAL_CALLBACK_PREFIX:
        raise AppError("Invalid approval callback", status.HTTP_400_BAD_REQUEST)

    action = SELLER_APPROVAL_CALLBACK_CODES.get(parts[1])
    if action is None:
        raise AppError("Invalid approval callback", status.HTTP_400_BAD_REQUEST)

    try:
        registration_id = int(parts[2])
    except ValueError:
        raise AppError("Invalid approval callback", status.HTTP_400_BAD_REQUEST) from None
    if registration_id <= 0:
        raise AppError("Invalid approval callback", status.HTTP_400_BAD_REQUEST)

    expected_signature = _seller_registration_callback_signature(
        action=action,
        registration_id=registration_id,
    )
    if not hmac.compare_digest(parts[3], expected_signature):
        raise AppError("Invalid approval callback", status.HTTP_400_BAD_REQUEST)
    return action, registration_id


def _seller_registration_callback_signature(
    *,
    action: str,
    registration_id: int,
) -> str:
    digest = hmac.new(
        settings.jwt_secret_key.encode("utf-8"),
        f"seller-registration-approval:{action}:{registration_id}".encode(),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest[:12]).decode("ascii").rstrip("=")
