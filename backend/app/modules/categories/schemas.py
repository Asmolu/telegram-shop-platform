from pydantic import BaseModel


class CategoriesStatus(BaseModel):
    module: str
    status: str
