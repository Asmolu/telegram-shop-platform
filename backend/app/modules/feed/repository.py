from dataclasses import dataclass
from typing import Literal

from sqlalchemy import case, func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only, selectinload

from app.db.models import (
    Look,
    LookItem,
    LookStatus,
    Product,
    ProductImage,
    ProductStatus,
    ProductVariant,
)

FeedItemKind = Literal["product", "look"]


@dataclass(frozen=True)
class FeedItemRef:
    item_type: FeedItemKind
    item_id: int


class FeedRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_public_refs(self, *, limit: int, offset: int) -> tuple[list[FeedItemRef], int]:
        feed_query = self._public_feed_query().subquery()
        type_rank = case((feed_query.c.item_type == "product", 0), else_=1)

        rows_result = await self.session.execute(
            select(feed_query.c.item_type, feed_query.c.item_id)
            .order_by(
                feed_query.c.search_priority.asc(),
                feed_query.c.created_at.desc(),
                type_rank.asc(),
                feed_query.c.item_id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        count_result = await self.session.execute(
            select(func.count()).select_from(feed_query)
        )
        return [
            FeedItemRef(item_type=item_type, item_id=item_id)
            for item_type, item_id in rows_result.all()
        ], int(count_result.scalar_one())

    async def list_public_products_by_ids(self, product_ids: list[int]) -> list[Product]:
        if not product_ids:
            return []

        result = await self.session.execute(
            select(Product)
            .options(
                load_only(
                    Product.id,
                    Product.name,
                    Product.slug,
                    Product.brand,
                    Product.base_price,
                    Product.old_price,
                    Product.size_grid,
                    Product.image_badge_type,
                    Product.image_badge_text,
                    Product.image_badge_color,
                    Product.image_badge_position,
                    Product.created_at,
                ),
                selectinload(Product.images).load_only(
                    ProductImage.id,
                    ProductImage.product_id,
                    ProductImage.file_path,
                    ProductImage.thumbnail_path,
                    ProductImage.card_path,
                    ProductImage.detail_path,
                    ProductImage.alt_text,
                    ProductImage.position,
                    ProductImage.is_primary,
                ),
                selectinload(Product.variants.and_(ProductVariant.is_active.is_(True))).load_only(
                    ProductVariant.id,
                    ProductVariant.product_id,
                    ProductVariant.size,
                    ProductVariant.color,
                    ProductVariant.stock_quantity,
                    ProductVariant.reserved_quantity,
                    ProductVariant.is_active,
                ),
            )
            .where(
                Product.id.in_(product_ids),
                Product.status == ProductStatus.ACTIVE,
                Product.is_listed.is_(True),
            )
        )
        return list(result.scalars().all())

    async def list_public_looks_by_ids(self, look_ids: list[int]) -> list[Look]:
        if not look_ids:
            return []

        result = await self.session.execute(
            select(Look)
            .options(
                selectinload(Look.images),
                selectinload(Look.items)
                .selectinload(LookItem.product)
                .selectinload(Product.variants),
                selectinload(Look.items)
                .selectinload(LookItem.product)
                .selectinload(Product.images)
                .load_only(
                    ProductImage.id,
                    ProductImage.product_id,
                    ProductImage.file_path,
                    ProductImage.thumbnail_path,
                    ProductImage.card_path,
                    ProductImage.position,
                    ProductImage.is_primary,
                ),
            )
            .where(
                Look.id.in_(look_ids),
                Look.status == LookStatus.ACTIVE,
                Look.is_listed.is_(True),
            )
        )
        return list(result.scalars().unique())

    def _public_feed_query(self):
        product_query = select(
            literal("product").label("item_type"),
            Product.id.label("item_id"),
            Product.search_priority.label("search_priority"),
            Product.created_at.label("created_at"),
        ).where(
            Product.status == ProductStatus.ACTIVE,
            Product.is_listed.is_(True),
        )
        look_query = select(
            literal("look").label("item_type"),
            Look.id.label("item_id"),
            Look.search_priority.label("search_priority"),
            Look.created_at.label("created_at"),
        ).where(
            Look.status == LookStatus.ACTIVE,
            Look.is_listed.is_(True),
        )
        return union_all(product_query, look_query)
