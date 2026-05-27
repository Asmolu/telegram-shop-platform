from pydantic import BaseModel


class CartStatus(BaseModel):
    module: str
    status: str
