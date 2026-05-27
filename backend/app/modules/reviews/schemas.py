from pydantic import BaseModel


class ReviewsStatus(BaseModel):
    module: str
    status: str
