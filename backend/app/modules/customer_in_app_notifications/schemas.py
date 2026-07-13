from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.db.models import (
    CustomerInAppNotificationActionMode,
    CustomerInAppNotificationCategory,
    CustomerInAppNotificationVariant,
)


class CustomerInAppNotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: CustomerInAppNotificationCategory
    event_code: str
    variant: CustomerInAppNotificationVariant
    action_mode: CustomerInAppNotificationActionMode
    order_id: int | None
    manual_payment_id: int | None
    return_request_id: int | None
    title: str
    message: str
    payload: dict[str, Any]
    occurred_at: datetime
    created_at: datetime


class CustomerInAppNotificationSeenRead(BaseModel):
    id: int
    seen_at: datetime
