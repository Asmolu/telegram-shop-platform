from pydantic import BaseModel


class FavoritesStatus(BaseModel):
    module: str
    status: str
