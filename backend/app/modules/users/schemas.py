from pydantic import BaseModel


class UsersStatus(BaseModel):
    module: str
    status: str
