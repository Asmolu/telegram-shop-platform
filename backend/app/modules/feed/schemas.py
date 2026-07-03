from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.common.pagination import PageMeta
from app.modules.looks.schemas import LookCardRead
from app.modules.products.schemas import ProductCardRead

FeedItemType = Literal["product", "look"]


class FeedProductItem(BaseModel):
    type: Literal["product"] = "product"
    product: ProductCardRead


class FeedLookItem(BaseModel):
    type: Literal["look"] = "look"
    look: LookCardRead


FeedItem = Annotated[FeedProductItem | FeedLookItem, Field(discriminator="type")]


class FeedListResponse(BaseModel):
    items: list[FeedItem]
    meta: PageMeta
