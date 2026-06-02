from pydantic import BaseModel, ConfigDict, Field


class TelegramStatus(BaseModel):
    module: str
    status: str


class TelegramUser(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int = Field(..., gt=0)
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None


class TelegramChat(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    type: str | None = None


class TelegramMessage(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    message_id: int | None = None
    text: str | None = None
    chat: TelegramChat
    from_user: TelegramUser | None = Field(default=None, alias="from")


class TelegramCallbackQuery(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    from_user: TelegramUser = Field(alias="from")
    message: TelegramMessage | None = None
    data: str | None = None


class TelegramUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    update_id: int | None = None
    message: TelegramMessage | None = None
    callback_query: TelegramCallbackQuery | None = None


class SellerBotWebhookResponse(BaseModel):
    ok: bool = True
    handled: bool
    result: str
