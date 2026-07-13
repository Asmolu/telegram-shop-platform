from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PageMeta
from app.modules.feed.repository import FeedRepository
from app.modules.feed.schemas import FeedListResponse, FeedLookItem, FeedProductItem
from app.modules.looks.service import LooksService
from app.modules.products.schemas import ProductCardRead


class FeedService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = FeedRepository(session)
        self.looks_service = LooksService(session)

    async def list_public_feed(self, *, limit: int, offset: int) -> FeedListResponse:
        refs, total = await self.repository.list_public_refs(limit=limit, offset=offset)
        product_ids = [ref.item_id for ref in refs if ref.item_type == "product"]
        look_ids = [ref.item_id for ref in refs if ref.item_type == "look"]

        products = await self.repository.list_public_products_by_ids(product_ids)
        looks = await self.repository.list_public_looks_by_ids(look_ids)
        products_by_id = {
            product.id: ProductCardRead.model_validate(product) for product in products
        }
        looks_by_id = {
            look.id: self.looks_service.build_card(look) for look in looks
        }

        items = []
        for ref in refs:
            if ref.item_type == "product" and ref.item_id in products_by_id:
                items.append(FeedProductItem(product=products_by_id[ref.item_id]))
            if ref.item_type == "look" and ref.item_id in looks_by_id:
                items.append(FeedLookItem(look=looks_by_id[ref.item_id]))

        return FeedListResponse(
            items=items,
            meta=PageMeta(limit=limit, offset=offset, total=total),
        )
