from pydantic import BaseModel


class TelegramStatus(BaseModel):
    module: str
    status: str
