from pydantic import BaseModel


class StatisticsStatus(BaseModel):
    module: str
    status: str
