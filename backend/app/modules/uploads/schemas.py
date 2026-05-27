from pydantic import BaseModel


class UploadsStatus(BaseModel):
    module: str
    status: str
