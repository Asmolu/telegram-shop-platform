from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.common.pagination import PageMeta
from app.db.models import CustomerServiceNotificationDeliveryStatus, NotificationChannel


class CustomerSubscriptionStartLink(BaseModel):
    bot_start_link: str | None
    start_command: str


class CustomerSubscriptionMe(BaseModel):
    has_chat: bool
    service_opt_in: bool
    marketing_opt_in: bool
    blocked_at: datetime | None
    telegram_username: str | None
    bot_start_link: str | None
    start_command: str


class CustomerSubscriptionUpdate(BaseModel):
    service_opt_in: bool | None = None
    marketing_opt_in: bool | None = None


class CustomerSubscriptionAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    telegram_user_id: int
    telegram_chat_id_masked: str | None
    telegram_username: str | None
    telegram_first_name: str | None
    telegram_last_name: str | None
    chat_type: str
    has_chat: bool
    service_opt_in: bool
    marketing_opt_in: bool
    blocked_at: datetime | None
    last_start_at: datetime | None
    last_stop_at: datetime | None
    last_settings_at: datetime | None
    last_delivery_error: str | None
    created_at: datetime
    updated_at: datetime


class CustomerSubscriptionList(BaseModel):
    items: list[CustomerSubscriptionAdminRead]
    meta: PageMeta


class CustomerServiceNotificationDeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    order_id: int | None
    subscription_id: int | None
    event_name: str
    channel: NotificationChannel
    status: CustomerServiceNotificationDeliveryStatus
    telegram_message_id: int | None
    error_code: str | None
    error_message: str | None
    retry_after_seconds: int | None
    sent_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CustomerServiceNotificationDeliveryList(BaseModel):
    items: list[CustomerServiceNotificationDeliveryRead]
    meta: PageMeta


class CustomerBotWebhookResponse(BaseModel):
    ok: bool = True
    handled: bool
    result: str = Field(..., min_length=1)
