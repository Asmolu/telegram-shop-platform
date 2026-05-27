from pydantic import BaseModel


class OrdersStatus(BaseModel):
    module: str
    status: str
