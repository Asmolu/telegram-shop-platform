from pydantic import BaseModel


class TagsStatus(BaseModel):
    module: str
    status: str
