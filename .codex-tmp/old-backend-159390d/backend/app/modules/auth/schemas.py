from pydantic import BaseModel, Field

from app.modules.users.schemas import UserRead


class TelegramLoginRequest(BaseModel):
    init_data: str = Field(..., description="Telegram WebApp initData string")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead
