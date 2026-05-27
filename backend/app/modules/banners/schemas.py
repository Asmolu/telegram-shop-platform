from pydantic import BaseModel


class BannersStatus(BaseModel):
    module: str
    status: str
