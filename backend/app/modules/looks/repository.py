from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    Look,
    LookImage,
    LookItem,
    LookStatus,
    Product,
    ProductCategory,
    ProductImage,
)


class LooksRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_public(self, *, limit: int, offset: int) -> tuple[list[Look], int]:
        base_filter = (Look.status == LookStatus.ACTIVE, Look.is_listed.is_(True))
        total = await self._count(*base_filter)
        result = await self.session.execute(
            self._look_select()
            .where(*base_filter)
            .order_by(Look.search_priority.asc(), Look.created_at.desc(), Look.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().unique()), total

    async def list_admin(
        self,
        *,
        limit: int,
        offset: int,
        status_filter: LookStatus | None = None,
    ) -> tuple[list[Look], int]:
        filters = []
        if status_filter is not None:
            filters.append(Look.status == status_filter)

        total = await self._count(*filters)
        result = await self.session.execute(
            self._look_select()
            .where(*filters)
            .order_by(Look.created_at.desc(), Look.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().unique()), total

    async def get_public_by_slug(self, slug: str) -> Look | None:
        result = await self.session.execute(
            self._look_select().where(
                Look.slug == slug,
                Look.status == LookStatus.ACTIVE,
                Look.is_listed.is_(True),
            )
        )
        return result.scalars().unique().one_or_none()

    async def get_public_by_id(self, look_id: int) -> Look | None:
        result = await self.session.execute(
            self._look_select().where(
                Look.id == look_id,
                Look.status == LookStatus.ACTIVE,
                Look.is_listed.is_(True),
            )
        )
        return result.scalars().unique().one_or_none()

    async def get_public_similarity_context_by_slug(self, slug: str) -> Look | None:
        result = await self.session.execute(
            self._look_select(include_product_taxonomy=True).where(
                Look.slug == slug,
                Look.status == LookStatus.ACTIVE,
                Look.is_listed.is_(True),
            )
        )
        return result.scalars().unique().one_or_none()

    async def get_public_similarity_context_by_id(self, look_id: int) -> Look | None:
        result = await self.session.execute(
            self._look_select(include_product_taxonomy=True).where(
                Look.id == look_id,
                Look.status == LookStatus.ACTIVE,
                Look.is_listed.is_(True),
            )
        )
        return result.scalars().unique().one_or_none()

    async def get_admin_by_id(self, look_id: int) -> Look | None:
        result = await self.session.execute(self._look_select().where(Look.id == look_id))
        return result.scalars().unique().one_or_none()

    async def get_by_slug(self, slug: str) -> Look | None:
        result = await self.session.execute(self._look_select().where(Look.slug == slug))
        return result.scalars().unique().one_or_none()

    async def list_numeric_slug_candidates(self) -> list[str]:
        result = await self.session.execute(
            select(Look.slug).where(
                func.length(Look.slug) == 5,
                Look.slug >= "00001",
                Look.slug <= "99999",
            )
        )
        return list(result.scalars().all())

    async def get_product_by_id(self, product_id: int) -> Product | None:
        result = await self.session.execute(
            select(Product)
            .options(
                selectinload(Product.variants),
                selectinload(Product.images).load_only(
                    ProductImage.id,
                    ProductImage.product_id,
                    ProductImage.file_path,
                    ProductImage.thumbnail_path,
                    ProductImage.card_path,
                    ProductImage.position,
                    ProductImage.is_primary,
                ),
            )
            .where(Product.id == product_id)
        )
        return result.scalar_one_or_none()

    async def get_image(self, *, look_id: int, image_id: int) -> LookImage | None:
        result = await self.session.execute(
            select(LookImage).where(LookImage.look_id == look_id, LookImage.id == image_id)
        )
        return result.scalar_one_or_none()

    async def next_image_position(self, look_id: int) -> int:
        result = await self.session.execute(
            select(func.coalesce(func.max(LookImage.position), -1)).where(
                LookImage.look_id == look_id
            )
        )
        return int(result.scalar_one()) + 1

    async def clear_primary_images(self, look_id: int) -> None:
        result = await self.session.execute(
            select(LookImage).where(LookImage.look_id == look_id, LookImage.is_primary.is_(True))
        )
        for image in result.scalars():
            image.is_primary = False

    def add(self, instance: Look | LookImage | LookItem) -> None:
        self.session.add(instance)

    async def delete(self, instance: LookImage | LookItem) -> None:
        await self.session.delete(instance)

    async def _count(self, *filters: object) -> int:
        result = await self.session.execute(select(func.count()).select_from(Look).where(*filters))
        return int(result.scalar_one())

    def _look_select(self, *, include_product_taxonomy: bool = False):
        options = [
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
        ]
        if include_product_taxonomy:
            options.extend(
                [
                    selectinload(Look.items).selectinload(LookItem.product).selectinload(
                        Product.product_categories
                    ).load_only(
                        ProductCategory.product_id,
                        ProductCategory.category_id,
                        ProductCategory.priority,
                    ),
                    selectinload(Look.items).selectinload(LookItem.product).selectinload(
                        Product.tags
                    ),
                ]
            )
        return select(Look).options(*options)
