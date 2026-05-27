from pydantic import BaseModel


class PromoCodesStatus(BaseModel):
    module: str
    status: str
