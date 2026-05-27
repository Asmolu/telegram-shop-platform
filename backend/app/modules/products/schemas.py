from pydantic import BaseModel


class ProductsStatus(BaseModel):
    module: str
    status: str
