from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FavoriteCreate(BaseModel):
    product_id: int


class FavoriteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    product_id: int
    created_at: datetime


class FavoriteList(BaseModel):
    items: list[FavoriteRead]
