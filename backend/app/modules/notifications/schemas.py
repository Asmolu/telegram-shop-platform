from pydantic import BaseModel


class NotificationsStatus(BaseModel):
    module: str
    status: str
