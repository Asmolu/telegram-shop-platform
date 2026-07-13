from pydantic import BaseModel, Field


class SellerBotStatusResponse(BaseModel):
    configured: bool
    seller_chat_configured: bool
    ok: bool
    bot: dict[str, object] | None = None
    error: str | None = None


class SellerBotMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class SellerBotBroadcastRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class SellerBotActionResponse(BaseModel):
    notification_id: int
    status: str
    message: str
