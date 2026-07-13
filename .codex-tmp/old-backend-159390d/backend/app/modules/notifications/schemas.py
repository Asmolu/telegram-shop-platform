from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.common.pagination import PageMeta
from app.db.models import NotificationChannel, NotificationStatus


class NotificationsStatus(BaseModel):
    module: str
    status: str


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None = None
    type: str
    title: str
    message: str
    payload: dict[str, object] | None = None
    channel: NotificationChannel
    status: NotificationStatus
    error_message: str | None = None
    sent_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class NotificationList(BaseModel):
    items: list[NotificationRead]
    meta: PageMeta
