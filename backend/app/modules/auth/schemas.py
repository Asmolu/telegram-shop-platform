from pydantic import BaseModel, Field


class TelegramLoginRequest(BaseModel):
    init_data: str = Field(..., description="Telegram WebApp initData string")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
